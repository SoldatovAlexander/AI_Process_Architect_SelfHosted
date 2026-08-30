from typing import Annotated

import jsonpatch
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .config import Settings, get_settings
from .db_models import ProcessRevision, Project
from .models import (
    AgentReadinessResponse,
    ProcessRevisionResponse,
    ProjectCreateRequest,
    ProjectPatchRequest,
    ProjectResponse,
    ProjectTargetModeRequest,
    ProjectRestoreRequest,
    ProjectUndoRequest,
    ReadinessResponse,
    RevisionDiffResponse,
)
from .repositories.projects import list_project_revisions, list_user_projects
from .readiness import calculate_readiness
from .exporters.agents import calculate_agent_readiness
from .process_ir import upgrade_process_ir
from .services.projects import (
    InvalidInitialProcess,
    InvalidProcessPatch,
    ProjectNotFound,
    RevisionConflict,
    RevisionNotFound,
    RevisionNotUndoable,
    apply_process_patch,
    archive_project,
    create_project_with_initial_revision,
    require_project_access,
    require_project_revision,
    restore_revision,
    undo_last_revision,
)
from .services.workspaces import WorkspaceAccessDenied
from .entitlement_dependencies import entitlement_http_exception
from .services.entitlements import EntitlementAccessError, require_project_creation


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def revision_response(revision: ProcessRevision) -> ProcessRevisionResponse:
    return ProcessRevisionResponse(
        id=revision.id,
        project_id=revision.project_id,
        version_number=revision.version_number,
        schema_version=revision.schema_version,
        process_ir=upgrade_process_ir(revision.process_ir),
        forward_patch=revision.forward_patch,
        inverse_patch=revision.inverse_patch,
        validation=revision.validation_result,
        parent_revision_id=revision.parent_revision_id,
        restored_from_revision_id=revision.restored_from_revision_id,
        source=revision.source,
        perspective=revision.perspective,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
    )


def project_response(db: Session, project: Project) -> ProjectResponse:
    if project.current_revision_id is None:
        raise HTTPException(status_code=500, detail="Project has no current revision.")
    current = db.get(ProcessRevision, project.current_revision_id)
    if current is None:
        raise HTTPException(status_code=500, detail="Current revision does not exist.")
    return ProjectResponse(
        id=project.id,
        workspace_id=project.workspace_id,
        name=project.name,
        description=project.description,
        default_locale=project.default_locale,
        status=project.status,
        target_mode=project.target_mode,
        current_revision_id=current.id,
        current_revision=revision_response(current),
        created_by_user_id=project.created_by_user_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _translate_error(error: RuntimeError) -> HTTPException:
    if isinstance(error, ProjectNotFound):
        return HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)})
    if isinstance(error, RevisionNotFound):
        return HTTPException(status_code=404, detail={"code": "revision_not_found", "message": str(error)})
    if isinstance(error, WorkspaceAccessDenied):
        return HTTPException(status_code=403, detail={"code": "project_access_denied", "message": str(error)})
    if isinstance(error, RevisionConflict):
        return HTTPException(
            status_code=409,
            detail={
                "code": "revision_conflict",
                "message": str(error),
                "currentRevisionId": error.current_revision_id,
            },
        )
    if isinstance(error, RevisionNotUndoable):
        return HTTPException(status_code=409, detail={"code": "revision_not_undoable", "message": str(error)})
    if isinstance(error, (InvalidInitialProcess, InvalidProcessPatch)):
        return HTTPException(status_code=422, detail={"code": "invalid_process_change", "message": str(error)})
    return HTTPException(status_code=500, detail="Unexpected project error.")


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    request: ProjectCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> ProjectResponse:
    try:
        require_project_creation(
            db,
            user=current_user,
            settings=settings,
            workspace_id=request.workspace_id,
        )
        project, _ = create_project_with_initial_revision(
            db,
            user=current_user,
            workspace_id=request.workspace_id,
            name=request.name,
            process_ir=request.process_ir,
            default_locale=request.default_locale,
            target_mode=request.target_mode,
        )
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except (InvalidInitialProcess, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    current_user: CurrentUser,
    db: DbSession,
    workspace_id: Annotated[str | None, Query()] = None,
) -> list[ProjectResponse]:
    return [project_response(db, project) for project in list_user_projects(db, current_user.id, workspace_id)]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, current_user: CurrentUser, db: DbSession) -> ProjectResponse:
    try:
        project = require_project_access(db, project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)


