from __future__ import annotations

from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .services.entitlements import (
    EffectiveEntitlements,
    EntitlementAccessError,
    require_boolean_entitlement,
)


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def entitlement_http_exception(error: EntitlementAccessError) -> HTTPException:
    if error.reason == "workspace_context_required":
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        code = "workspace_context_required"
    elif error.reason == "workspace_access_denied":
        status_code = status.HTTP_403_FORBIDDEN
        code = "workspace_access_denied"
    elif error.reason == "limit_reached":
        status_code = status.HTTP_403_FORBIDDEN
        code = "entitlement_limit_exceeded"
    else:
        status_code = status.HTTP_403_FORBIDDEN
        code = "entitlement_required"
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "entitlementId": error.entitlement_id,
            "reason": error.reason,
            "limit": error.limit,
        },
    )


def entitlement_dependency(
    entitlement_id: str,
) -> Callable[..., EffectiveEntitlements]:
    def require_entitlement(
        current_user: CurrentUser,
        db: DbSession,
        settings: AppSettings,
        workspace_id: Annotated[str | None, Query(alias="workspaceId")] = None,
    ) -> EffectiveEntitlements:
        try:
            return require_boolean_entitlement(
                db,
                user=current_user,
                settings=settings,
                entitlement_id=entitlement_id,
                workspace_id=workspace_id,
            )
        except EntitlementAccessError as error:
            raise entitlement_http_exception(error) from error

    require_entitlement.__name__ = f"require_{entitlement_id.replace('.', '_')}"
    return require_entitlement


CodeGenerateEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("code.generate")),
]
SpecExportEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("export.spec")),
]
BpmnExportEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("export.bpmn")),
]
N8nExportEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("export.n8n")),
]
AgentExportEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("export.agent")),
]
PrivateTemplateEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("template.private")),
]
InterviewImportEntitlement = Annotated[
    EffectiveEntitlements,
    Depends(entitlement_dependency("interview.import")),
]
