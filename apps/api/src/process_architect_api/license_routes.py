from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .deployment_profiles import get_deployment_profile
from .monitoring import record_license_validation
from .services.licensing import (
    LicenseValidationError,
    activate_license,
    active_workspace_license,
    ensure_installation_state,
    fetch_online_license,
)
from .services.workspaces import WorkspaceAccessDenied, require_membership


router = APIRouter(prefix="/api/v1", tags=["licenses"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class OfflineLicenseRequest(BaseModel):
    envelope: dict[str, Any]


class OnlineLicenseRequest(BaseModel):
    activation_code: str = Field(alias="activationCode", min_length=6, max_length=256)


def _owner(db: Session, workspace_id: str, user: CurrentUser) -> None:
    if get_deployment_profile().administration.license_mode != "consumer":
        raise HTTPException(status_code=404, detail={"code": "license_management_unavailable"})
    try:
        membership = require_membership(db, workspace_id, user.id)
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})


def _error(error: LicenseValidationError) -> HTTPException:
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE if error.code in {
        "license_server_not_configured", "license_server_unavailable"
    } else status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=status_code, detail={"code": error.code, "message": str(error)})


def _response(db: Session, workspace_id: str) -> dict[str, Any]:
    installation = ensure_installation_state(db)
    record = active_workspace_license(db, workspace_id)
    db.commit()
    return {
        "deploymentId": installation.deployment_id,
        "workspaceId": workspace_id,
        "license": None if record is None else {
            "licenseId": record.license_id,
            "keyId": record.key_id,
            "planId": record.payload["planId"],
            "catalogVersion": record.payload["catalogVersion"],
            "status": record.status,
            "activationSource": record.activation_source,
            "issuedAt": record.payload["issuedAt"],
            "expiresAt": record.payload["expiresAt"],
            "graceUntil": record.payload["graceUntil"],
            "activatedAt": record.activated_at,
        },
    }


@router.get("/workspaces/{workspace_id}/license")
def license_status(workspace_id: str, current_user: CurrentUser, db: DbSession) -> dict[str, Any]:
    _owner(db, workspace_id, current_user)
    return _response(db, workspace_id)


@router.post("/workspaces/{workspace_id}/license/offline")
def activate_offline_license(
    workspace_id: str,
    request: OfflineLicenseRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict[str, Any]:
    _owner(db, workspace_id, current_user)
    try:
        activate_license(db, workspace_id=workspace_id, user=current_user, envelope=request.envelope, source="offline", settings=settings)
    except LicenseValidationError as error:
        record_license_validation("offline", _metric_outcome(error.code))
        raise _error(error) from error
    record_license_validation("offline", "success")
    return _response(db, workspace_id)


@router.post("/workspaces/{workspace_id}/license/online")
async def activate_online_license(
    workspace_id: str,
    request: OnlineLicenseRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict[str, Any]:
    _owner(db, workspace_id, current_user)
    installation = ensure_installation_state(db)
    db.commit()
    try:
        envelope = await fetch_online_license(
            activation_code=request.activation_code,
            deployment_id=installation.deployment_id,
            workspace_id=workspace_id,
            settings=settings,
        )
        activate_license(db, workspace_id=workspace_id, user=current_user, envelope=envelope, source="online", settings=settings)
    except LicenseValidationError as error:
        record_license_validation("online", _metric_outcome(error.code))
        raise _error(error) from error
    record_license_validation("online", "success")
    return _response(db, workspace_id)


def _metric_outcome(code: str) -> str:
    if code == "license_signature_invalid":
        return "invalid_signature"
    if code == "license_binding_mismatch":
        return "binding_mismatch"
    if code == "license_expired":
        return "expired"
    if code == "license_revoked":
        return "revoked"
    if code.startswith("license_server"):
        return "server_error"
    if code in {"license_trust_store_invalid", "license_revocation_list_invalid", "license_schema_unavailable"}:
        return "configuration_error"
    return "invalid_document"
