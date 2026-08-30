import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_run_routes import _run_response
from .auth import CurrentUser
from .database import get_db
from .entitlement_dependencies import entitlement_http_exception
from .db_models import AgentDispatchJob, AgentIncident, AgentRun
from .config import get_settings
from .models import AgentDispatchJobResponse, AgentDispatchResponse, AgentIncidentReplayRequest, AgentIncidentReplayResponse, AgentIncidentResolveRequest, AgentIncidentResponse, AgentRunDispatchRequest, AgentRunResponse, AgentRuntimeCallbackRequest
from .services.agent_dispatch import AgentDispatchConflict, apply_runtime_callback, cancel_dispatch, enqueue_agent_run
from .services.agent_incidents import AgentIncidentConflict, replay_incident, resolve_incident
from .services.projects import ProjectNotFound, require_project_access
from .services.workspaces import WorkspaceAccessDenied
from .services.entitlements import EntitlementAccessError, require_boolean_entitlement


router = APIRouter(prefix="/api/v1", tags=["agent-dispatch"])
DbSession = Annotated[Session, Depends(get_db)]


def job_response(job: AgentDispatchJob) -> AgentDispatchJobResponse:
    return AgentDispatchJobResponse.model_validate(job, from_attributes=True)


def incident_response(incident: AgentIncident) -> AgentIncidentResponse:
    return AgentIncidentResponse.model_validate(incident, from_attributes=True)


def _project(project_id: str, user: CurrentUser, db: Session):
    try:
        return require_project_access(db, project_id, user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)}) from error


def _job(job_id: str, user: CurrentUser, db: Session, *, for_update: bool = False) -> tuple[AgentDispatchJob, AgentRun]:
    statement = select(AgentDispatchJob).where(AgentDispatchJob.id == job_id)
    job = db.scalar(statement.with_for_update()) if for_update else db.scalar(statement)
    run = db.get(AgentRun, job.run_id) if job else None
    if not job or not run:
        raise HTTPException(status_code=404, detail={"code": "agent_dispatch_not_found"})
    _project(run.project_id, user, db)
    return job, run


def _incident(incident_id: str, user: CurrentUser, db: Session, *, for_update: bool = False) -> AgentIncident:
    statement = select(AgentIncident).where(AgentIncident.id == incident_id)
    incident = db.scalar(statement.with_for_update()) if for_update else db.scalar(statement)
    if not incident:
        raise HTTPException(status_code=404, detail={"code": "agent_incident_not_found"})
    _project(incident.project_id, user, db)
    return incident


@router.post("/projects/{project_id}/agent-dispatches", response_model=AgentDispatchResponse)
def create_dispatch(project_id: str, request: AgentRunDispatchRequest, response: Response, current_user: CurrentUser, db: DbSession) -> AgentDispatchResponse:
    project = _project(project_id, current_user, db)
    try:
        require_boolean_entitlement(
            db,
            user=current_user,
            settings=get_settings(),
            entitlement_id="agent.execute",
            workspace_id=project.workspace_id,
        )
        run, job, duplicate = enqueue_agent_run(db, project, current_user, request.runtime, request.idempotency_key, request.limits.model_dump())
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except AgentDispatchConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_dispatch_blocked", "message": str(error)}) from error
    response.status_code = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return AgentDispatchResponse(run=_run_response(db, run), job=job_response(job))


@router.get("/agent-dispatches/{job_id}", response_model=AgentDispatchResponse)
def get_dispatch(job_id: str, current_user: CurrentUser, db: DbSession) -> AgentDispatchResponse:
    job, run = _job(job_id, current_user, db)
    return AgentDispatchResponse(run=_run_response(db, run), job=job_response(job))


@router.post("/agent-dispatches/{job_id}/cancel", response_model=AgentDispatchResponse)
def stop_dispatch(job_id: str, current_user: CurrentUser, db: DbSession) -> AgentDispatchResponse:
    job, run = _job(job_id, current_user, db, for_update=True)
    try:
        cancel_dispatch(db, job, run, current_user)
    except AgentDispatchConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_dispatch_conflict", "message": str(error)}) from error
    return AgentDispatchResponse(run=_run_response(db, run), job=job_response(job))


@router.get("/projects/{project_id}/agent-incidents", response_model=list[AgentIncidentResponse])
def list_incidents(project_id: str, current_user: CurrentUser, db: DbSession) -> list[AgentIncidentResponse]:
    _project(project_id, current_user, db)
    incidents = db.scalars(select(AgentIncident).where(AgentIncident.project_id == project_id).order_by(AgentIncident.created_at.desc())).all()
    return [incident_response(item) for item in incidents]


@router.post("/agent-incidents/{incident_id}/resolve", response_model=AgentIncidentResponse)
def close_incident(incident_id: str, request: AgentIncidentResolveRequest, current_user: CurrentUser, db: DbSession) -> AgentIncidentResponse:
    try:
        incident = resolve_incident(db, _incident(incident_id, current_user, db, for_update=True), current_user, request.resolution_code)
    except AgentIncidentConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_incident_conflict", "message": str(error)}) from error
    return incident_response(incident)


@router.post("/agent-incidents/{incident_id}/replay", response_model=AgentIncidentReplayResponse)
def replay_failed_run(incident_id: str, request: AgentIncidentReplayRequest, current_user: CurrentUser, db: DbSession) -> AgentIncidentReplayResponse:
    incident = _incident(incident_id, current_user, db, for_update=True)
    project = _project(incident.project_id, current_user, db)
    try:
        require_boolean_entitlement(
            db,
            user=current_user,
            settings=get_settings(),
            entitlement_id="agent.execute",
            workspace_id=project.workspace_id,
        )
        incident, run, job = replay_incident(db, incident, project, current_user, request.revision, request.resolution_code, request.idempotency_key)
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except AgentIncidentConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_incident_replay_blocked", "message": str(error)}) from error
    return AgentIncidentReplayResponse(incident=incident_response(incident), dispatch=AgentDispatchResponse(run=_run_response(db, run), job=job_response(job)))


@router.post("/runtime/agent-runs/{run_id}/callback", response_model=AgentRunResponse, include_in_schema=False)
def runtime_callback(run_id: str, request: AgentRuntimeCallbackRequest, db: DbSession, authorization: Annotated[str | None, Header()] = None) -> AgentRunResponse:
    configured = get_settings().agent_runtime_callback_token
    expected = configured.get_secret_value() if configured else ""
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail={"code": "runtime_callback_unauthorized"})
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
    if not run:
        raise HTTPException(status_code=404, detail={"code": "agent_run_not_found"})
    try:
        run = apply_runtime_callback(db, run, request.callback_id, request.status, request.reason_code, request.steps, request.tool_calls, request.cost_microunits)
    except AgentDispatchConflict as error:
        raise HTTPException(status_code=409, detail={"code": "runtime_callback_conflict", "message": str(error)}) from error
    return _run_response(db, run)
