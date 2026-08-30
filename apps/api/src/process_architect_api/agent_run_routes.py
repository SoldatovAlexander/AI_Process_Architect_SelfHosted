from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .entitlement_dependencies import entitlement_http_exception
from .db_models import AgentDispatchJob, AgentIncident, AgentRun, AgentRunEvent
from .models import AgentRunCreateRequest, AgentRunEventResponse, AgentRunResponse, AgentRunTransitionRequest, AgentRunUsageRequest
from .services.agent_runs import AgentRunConflict, create_agent_run, enforce_timeout, record_usage, transition_agent_run
from .services.projects import ProjectNotFound, require_project_access
from .services.workspaces import WorkspaceAccessDenied
from .services.entitlements import EntitlementAccessError, require_boolean_entitlement


router = APIRouter(prefix="/api/v1", tags=["agent-runs"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _run_response(db: Session, run: AgentRun) -> AgentRunResponse:
    run = enforce_timeout(db, run)
    events = list(db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == run.id).order_by(AgentRunEvent.sequence)))
    dispatch = db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == run.id))
    incident = db.scalar(select(AgentIncident).where(AgentIncident.run_id == run.id))
    return AgentRunResponse(
        id=run.id, project_id=run.project_id, revision_id=run.revision_id, runtime=run.runtime,
        status=run.status, contract_version=run.contract_version, idempotency_key=run.idempotency_key,
        limits={"max_steps": run.max_steps, "max_tool_calls": run.max_tool_calls, "timeout_seconds": run.timeout_seconds, "max_cost_microunits": run.max_cost_microunits},
        usage={"steps": run.steps_used, "tool_calls": run.tool_calls_used, "cost_microunits": run.cost_microunits},
        started_at=run.started_at, ended_at=run.ended_at, created_at=run.created_at, updated_at=run.updated_at,
        events=[AgentRunEventResponse(id=item.id, sequence=item.sequence, event_type=item.event_type, actor_type=item.actor_type, reason_code=item.reason_code, metrics=item.metrics, created_at=item.created_at) for item in events],
        dispatch_status=dispatch.status if dispatch else None, dispatch_attempts=dispatch.attempt_count if dispatch else 0,
        incident_id=incident.id if incident else None, incident_status=incident.status if incident else None,
        incident_category=incident.category if incident else None, incident_reason_code=incident.reason_code if incident else None,
        replay_run_id=incident.replay_run_id if incident else None,
    )


def _project(project_id: str, user: CurrentUser, db: Session):
    try:
        return require_project_access(db, project_id, user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)}) from error


def _run(run_id: str, user: CurrentUser, db: Session, *, for_update: bool = False) -> AgentRun:
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update()) if for_update else db.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "agent_run_not_found"})
    _project(run.project_id, user, db)
    return run


@router.post("/projects/{project_id}/agent-runs", response_model=AgentRunResponse)
def create_run(
    project_id: str,
    request: AgentRunCreateRequest,
    response: Response,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> AgentRunResponse:
    project = _project(project_id, current_user, db)
    try:
        require_boolean_entitlement(
            db,
            user=current_user,
            settings=settings,
            entitlement_id="agent.execute",
            workspace_id=project.workspace_id,
        )
        run, duplicate = create_agent_run(db, project, current_user, request.runtime, request.idempotency_key, request.limits.model_dump())
    except EntitlementAccessError as error:
        raise entitlement_http_exception(error) from error
    except AgentRunConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_run_conflict", "message": str(error)}) from error
    response.status_code = status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED
    return _run_response(db, run)


@router.get("/projects/{project_id}/agent-runs", response_model=list[AgentRunResponse])
def list_runs(project_id: str, current_user: CurrentUser, db: DbSession) -> list[AgentRunResponse]:
    _project(project_id, current_user, db)
    runs = db.scalars(select(AgentRun).where(AgentRun.project_id == project_id).order_by(AgentRun.created_at.desc())).all()
    return [_run_response(db, run) for run in runs]


@router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
def get_run(run_id: str, current_user: CurrentUser, db: DbSession) -> AgentRunResponse:
    return _run_response(db, _run(run_id, current_user, db))


@router.post("/agent-runs/{run_id}/transitions", response_model=AgentRunResponse)
def transition_run(run_id: str, request: AgentRunTransitionRequest, current_user: CurrentUser, db: DbSession) -> AgentRunResponse:
    run = _run(run_id, current_user, db, for_update=True)
    if db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == run.id)):
        raise HTTPException(status_code=409, detail={"code": "worker_managed_run", "message": "Worker-managed runs accept state changes only from the runtime callback."})
    try:
        run = transition_agent_run(db, run, current_user, request.action, request.reason_code)
    except AgentRunConflict as error:
        raise HTTPException(status_code=409, detail={"code": "invalid_agent_run_transition", "message": str(error)}) from error
    return _run_response(db, run)


@router.post("/agent-runs/{run_id}/usage", response_model=AgentRunResponse)
def add_usage(run_id: str, request: AgentRunUsageRequest, current_user: CurrentUser, db: DbSession) -> AgentRunResponse:
    run = _run(run_id, current_user, db, for_update=True)
    if db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == run.id)):
        raise HTTPException(status_code=409, detail={"code": "worker_managed_run", "message": "Worker-managed usage is accepted only through the runtime callback."})
    try:
        run = record_usage(db, run, request.steps, request.tool_calls, request.cost_microunits)
    except AgentRunConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_run_not_running", "message": str(error)}) from error
    return _run_response(db, run)
