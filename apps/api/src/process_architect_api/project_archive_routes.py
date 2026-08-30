from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .entitlement_dependencies import entitlement_http_exception
from .db_models import ProjectArchiveRestore
from .models import ProjectArchiveRestoreResponse, ProjectArchiveValidationResponse
from .project_archive import (
    InvalidProjectArchive,
    ProjectArchiveConflict,
    export_project_archive,
    restore_project_archive,
    validate_project_archive,
)
from .project_routes import project_response
from .services.projects import ProjectNotFound, require_project_access
from .services.workspaces import WorkspaceAccessDenied
from .services.entitlements import (
    EntitlementAccessError,
    require_boolean_entitlement,
    require_project_creation,
)


router = APIRouter(prefix="/api/v1/project-archives", tags=["project-archives"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/projects/{project_id}")
def download_project_archive(
    project_id: str,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    try:
        project = require_project_access(db, project_id, current_user.id)
        require_boolean_entitlement(
            db,
            user=current_user,
            settings=settings,
            entitlement_id="backup.export",
            workspace_id=project.workspace_id,
        )
        content = export_project_archive(db, project)
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)}) from error
    except InvalidProjectArchive as error:
        raise HTTPException(status_code=422, detail={"code": "archive_contains_secrets", "message": str(error)}) from error
    return Response(content, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{project.id}-project-backup.apa.zip"'})


async def _validated(request: Request):
    try:
        return validate_project_archive(await request.body())
    except InvalidProjectArchive as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_project_archive", "message": str(error)}) from error


@router.post("/validate", response_model=ProjectArchiveValidationResponse)
async def validate_archive(request: Request, current_user: CurrentUser, db: DbSession) -> ProjectArchiveValidationResponse:
    validated = await _validated(request)
    existing = db.scalar(select(ProjectArchiveRestore).where(ProjectArchiveRestore.archive_sha256 == validated.archive_sha256))
    restored_project_id = None
    if existing:
        try:
            require_project_access(db, existing.restored_project_id, current_user.id)
            restored_project_id = existing.restored_project_id
        except (ProjectNotFound, WorkspaceAccessDenied):
            pass
    project = validated.documents["project.json"]
    return ProjectArchiveValidationResponse(
        valid=True,
        archive_sha256=validated.archive_sha256,
        source_project_id=project["id"],
        project_name=project["name"],
        format_version=validated.manifest["formatVersion"],
        counts=validated.manifest["counts"],
        warnings=validated.warnings,
        already_restored_project_id=restored_project_id,
    )


@router.post("/restore", response_model=ProjectArchiveRestoreResponse)
async def restore_archive(
    request: Request,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    workspace_id: Annotated[str, Query(alias="workspaceId")],
) -> ProjectArchiveRestoreResponse:
    validated = await _validated(request)
    try:
        require_project_creation(
            db,
            user=current_user,
            settings=settings,
            workspace_id=workspace_id,
        )
        project, already_restored = restore_project_archive(db, validated=validated, workspace_id=workspace_id, user=current_user)
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=403, detail={"code": "workspace_access_denied", "message": str(error)}) from error
    except ProjectArchiveConflict as error:
        raise HTTPException(status_code=409, detail={"code": "project_archive_conflict", "message": str(error)}) from error
    return ProjectArchiveRestoreResponse(project=project_response(db, project), archive_sha256=validated.archive_sha256, already_restored=already_restored)
