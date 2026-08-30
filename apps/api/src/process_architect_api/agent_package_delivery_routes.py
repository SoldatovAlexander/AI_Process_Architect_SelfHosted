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
from .db_models import AgentPackageDelivery, RuntimeConnectionProfile
from .models import AgentPackageDeliveryCreateRequest, AgentPackageDeliveryPreviewRequest, AgentPackageDeliveryPreviewResponse, AgentPackageDeliveryResponse
from .services.agent_package_deliveries import AgentPackageDeliveryError, delete_stored_agent_package, prepare_agent_package_delivery, store_inactive_agent_package
from .services.projects import ProjectNotFound, RevisionNotFound, require_project_access, require_project_revision
from .services.workspaces import WorkspaceAccessDenied, require_membership
from .services.billing_usage import begin_metered_usage, finish_metered_usage
from .services.entitlements import EntitlementAccessError, require_boolean_entitlement


router = APIRouter(prefix="/api/v1", tags=["agent-package-deliveries"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _source(db: Session, project_id: str, revision_id: str, user: CurrentUser):
    try:
        project = require_project_access(db, project_id, user.id)
        membership = require_membership(db, project.workspace_id, user.id)
        revision = require_project_revision(db, project, revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "agent_delivery_source_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    if project.current_revision_id != revision.id:
        raise HTTPException(status_code=409, detail={"code": "revision_conflict", "currentRevisionId": project.current_revision_id})
    if project.status == "archived":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    if project.target_mode != "agent":
        raise HTTPException(status_code=409, detail={"code": "agent_mode_required"})
    return project, revision


def _profile(db: Session, profile_id: str, workspace_id: str, *, require_verified: bool = True) -> RuntimeConnectionProfile:
    profile = db.get(RuntimeConnectionProfile, profile_id)
    if profile is None or profile.workspace_id != workspace_id or profile.kind not in {"openclaw", "hermes"}:
        raise HTTPException(status_code=404, detail={"code": "agent_profile_not_found"})
    if require_verified and profile.status != "verified":
        raise HTTPException(status_code=409, detail={"code": "agent_profile_not_verified"})
    return profile


def _response(delivery: AgentPackageDelivery) -> AgentPackageDeliveryResponse:
    return AgentPackageDeliveryResponse.model_validate(delivery, from_attributes=True)


def _preview(db: Session, project_id: str, request: AgentPackageDeliveryPreviewRequest, user: CurrentUser):
    project, revision = _source(db, project_id, request.revision_id, user)
    profile = _profile(db, request.profile_id, project.workspace_id)
    try:
        prepared = prepare_agent_package_delivery(revision.process_ir, profile.kind, project.default_locale)
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail={"code": "agent_package_invalid", "message": str(error)}) from error
    return project, revision, profile, prepared


@router.post("/projects/{project_id}/agent-package-deliveries/preview", response_model=AgentPackageDeliveryPreviewResponse)
def preview_delivery(project_id: str, request: AgentPackageDeliveryPreviewRequest, current_user: CurrentUser, db: DbSession) -> AgentPackageDeliveryPreviewResponse:
    _, revision, profile, prepared = _preview(db, project_id, request, current_user)
    return AgentPackageDeliveryPreviewResponse(
        profile_id=profile.id,
        revision_id=revision.id,
        runtime=profile.kind,
        process_name=prepared.process_name,
        package_sha256=prepared.package_sha256,
        package_size=prepared.package_size,
        file_count=prepared.file_count,
        readiness_score=prepared.readiness_score,
        blocker_count=prepared.blocker_count,
        ready=prepared.ready,
    )


@router.get("/projects/{project_id}/agent-package-deliveries", response_model=list[AgentPackageDeliveryResponse])
def list_deliveries(project_id: str, current_user: CurrentUser, db: DbSession) -> list[AgentPackageDeliveryResponse]:
    try:
        project = require_project_access(db, project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"}) from error
    deliveries = db.scalars(select(AgentPackageDelivery).where(AgentPackageDelivery.project_id == project.id).order_by(AgentPackageDelivery.created_at.desc())).all()
    return [_response(item) for item in deliveries]


@router.post("/projects/{project_id}/agent-package-deliveries", response_model=AgentPackageDeliveryResponse, status_code=status.HTTP_201_CREATED)
async def create_delivery(
    project_id: str,
    request: AgentPackageDeliveryCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> AgentPackageDeliveryResponse:
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
    if request.expected_package_sha256 != prepared.package_sha256:
        raise HTTPException(status_code=409, detail={"code": "agent_delivery_preview_stale"})
    if not prepared.ready:
        raise HTTPException(status_code=409, detail={"code": "agent_package_not_ready"})

    same_key = db.scalar(select(AgentPackageDelivery).where(AgentPackageDelivery.profile_id == profile.id, AgentPackageDelivery.idempotency_key == request.idempotency_key))
    if same_key is not None:
        if same_key.project_id != project.id or same_key.revision_id != revision.id or same_key.package_sha256 != prepared.package_sha256:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        return _response(same_key)
    existing = db.scalar(select(AgentPackageDelivery).where(AgentPackageDelivery.profile_id == profile.id, AgentPackageDelivery.revision_id == revision.id, AgentPackageDelivery.package_sha256 == prepared.package_sha256, AgentPackageDelivery.status == "stored").limit(1))
    if existing is not None:
        return _response(existing)

    usage_meter = begin_metered_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        metric="runtime_publish",
        operation=f"runtime-publish.{profile.kind}",
        request_key=request.idempotency_key,
    )

    delivery = AgentPackageDelivery(
        project_id=project.id,
        revision_id=revision.id,
        profile_id=profile.id,
        runtime=profile.kind,
        idempotency_key=request.idempotency_key,
        package_sha256=prepared.package_sha256,
        package_size=prepared.package_size,
        file_count=prepared.file_count,
        status="storing",
        created_by_user_id=current_user.id,
    )
    db.add(delivery)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        finish_metered_usage(
            db, meter=usage_meter, outcome="released", reason_code="agent_delivery_conflict"
        )
        raise HTTPException(status_code=409, detail={"code": "agent_delivery_conflict"}) from error
    db.refresh(delivery)
    try:
        delivery.remote_package_id = await store_inactive_agent_package(profile, prepared, revision.id, request.idempotency_key)
    except AgentPackageDeliveryError as error:
        delivery.remote_package_id = error.remote_package_id
        delivery.status = "failed"
        delivery.last_error_code = error.code
        db.commit()
        finish_metered_usage(
            db, meter=usage_meter, outcome="released", reason_code="runtime_publish_failed"
        )
        raise HTTPException(status_code=502, detail={"code": error.code, "deliveryId": delivery.id}) from error
    delivery.status = "stored"
    delivery.stored_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(delivery)
    finish_metered_usage(
        db, meter=usage_meter, outcome="consumed", reason_code="runtime_publish_completed"
    )
    return _response(delivery)


@router.delete("/agent-package-deliveries/{delivery_id}", response_model=AgentPackageDeliveryResponse)
async def delete_delivery(delivery_id: str, current_user: CurrentUser, db: DbSession) -> AgentPackageDeliveryResponse:
    delivery = db.get(AgentPackageDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail={"code": "agent_delivery_not_found"})
    try:
        project = require_project_access(db, delivery.project_id, current_user.id)
        membership = require_membership(db, project.workspace_id, current_user.id)
        require_project_revision(db, project, delivery.revision_id)
    except (ProjectNotFound, RevisionNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "agent_delivery_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    if delivery.status == "deleted":
        return _response(delivery)
    if not delivery.remote_package_id:
        raise HTTPException(status_code=409, detail={"code": "agent_delivery_not_deletable"})
    profile = _profile(db, delivery.profile_id, project.workspace_id, require_verified=False)
    try:
        await delete_stored_agent_package(profile, delivery.remote_package_id)
    except AgentPackageDeliveryError as error:
        delivery.status = "deletion_failed"
        delivery.last_error_code = error.code
        db.commit()
        raise HTTPException(status_code=502, detail={"code": error.code, "deliveryId": delivery.id}) from error
    delivery.status = "deleted"
    delivery.last_error_code = None
    delivery.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(delivery)
    return _response(delivery)
