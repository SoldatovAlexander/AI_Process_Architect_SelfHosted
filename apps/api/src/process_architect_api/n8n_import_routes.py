from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .entitlement_dependencies import N8nExportEntitlement
from .db_models import N8nImportArtifact
from .exporters import generate_n8n_roundtrip_package
from .exporters.n8n import SUPPORTED_TARGETS
from .models import N8nImportArtifactResponse, N8nImportRequest, N8nImportResponse, N8nRoundtripRequest
from .n8n_importer import InvalidN8nWorkflow, import_n8n_workflow
from .n8n_roundtrip import build_roundtrip_workflow
from .project_routes import project_response
from .services.projects import InvalidInitialProcess, create_project_with_initial_revision
from .services.projects import ProjectNotFound, RevisionNotFound, require_project_access, require_project_revision
from .services.workspaces import WorkspaceAccessDenied
from .services.billing_usage import metered_operation


router = APIRouter(prefix="/api/v1/n8n-imports", tags=["n8n-imports"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]
IdempotencyHeader = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=128)]


@router.post("", response_model=N8nImportResponse, status_code=status.HTTP_201_CREATED)
def import_workflow(request: N8nImportRequest, current_user: CurrentUser, db: DbSession) -> N8nImportResponse:
    try:
        process_ir, diagnostics, source_minor, source_sha = import_n8n_workflow(
            request.workflow,
            request.locale,
            request.source_minor,
        )
        project, revision = create_project_with_initial_revision(
            db,
            user=current_user,
            workspace_id=request.workspace_id,
            name=process_ir["process"]["name"],
            process_ir=process_ir,
            default_locale=request.locale,
            source="import",
            perspective="as_is",
            commit=False,
        )
    except InvalidN8nWorkflow as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_n8n_workflow", "message": str(error)}) from error
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=403, detail={"code": "workspace_access_denied", "message": str(error)}) from error
    except InvalidInitialProcess as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_imported_process", "message": str(error)}) from error
    artifact = N8nImportArtifact(
        project_id=project.id,
        revision_id=revision.id,
        source_minor=source_minor,
        workflow_name=process_ir["process"]["name"],
        source_sha256=source_sha,
        source_workflow=request.workflow,
        diagnostics=diagnostics,
        created_by_user_id=current_user.id,
    )
    try:
        db.add(artifact)
        db.commit()
        db.refresh(project)
        db.refresh(revision)
        db.refresh(artifact)
    except Exception:
        db.rollback()
        raise
    return N8nImportResponse(
        project=project_response(db, project),
        artifact_id=artifact.id,
        source_minor=source_minor,
        source_sha256=source_sha,
        diagnostics=diagnostics,
    )


@router.get("/{artifact_id}", response_model=N8nImportArtifactResponse)
def get_import_artifact(artifact_id: str, current_user: CurrentUser, db: DbSession) -> N8nImportArtifactResponse:
    artifact = db.get(N8nImportArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail={"code": "import_artifact_not_found", "message": "Import artifact does not exist."})
    try:
        require_project_access(db, artifact.project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "import_artifact_not_found", "message": str(error)}) from error
    return N8nImportArtifactResponse.model_validate(artifact, from_attributes=True)


@router.post("/projects/{project_id}/round-trip/{target_minor}/package")
def export_roundtrip_package(
    project_id: str,
    target_minor: str,
    request: N8nRoundtripRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    entitlement: N8nExportEntitlement,
    idempotency_key: IdempotencyHeader = None,
) -> Response:
    if target_minor not in SUPPORTED_TARGETS:
        raise HTTPException(status_code=404, detail={"code": "unsupported_n8n_target", "supported": SUPPORTED_TARGETS})
    try:
        project = require_project_access(db, project_id, current_user.id)
        revision = require_project_revision(db, project, request.revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "round_trip_source_not_found", "message": str(error)}) from error
    if project.current_revision_id != revision.id:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "message": "Export the current project revision."})
    artifact = db.scalar(
        select(N8nImportArtifact)
        .where(N8nImportArtifact.project_id == project.id)
        .order_by(N8nImportArtifact.created_at)
        .limit(1)
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail={"code": "round_trip_source_not_found", "message": "Project has no imported n8n source artifact."})
    workflow, report = build_roundtrip_workflow(
        revision.process_ir,
        source_workflow=artifact.source_workflow,
        source_minor=artifact.source_minor,
        target_minor=target_minor,
        locale=request.locale,
        perspective=revision.perspective,
    )
    with metered_operation(
        db,
        workspace_id=entitlement.workspace_id,
        settings=settings,
        metric="export",
        operation=f"export.n8n-roundtrip.{target_minor}",
        request_key=idempotency_key or f"server:{uuid4()}",
    ):
        content = generate_n8n_roundtrip_package(
            revision.process_ir,
            workflow,
            report,
            target_minor,
            request.locale,
            request.include_general_guide,
        )
    process_id = revision.process_ir["process"]["id"]
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{process_id}-n8n-{target_minor}-round-trip.zip"'},
    )
