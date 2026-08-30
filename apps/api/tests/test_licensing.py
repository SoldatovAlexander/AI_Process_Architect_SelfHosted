import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from process_architect_api.config import get_settings
from process_architect_api.services.licensing import canonical_payload
from process_architect_api.deployment_profiles import clear_deployment_profile_cache

from test_api import authorization, request


def register() -> tuple[dict[str, str], str]:
    tokens = request("POST", "/api/v1/auth/register", json={
        "email": "license-owner@example.com", "password": "correct-horse-battery-staple",
    }).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    return headers, user["workspaces"][0]["workspace_id"]


def configure_issuer(tmp_path, monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust_path = tmp_path / "trusted.json"
    trust_path.write_text(json.dumps({
        "schemaVersion": "1",
        "keys": [{"keyId": "test-issuer", "publicKey": base64.urlsafe_b64encode(public_raw).decode().rstrip("=")}],
    }), encoding="utf-8")
    revocations_path = tmp_path / "revocations.json"
    revocations_path.write_text('{"schemaVersion":"1","licenseIds":[]}', encoding="utf-8")
    monkeypatch.setenv("LICENSE_TRUSTED_KEYS_PATH", str(trust_path))
    monkeypatch.setenv("LICENSE_REVOCATIONS_PATH", str(revocations_path))
    get_settings.cache_clear()
    return private_key, revocations_path


def envelope(private_key, deployment_id: str, workspace_id: str, **changes):
    now = datetime.now(timezone.utc)
    payload = {
        "schemaVersion": "1", "licenseId": "license-test-0001", "keyId": "test-issuer",
        "customerId": "customer-test", "deploymentId": deployment_id, "workspaceId": workspace_id,
        "planId": "self_hosted_full", "catalogVersion": "1.1",
        "issuedAt": (now - timedelta(minutes=1)).isoformat(),
        "notBefore": (now - timedelta(minutes=1)).isoformat(),
        "expiresAt": (now + timedelta(days=30)).isoformat(),
        "graceUntil": (now + timedelta(days=37)).isoformat(),
        "entitlementOverrides": {"project.max_active": 3},
    }
    payload.update(changes)
    signature = private_key.sign(canonical_payload(payload))
    return {"payload": payload, "signature": base64.urlsafe_b64encode(signature).decode().rstrip("=")}


def test_offline_license_activation_updates_effective_entitlements(tmp_path, monkeypatch):
    private_key, _ = configure_issuer(tmp_path, monkeypatch)
    headers, workspace_id = register()
    status = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers).json()

    activated = request(
        "POST", f"/api/v1/workspaces/{workspace_id}/license/offline", headers=headers,
        json={"envelope": envelope(private_key, status["deploymentId"], workspace_id)},
    )
    effective = request("GET", f"/api/v1/workspaces/{workspace_id}/entitlements", headers=headers)

    assert activated.status_code == 200
    assert activated.json()["license"]["licenseId"] == "license-test-0001"
    assert activated.json()["license"]["activationSource"] == "offline"
    assert effective.json()["source"] == "license"
    assert effective.json()["entitlements"]["project.max_active"] == 3


def test_tampered_and_foreign_licenses_are_rejected(tmp_path, monkeypatch):
    private_key, _ = configure_issuer(tmp_path, monkeypatch)
    headers, workspace_id = register()
    deployment_id = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers).json()["deploymentId"]
    signed = envelope(private_key, deployment_id, workspace_id)
    signed["payload"]["planId"] = "read_only"

    tampered = request("POST", f"/api/v1/workspaces/{workspace_id}/license/offline", headers=headers, json={"envelope": signed})
    foreign = request("POST", f"/api/v1/workspaces/{workspace_id}/license/offline", headers=headers, json={
        "envelope": envelope(private_key, "5f76c97f-594f-4eba-8a65-7860cc9b3ee9", workspace_id),
    })

    assert tampered.status_code == 422
    assert tampered.json()["detail"]["code"] == "license_signature_invalid"
    assert foreign.status_code == 422
    assert foreign.json()["detail"]["code"] == "license_binding_mismatch"


def test_local_revocation_fails_closed_and_keeps_backup_right(tmp_path, monkeypatch):
    private_key, revocations_path = configure_issuer(tmp_path, monkeypatch)
    headers, workspace_id = register()
    deployment_id = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers).json()["deploymentId"]
    request("POST", f"/api/v1/workspaces/{workspace_id}/license/offline", headers=headers, json={
        "envelope": envelope(private_key, deployment_id, workspace_id),
    })
    revocations_path.write_text('{"schemaVersion":"1","licenseIds":["license-test-0001"]}', encoding="utf-8")

    effective = request("GET", f"/api/v1/workspaces/{workspace_id}/entitlements", headers=headers)

    assert effective.json()["status"] == "revoked"
    assert effective.json()["plan_id"] == "read_only"
    assert effective.json()["entitlements"]["backup.export"] is True


def test_online_activation_uses_same_signed_envelope(tmp_path, monkeypatch):
    private_key, _ = configure_issuer(tmp_path, monkeypatch)
    monkeypatch.setenv("LICENSE_SERVER_URL", "https://licenses.example.com")
    get_settings.cache_clear()
    headers, workspace_id = register()
    deployment_id = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers).json()["deploymentId"]

    async def fake_fetch(**kwargs):
        assert kwargs["activation_code"] == "activation-code"
        assert kwargs["deployment_id"] == deployment_id
        return envelope(private_key, deployment_id, workspace_id, licenseId="license-online-0001")

    monkeypatch.setattr("process_architect_api.license_routes.fetch_online_license", fake_fetch)
    response = request("POST", f"/api/v1/workspaces/{workspace_id}/license/online", headers=headers, json={"activationCode": "activation-code"})

    assert response.status_code == 200
    assert response.json()["license"]["licenseId"] == "license-online-0001"
    assert response.json()["license"]["activationSource"] == "online"


def test_license_longer_than_three_months_is_rejected(tmp_path, monkeypatch):
    private_key, _ = configure_issuer(tmp_path, monkeypatch)
    headers, workspace_id = register()
    deployment_id = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers).json()["deploymentId"]
    signed = envelope(private_key, deployment_id, workspace_id)
    issued = datetime.fromisoformat(signed["payload"]["notBefore"].replace("Z", "+00:00"))
    signed["payload"]["expiresAt"] = (issued + timedelta(days=94)).isoformat()
    signed["payload"]["graceUntil"] = (issued + timedelta(days=101)).isoformat()
    signed["signature"] = base64.urlsafe_b64encode(private_key.sign(canonical_payload(signed["payload"]))).decode().rstrip("=")

    response = request("POST", f"/api/v1/workspaces/{workspace_id}/license/offline", headers=headers, json={"envelope": signed})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "license_duration_exceeded"


def test_hosted_control_plane_does_not_expose_consumer_license_activation(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    if not (root / "config" / "deployment_profiles" / "v1" / "hosted.json").is_file():
        pytest.skip("hosted deployment profile is excluded from the self-hosted package")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, workspace_id = register()

    response = request("GET", f"/api/v1/workspaces/{workspace_id}/license", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "license_management_unavailable"
