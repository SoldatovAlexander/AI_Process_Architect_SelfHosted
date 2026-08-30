from typing import Annotated
from urllib.parse import urlparse
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import get_settings
from .database import get_db
from .db_models import RuntimeConnectionCheck, RuntimeConnectionProfile
from .models import RuntimeConnectionCheckResponse, RuntimeConnectionProfileRequest, RuntimeConnectionProfileResponse
from .services.runtime_connections import RuntimeVerificationError, verify_runtime_connection
from .services.workspaces import WorkspaceAccessDenied, require_membership


router = APIRouter(prefix="/api/v1", tags=["runtime-connections"])
DbSession = Annotated[Session, Depends(get_db)]


def _membership(db: Session, workspace_id: str, user: CurrentUser, *, owner: bool = False):
    try:
        membership = require_membership(db, workspace_id, user.id)
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found", "message": str(error)}) from error
    if owner and membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    return membership


def _profile(db: Session, profile_id: str, user: CurrentUser, *, owner: bool = False) -> RuntimeConnectionProfile:
    profile = db.get(RuntimeConnectionProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail={"code": "runtime_profile_not_found"})
    _membership(db, profile.workspace_id, user, owner=owner)
    return profile


def _validated_endpoint(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
        raise HTTPException(status_code=422, detail={"code": "invalid_runtime_endpoint", "message": "Use an HTTP(S) endpoint without embedded credentials, query parameters, or fragments."})
    host = parsed.hostname.lower()
    e2e_hosts = {"fake-n8n", "fake-agent-runtime"}
    e2e_allowed = get_settings().e2e_runtime_enabled and host in e2e_hosts
    if parsed.scheme != "https" and host not in {"localhost", "127.0.0.1", "::1"} and not e2e_allowed:
        raise HTTPException(status_code=422, detail={"code": "insecure_runtime_endpoint", "message": "Remote runtime endpoints must use HTTPS."})
    return value.rstrip("/")


def _response(profile: RuntimeConnectionProfile) -> RuntimeConnectionProfileResponse:
    return RuntimeConnectionProfileResponse.model_validate(profile, from_attributes=True)


@router.get("/workspaces/{workspace_id}/runtime-connections", response_model=list[RuntimeConnectionProfileResponse])
def list_runtime_connections(workspace_id: str, current_user: CurrentUser, db: DbSession) -> list[RuntimeConnectionProfileResponse]:
    _membership(db, workspace_id, current_user)
    profiles = db.scalars(select(RuntimeConnectionProfile).where(RuntimeConnectionProfile.workspace_id == workspace_id).order_by(RuntimeConnectionProfile.name)).all()
    return [_response(item) for item in profiles]


@router.post("/workspaces/{workspace_id}/runtime-connections", response_model=RuntimeConnectionProfileResponse, status_code=status.HTTP_201_CREATED)
def create_runtime_connection(workspace_id: str, request: RuntimeConnectionProfileRequest, current_user: CurrentUser, db: DbSession) -> RuntimeConnectionProfileResponse:
    _membership(db, workspace_id, current_user, owner=True)
    profile = RuntimeConnectionProfile(workspace_id=workspace_id, name=request.name, kind=request.kind, endpoint_url=_validated_endpoint(request.endpoint_url), secret_ref=request.secret_ref, n8n_minor=request.n8n_minor, status="draft", created_by_user_id=current_user.id)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "runtime_profile_exists", "message": "A profile with this name already exists in the workspace."}) from error
    db.refresh(profile)
    return _response(profile)


@router.put("/runtime-connections/{profile_id}", response_model=RuntimeConnectionProfileResponse)
def update_runtime_connection(profile_id: str, request: RuntimeConnectionProfileRequest, current_user: CurrentUser, db: DbSession) -> RuntimeConnectionProfileResponse:
    profile = _profile(db, profile_id, current_user, owner=True)
    profile.name = request.name
    profile.kind = request.kind
    profile.endpoint_url = _validated_endpoint(request.endpoint_url)
    profile.secret_ref = request.secret_ref
    profile.n8n_minor = request.n8n_minor
    profile.status = "draft"
    profile.detected_version = None
    profile.last_check_code = None
    profile.last_checked_at = None
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "runtime_profile_exists"}) from error
    db.refresh(profile)
    return _response(profile)


@router.post("/runtime-connections/{profile_id}/verify", response_model=RuntimeConnectionCheckResponse)
async def verify_connection(profile_id: str, current_user: CurrentUser, db: DbSession) -> RuntimeConnectionCheckResponse:
    profile = _profile(db, profile_id, current_user, owner=True)
    checked_at = datetime.now(timezone.utc)
    try:
        result = await verify_runtime_connection(profile)
        profile.status = "verified"
        profile.detected_version = result.detected_version
        profile.last_check_code = result.code
    except RuntimeVerificationError as error:
        result_code = error.code
        profile.status = "failed"
        profile.detected_version = None
        profile.last_check_code = result_code
    else:
        result_code = result.code
    profile.last_checked_at = checked_at
    db.add(RuntimeConnectionCheck(profile_id=profile.id, status=profile.status, result_code=result_code, detected_version=profile.detected_version, checked_by_user_id=current_user.id, checked_at=checked_at))
    db.commit()
    db.refresh(profile)
    return RuntimeConnectionCheckResponse(profile=_response(profile), result_code=result_code, detected_version=profile.detected_version)


@router.post("/runtime-connections/{profile_id}/disable", response_model=RuntimeConnectionProfileResponse)
def disable_connection(profile_id: str, current_user: CurrentUser, db: DbSession) -> RuntimeConnectionProfileResponse:
    profile = _profile(db, profile_id, current_user, owner=True)
    profile.status = "disabled"
    db.commit()
    db.refresh(profile)
    return _response(profile)


@router.delete("/runtime-connections/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_runtime_connection(profile_id: str, current_user: CurrentUser, db: DbSession) -> Response:
    profile = _profile(db, profile_id, current_user, owner=True)
    db.delete(profile)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
