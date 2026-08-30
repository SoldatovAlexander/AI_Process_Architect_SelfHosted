from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .entitlement_dependencies import entitlement_http_exception
from .db_models import N8nPublication, RuntimeConnectionProfile
from .models import N8nPublicationCreateRequest, N8nPublicationPreviewRequest, N8nPublicationPreviewResponse, N8nPublicationResponse
from .services.n8n_publications import N8nPublicationError, delete_inactive_workflow, prepare_n8n_publication, publish_inactive_workflow
from .services.billing_usage import begin_metered_usage, finish_metered_usage
from .services.projects import ProjectNotFound, RevisionNotFound, require_project_access, require_project_revision
from .services.workspaces import WorkspaceAccessDenied, require_membership
from .services.entitlements import EntitlementAccessError, require_boolean_entitlement


router = APIRouter(prefix="/api/v1", tags=["n8n-publications"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _project_and_revision(db: Session, project_id: str, revision_id: str, user: CurrentUser):
    try:
        project = require_project_access(db, project_id, user.id)
        membership = require_membership(db, project.workspace_id, user.id)
        revision = require_project_revision(db, project, revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "publication_source_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    if project.current_revision_id != revision.id:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "currentRevisionId": project.current_revision_id})
    if project.status == "archived":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    return project, revision


def _n8n_profile(db: Session, profile_id: str, workspace_id: str, *, require_verified: bool = True) -> RuntimeConnectionProfile:
    profile = db.get(RuntimeConnectionProfile, profile_id)
    if profile is None or profile.workspace_id != workspace_id or profile.kind != "n8n":
        raise HTTPException(status_code=404, detail={"code": "n8n_profile_not_found"})
    if require_verified and profile.status != "verified":
        raise HTTPException(status_code=409, detail={"code": "n8n_profile_not_verified"})
    return profile


def _response(publication: N8nPublication) -> N8nPublicationResponse:
    return N8nPublicationResponse.model_validate(publication, from_attributes=True)


def _preview(db: Session, project_id: str, request: N8nPublicationPreviewRequest, user: CurrentUser):
    project, revision = _project_and_revision(db, project_id, request.revision_id, user)
    profile = _n8n_profile(db, request.profile_id, project.workspace_id)
    try:
        prepared = prepare_n8n_publication(db, project, revision, profile)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail={"code": "n8n_workflow_invalid", "message": str(error)}) from error
    return project, revision, profile, prepared


@router.post("/projects/{project_id}/n8n-publications/preview", response_model=N8nPublicationPreviewResponse)
def preview_publication(project_id: str, request: N8nPublicationPreviewRequest, current_user: CurrentUser, db: DbSession) -> N8nPublicationPreviewResponse:
    _, revision, profile, prepared = _preview(db, project_id, request, current_user)
    return N8nPublicationPreviewResponse(
        profile_id=profile.id,
        revision_id=revision.id,
        target_minor=profile.n8n_minor,
        workflow_name=prepared.payload["name"],
        workflow_sha256=prepared.workflow_sha256,
        node_count=prepared.node_count,
        connection_count=prepared.connection_count,
        source_mode=prepared.source_mode,
    )


@router.get("/projects/{project_id}/n8n-publications", response_model=list[N8nPublicationResponse])
def list_publications(project_id: str, current_user: CurrentUser, db: DbSession) -> list[N8nPublicationResponse]:
    try:
        project = require_project_access(db, project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"}) from error
    publications = db.scalars(select(N8nPublication).where(N8nPublication.project_id == project.id).order_by(N8nPublication.created_at.desc())).all()
    return [_response(item) for item in publications]


@router.post("/projects/{project_id}/n8n-publications", response_model=N8nPublicationResponse, status_code=status.HTTP_201_CREATED)
async def create_publication(
    project_id: str,
    request: N8nPublicationCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> N8nPublicationResponse:
    project, revision, profile, prepared = _preview(db, project_id, request, current_user)
    try:
        require_boolean_entitlement(
            db,
            user=current_user,
            settings=settings,
            entitlement_id="runtime.publish",
            workspace_id=project.workspace_id,
        )
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    if request.expected_workflow_sha256 != prepared.workflow_sha256:
        raise HTTPException(status_code=409, detail={"code": "publication_preview_stale"})

    same_key = db.scalar(select(N8nPublication).where(N8nPublication.profile_id == profile.id, N8nPublication.idempotency_key == request.idempotency_key))
    if same_key is not None:
        if same_key.project_id != project.id or same_key.revision_id != revision.id or same_key.workflow_sha256 != prepared.workflow_sha256:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        return _response(same_key)
    existing = db.scalar(select(N8nPublication).where(N8nPublication.profile_id == profile.id, N8nPublication.revision_id == revision.id, N8nPublication.workflow_sha256 == prepared.workflow_sha256, N8nPublication.status == "published").limit(1))
    if existing is not None:
        return _response(existing)

    usage_meter = begin_metered_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        metric="runtime_publish",
        operation="runtime-publish.n8n",
        request_key=request.idempotency_key,
    )

    publication = N8nPublication(
        project_id=project.id,
        revision_id=revision.id,
        profile_id=profile.id,
        idempotency_key=request.idempotency_key,
        workflow_sha256=prepared.workflow_sha256,
        status="publishing",
        created_by_user_id=current_user.id,
    )
    db.add(publication)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        finish_metered_usage(
            db, meter=usage_meter, outcome="released", reason_code="publication_conflict"
        )
        raise HTTPException(status_code=409, detail={"code": "publication_conflict"}) from error
    db.refresh(publication)
    try:
        publication.remote_workflow_id = await publish_inactive_workflow(profile, prepared)
    except N8nPublicationError as error:
        publication.remote_workflow_id = error.remote_workflow_id
        publication.status = "failed"
        publication.last_error_code = error.code
        db.commit()
        finish_metered_usage(
            db, meter=usage_meter, outcome="released", reason_code="runtime_publish_failed"
        )
        raise HTTPException(status_code=502, detail={"code": error.code, "publicationId": publication.id}) from error
    publication.status = "published"
    publication.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(publication)
    finish_metered_usage(
        db, meter=usage_meter, outcome="consumed", reason_code="runtime_publish_completed"
    )
    return _response(publication)


@router.delete("/n8n-publications/{publication_id}", response_model=N8nPublicationResponse)
async def delete_publication(publication_id: str, current_user: CurrentUser, db: DbSession) -> N8nPublicationResponse:
    publication = db.get(N8nPublication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail={"code": "publication_not_found"})
    try:
        project = require_project_access(db, publication.project_id, current_user.id)
        membership = require_membership(db, project.workspace_id, current_user.id)
        require_project_revision(db, project, publication.revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "publication_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    if publication.status == "deleted":
        return _response(publication)
    if not publication.remote_workflow_id:
        raise HTTPException(status_code=409, detail={"code": "publication_not_deletable"})
    profile = _n8n_profile(db, publication.profile_id, project.workspace_id, require_verified=False)
    try:
        await delete_inactive_workflow(profile, publication.remote_workflow_id)
    except N8nPublicationError as error:
        publication.status = "deletion_failed"
        publication.last_error_code = error.code
        db.commit()
        raise HTTPException(status_code=502, detail={"code": error.code, "publicationId": publication.id}) from error
    publication.status = "deleted"
    publication.last_error_code = None
    publication.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(publication)
    return _response(publication)
