from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .services.entitlements import EntitlementAccessError, effective_workspace_entitlements, resolve_entitlement_workspace


router = APIRouter(prefix="/api/v1", tags=["entitlements"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/workspaces/{workspace_id}/entitlements")
def current_entitlements(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    try:
        workspace = resolve_entitlement_workspace(db, current_user, workspace_id)
        effective = effective_workspace_entitlements(db, workspace, settings)
    except EntitlementAccessError as error:
        raise HTTPException(status_code=403, detail={"code": error.reason}) from error
    return {
        "workspace_id": workspace.id,
        "plan_id": effective.plan_id,
        "configured_plan_id": effective.configured_plan_id,
        "status": effective.status,
        "source": effective.source,
        "catalog_version": effective.catalog_version,
        "entitlements": effective.values,
        "fallback_reason": effective.fallback_reason,
        "expires_at": effective.expires_at,
        "grace_until": effective.grace_until,
    }
