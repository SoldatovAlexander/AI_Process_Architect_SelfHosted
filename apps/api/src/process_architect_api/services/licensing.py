from __future__ import annotations

import base64
import calendar
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import InstallationState, User, WorkspaceCommercialState, WorkspaceLicense
from ..entitlements import EntitlementCatalogError, get_entitlement_catalog
from ..deployment_profiles import get_deployment_profile
from ..paths import WORKSPACE_ROOT
from ..monitoring import record_license_validation


LICENSE_SCHEMA_PATH = WORKSPACE_ROOT / "02_architecture" / "schemas" / "license-envelope-v1.schema.json"


class LicenseValidationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ValidatedLicense:
    payload: dict
    signature: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    grace_until: datetime


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone is required.")
    return parsed.astimezone(timezone.utc)


def _add_months(value: datetime, months: int) -> datetime:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _read_json(path: str, code: str) -> dict:
    try:
        value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LicenseValidationError(code, f"Cannot read licensing configuration: {error}") from error
    if not isinstance(value, dict):
        raise LicenseValidationError(code, "Licensing configuration must be a JSON object.")
    return value


def _trusted_keys(settings: Settings) -> dict[str, Ed25519PublicKey]:
    path = settings.license_trusted_keys_path or str(WORKSPACE_ROOT / "config" / "licensing" / "trusted-public-keys.json")
    document = _read_json(path, "license_trust_store_invalid")
    if document.get("schemaVersion") != "1" or not isinstance(document.get("keys"), list):
        raise LicenseValidationError("license_trust_store_invalid", "Invalid trusted key catalog.")
    result: dict[str, Ed25519PublicKey] = {}
    for entry in document["keys"]:
        try:
            key_id = entry["keyId"]
            raw = base64.urlsafe_b64decode(entry["publicKey"] + "==")
            if not isinstance(key_id, str) or key_id in result:
                raise ValueError
            result[key_id] = Ed25519PublicKey.from_public_bytes(raw)
        except (KeyError, TypeError, ValueError) as error:
            raise LicenseValidationError("license_trust_store_invalid", "Invalid Ed25519 public key entry.") from error
    return result


def revoked_license_ids(settings: Settings) -> set[str]:
    path = settings.license_revocations_path or str(WORKSPACE_ROOT / "config" / "licensing" / "revocations.json")
    document = _read_json(path, "license_revocation_list_invalid")
    values = document.get("licenseIds")
    if document.get("schemaVersion") != "1" or not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise LicenseValidationError("license_revocation_list_invalid", "Invalid license revocation list.")
    return set(values)