@router.get("/{project_id}/readiness", response_model=ReadinessResponse)
def get_readiness(
    project_id: str,
    current_user: CurrentUser,
    db: DbSession,
    revision_id: Annotated[str | None, Query(alias="revisionId")] = None,
) -> ReadinessResponse:
    try:
        project = require_project_access(db, project_id, current_user.id)
        selected_revision_id = revision_id or project.current_revision_id
        if selected_revision_id is None:
            raise RevisionNotFound("Project has no current revision.")
        revision = require_project_revision(db, project, selected_revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return calculate_readiness(revision.process_ir, revision.id)


@router.get("/{project_id}/agent-readiness", response_model=AgentReadinessResponse)
def get_agent_readiness(
    project_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> AgentReadinessResponse:
    try:
        project = require_project_access(db, project_id, current_user.id)
        if project.current_revision_id is None:
            raise RevisionNotFound("Project has no current revision.")
        revision = require_project_revision(db, project, project.current_revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return AgentReadinessResponse.model_validate(calculate_agent_readiness(revision.process_ir))


@router.patch("/{project_id}/target-mode", response_model=ProjectResponse)
def set_target_mode(
    project_id: str,
    request: ProjectTargetModeRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    try:
        project = require_project_access(db, project_id, current_user.id, for_update=True)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    project.target_mode = request.target_mode
    db.commit()
    db.refresh(project)
    return project_response(db, project)


@router.post("/{project_id}/archive", response_model=ProjectResponse)
def archive(project_id: str, current_user: CurrentUser, db: DbSession) -> ProjectResponse:
    try:
        project = archive_project(db, user=current_user, project_id=project_id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)


@router.get("/{project_id}/revisions", response_model=list[ProcessRevisionResponse])
def list_revisions(project_id: str, current_user: CurrentUser, db: DbSession) -> list[ProcessRevisionResponse]:
    try:
        require_project_access(db, project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return [revision_response(item) for item in list_project_revisions(db, project_id)]


@router.get("/{project_id}/revisions/diff", response_model=RevisionDiffResponse)
def revision_diff(
    project_id: str,
    current_user: CurrentUser,
    db: DbSession,
    from_revision_id: Annotated[str, Query(alias="fromRevisionId")],
    to_revision_id: Annotated[str, Query(alias="toRevisionId")],
) -> RevisionDiffResponse:
    try:
        project = require_project_access(db, project_id, current_user.id)
        from_revision = require_project_revision(db, project, from_revision_id)
        to_revision = require_project_revision(db, project, to_revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return RevisionDiffResponse(
        project_id=project.id,
        from_revision_id=from_revision.id,
        to_revision_id=to_revision.id,
        patch=jsonpatch.make_patch(from_revision.process_ir, to_revision.process_ir).patch,
    )


@router.post("/{project_id}/revisions", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def patch_project(
    project_id: str,
    request: ProjectPatchRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    try:
        project, _ = apply_process_patch(
            db,
            user=current_user,
            project_id=project_id,
            base_revision_id=request.base_revision_id,
            patch=request.patch,
        )
    except (ProjectNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)


@router.post("/{project_id}/undo", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def undo(
    project_id: str,
    request: ProjectUndoRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    try:
        project, _ = undo_last_revision(
            db,
            user=current_user,
            project_id=project_id,
            base_revision_id=request.base_revision_id,
        )
    except (ProjectNotFound, RevisionConflict, RevisionNotUndoable, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return project_response(db, project)


@router.post("/{project_id}/restore", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def restore(
    project_id: str,
    request: ProjectRestoreRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProjectResponse:
    try:
        project, _ = restore_revision(
            db,
            user=current_user,
            project_id=project_id,
            base_revision_id=request.base_revision_id,
            target_revision_id=request.target_revision_id,
        )
    except (
        ProjectNotFound,
        RevisionNotFound,
        RevisionConflict,
        InvalidProcessPatch,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return project_response(db, project)