def canonical_payload(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ensure_installation_state(db: Session) -> InstallationState:
    state = db.get(InstallationState, "installation")
    if state is None:
        state = InstallationState(id="installation", deployment_id=str(uuid4()))
        db.add(state)
        db.flush()
    return state


def validate_license_envelope(
    envelope: dict,
    *,
    settings: Settings,
    deployment_id: str,
    workspace_id: str,
    now: datetime | None = None,
) -> ValidatedLicense:
    try:
        schema = json.loads(LICENSE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LicenseValidationError("license_schema_unavailable", str(error)) from error
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(envelope),
        key=lambda item: list(item.path),
    )
    if errors:
        raise LicenseValidationError("license_format_invalid", errors[0].message)
    payload = envelope["payload"]
    keys = _trusted_keys(settings)
    public_key = keys.get(payload["keyId"])
    if public_key is None:
        raise LicenseValidationError("license_key_unknown", "The signing key is not trusted by this installation.")
    try:
        signature = base64.urlsafe_b64decode(envelope["signature"] + "==")
        public_key.verify(signature, canonical_payload(payload))
    except (InvalidSignature, ValueError) as error:
        raise LicenseValidationError("license_signature_invalid", "License signature verification failed.") from error
    if payload["deploymentId"] != deployment_id or payload["workspaceId"] != workspace_id:
        raise LicenseValidationError("license_binding_mismatch", "License belongs to another installation or workspace.")
    if payload["licenseId"] in revoked_license_ids(settings):
        raise LicenseValidationError("license_revoked", "License has been revoked.")
    try:
        catalog = get_entitlement_catalog()
        catalog.plan(payload["planId"])
        if payload["catalogVersion"] != catalog.catalog_version:
            raise LicenseValidationError("license_catalog_mismatch", "License uses an incompatible entitlement catalog.")
        overrides = payload.get("entitlementOverrides", {})
        for entitlement_id, value in overrides.items():
            definition = catalog.definition(entitlement_id)
            if definition.kind == "boolean" and type(value) is not bool:
                raise ValueError(entitlement_id)
            if definition.kind == "integer" and (type(value) is not int or value < -1):
                raise ValueError(entitlement_id)
    except EntitlementCatalogError as error:
        raise LicenseValidationError("license_plan_invalid", str(error)) from error
    except ValueError as error:
        raise LicenseValidationError("license_override_invalid", f"Invalid entitlement override: {error}") from error
    try:
        issued_at = _utc(payload["issuedAt"])
        not_before = _utc(payload["notBefore"])
        expires_at = _utc(payload["expiresAt"])
        grace_until = _utc(payload["graceUntil"])
    except ValueError as error:
        raise LicenseValidationError("license_time_invalid", str(error)) from error
    current = now or datetime.now(timezone.utc)
    skew = timedelta(seconds=settings.license_clock_skew_seconds)
    if issued_at > current + skew or not_before > current + skew:
        raise LicenseValidationError("license_not_yet_valid", "License validity period has not started.")
    if not_before > expires_at or expires_at > grace_until:
        raise LicenseValidationError("license_time_invalid", "License dates are inconsistent.")
    if expires_at > _add_months(not_before, 3):
        raise LicenseValidationError("license_duration_exceeded", "Self-hosted license duration cannot exceed three months.")
    if current >= grace_until + skew:
        raise LicenseValidationError("license_expired", "License and its grace period have expired.")
    return ValidatedLicense(payload, envelope["signature"], issued_at, not_before, expires_at, grace_until)


def activate_license(
    db: Session,
    *,
    workspace_id: str,
    user: User,
    envelope: dict,
    source: str,
    settings: Settings,
) -> WorkspaceLicense:
    installation = ensure_installation_state(db)
    validated = validate_license_envelope(
        envelope,
        settings=settings,
        deployment_id=installation.deployment_id,
        workspace_id=workspace_id,
    )
    existing = db.scalar(select(WorkspaceLicense).where(WorkspaceLicense.license_id == validated.payload["licenseId"]))
    if existing is not None:
        if existing.workspace_id != workspace_id or existing.signature != validated.signature:
            raise LicenseValidationError("license_id_conflict", "License ID is already used by another document.")
    now = datetime.now(timezone.utc)
    for previous in db.scalars(select(WorkspaceLicense).where(WorkspaceLicense.workspace_id == workspace_id, WorkspaceLicense.status == "active")):
        if existing is not None and previous.id == existing.id:
            continue
        previous.status = "superseded"
        previous.superseded_at = now
    if existing is None:
        record = WorkspaceLicense(
            license_id=validated.payload["licenseId"], workspace_id=workspace_id,
            key_id=validated.payload["keyId"], payload=validated.payload,
            signature=validated.signature, status="active", activation_source=source,
            activated_by_user_id=user.id,
        )
        db.add(record)
    else:
        record = existing
        record.status = "active"
        record.activation_source = source
        record.activated_by_user_id = user.id
        record.activated_at = now
        record.superseded_at = None
    state = db.get(WorkspaceCommercialState, workspace_id)
    if state is None:
        raise LicenseValidationError("commercial_state_missing", "Workspace commercial state is missing.")
    state.plan_id = validated.payload["planId"]
    state.status = "grace" if now >= validated.expires_at else "active"
    state.source = "license"
    state.catalog_version = validated.payload["catalogVersion"]
    state.entitlement_overrides = validated.payload.get("entitlementOverrides", {})
    state.effective_from = validated.not_before
    state.expires_at = validated.expires_at
    state.grace_until = validated.grace_until
    db.commit()
    db.refresh(record)
    return record


def active_workspace_license(db: Session, workspace_id: str) -> WorkspaceLicense | None:
    return db.scalar(
        select(WorkspaceLicense)
        .where(WorkspaceLicense.workspace_id == workspace_id, WorkspaceLicense.status == "active")
        .order_by(WorkspaceLicense.activated_at.desc())
    )


def reconcile_license_state(db: Session, workspace_id: str, settings: Settings) -> None:
    record = active_workspace_license(db, workspace_id)
    if record is None:
        return
    state = db.get(WorkspaceCommercialState, workspace_id)
    if state is None:
        return
    try:
        installation = ensure_installation_state(db)
        validated = validate_license_envelope(
            {"payload": record.payload, "signature": record.signature}, settings=settings,
            deployment_id=installation.deployment_id, workspace_id=workspace_id,
        )
        record_license_validation("runtime", "success")
        now = datetime.now(timezone.utc)
        payload = validated.payload
        state.plan_id = payload["planId"]
        state.status = "grace" if now >= validated.expires_at else "active"
        state.source = "license"
        state.catalog_version = payload["catalogVersion"]
        state.entitlement_overrides = payload.get("entitlementOverrides", {})
        state.effective_from = validated.not_before
        state.expires_at = validated.expires_at
        state.grace_until = validated.grace_until
        db.commit()
    except LicenseValidationError as error:
        outcome = {
            "license_revoked": "revoked",
            "license_expired": "expired",
            "license_signature_invalid": "invalid_signature",
            "license_binding_mismatch": "binding_mismatch",
        }.get(error.code, "configuration_error")
        record_license_validation("runtime", outcome)
        if error.code == "license_revoked":
            record.status = "revoked"
            state.status = "revoked"
            db.commit()
        elif error.code not in {"license_expired", "license_not_yet_valid"}:
            state.status = "read_only"
            db.commit()


async def fetch_online_license(
    *, activation_code: str, deployment_id: str, workspace_id: str, settings: Settings
) -> dict:
    if not settings.license_server_url.strip():
        raise LicenseValidationError("license_server_not_configured", "Online licensing is not configured.")
    parsed = urlparse(settings.license_server_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LicenseValidationError(
            "license_server_not_configured",
            "License server must be an HTTPS base URL without credentials, query, or fragment.",
        )
    profile = get_deployment_profile()
    if profile.network.egress == "local_only":
        raise LicenseValidationError("license_server_not_configured", "This deployment profile permits offline licensing only.")
    if profile.network.egress == "allowlist" and parsed.hostname not in profile.network.allowed_hosts:
        raise LicenseValidationError("license_server_not_configured", "License server host is not allowed by the deployment profile.")
    headers = {"Accept": "application/json"}
    if settings.license_server_token and settings.license_server_token.get_secret_value().strip():
        headers["Authorization"] = f"Bearer {settings.license_server_token.get_secret_value().strip()}"
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                settings.license_server_url.rstrip("/") + "/v1/licenses/activate",
                headers=headers,
                json={"activationCode": activation_code, "deploymentId": deployment_id, "workspaceId": workspace_id, "product": "ai-process-architect"},
            )
            response.raise_for_status()
            value = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise LicenseValidationError("license_server_unavailable", "Online license activation failed.") from error
    if not isinstance(value, dict):
        raise LicenseValidationError("license_server_response_invalid", "License server returned an invalid response.")
    return value
