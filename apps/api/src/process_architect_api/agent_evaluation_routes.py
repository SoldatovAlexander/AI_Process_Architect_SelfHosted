from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .db_models import AgentBaselineDecision, AgentEvaluationRun, ProcessRevision
from .models import AgentBaselineDecisionResponse, AgentBaselineRequest, AgentEvaluationCreateRequest, AgentEvaluationRunResponse, AgentPilotGateResponse
from .services.agent_evaluations import AgentEvaluationConflict, calculate_pilot_gate, create_evaluation, set_baseline
from .services.projects import ProjectNotFound, require_project_access
from .services.workspaces import WorkspaceAccessDenied


router = APIRouter(prefix="/api/v1", tags=["agent-evaluations"])
DbSession = Annotated[Session, Depends(get_db)]


def _project(project_id: str, user: CurrentUser, db: Session):
    try:
        return require_project_access(db, project_id, user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise HTTPException(status_code=404, detail={"code": "project_not_found", "message": str(error)}) from error


def _evaluation_response(item: AgentEvaluationRun | None) -> AgentEvaluationRunResponse | None:
    if not item:
        return None
    return AgentEvaluationRunResponse(
        id=item.id, project_id=item.project_id, revision_id=item.revision_id, runtime=item.runtime,
        suite_version=item.suite_version, status=item.status, results=item.results,
        passed_count=item.passed_count, total_count=item.total_count,
        cost_microunits=item.cost_microunits, duration_ms=item.duration_ms, created_at=item.created_at,
    )


def _baseline_response(item: AgentBaselineDecision | None) -> AgentBaselineDecisionResponse | None:
    if not item:
        return None
    return AgentBaselineDecisionResponse(id=item.id, evaluation_run_id=item.evaluation_run_id, runtime=item.runtime, action=item.action, reason_code=item.reason_code, created_at=item.created_at)


@router.get("/projects/{project_id}/agent-pilot-gate", response_model=AgentPilotGateResponse)
def pilot_gate(project_id: str, current_user: CurrentUser, db: DbSession, runtime: Annotated[Literal["openclaw", "hermes"], Query()] = "openclaw") -> AgentPilotGateResponse:
    project = _project(project_id, current_user, db)
    revision = db.get(ProcessRevision, project.current_revision_id)
    if not revision:
        raise HTTPException(status_code=409, detail={"code": "project_has_no_revision"})
    result = calculate_pilot_gate(db, project, revision, runtime)
    result["latest_evaluation"] = _evaluation_response(result["latest_evaluation"])
    result["baseline"] = _baseline_response(result["baseline"])
    return AgentPilotGateResponse(**result)


@router.get("/projects/{project_id}/agent-evaluations", response_model=list[AgentEvaluationRunResponse])
def evaluations(project_id: str, current_user: CurrentUser, db: DbSession) -> list[AgentEvaluationRunResponse]:
    _project(project_id, current_user, db)
    items = db.scalars(select(AgentEvaluationRun).where(AgentEvaluationRun.project_id == project_id).order_by(AgentEvaluationRun.created_at.desc(), AgentEvaluationRun.id.desc())).all()
    return [_evaluation_response(item) for item in items]


@router.post("/projects/{project_id}/agent-evaluations", response_model=AgentEvaluationRunResponse, status_code=status.HTTP_201_CREATED)
def add_evaluation(project_id: str, request: AgentEvaluationCreateRequest, current_user: CurrentUser, db: DbSession) -> AgentEvaluationRunResponse:
    project = _project(project_id, current_user, db)
    revision = db.get(ProcessRevision, project.current_revision_id)
    if not revision:
        raise HTTPException(status_code=409, detail={"code": "project_has_no_revision"})
    try:
        item = create_evaluation(db, project, revision, current_user, request.runtime, [result.model_dump() for result in request.results], request.cost_microunits, request.duration_ms)
    except AgentEvaluationConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_evaluation_conflict", "message": str(error)}) from error
    return _evaluation_response(item)


@router.post("/projects/{project_id}/agent-baselines", response_model=AgentBaselineDecisionResponse, status_code=status.HTTP_201_CREATED)
def baseline(project_id: str, request: AgentBaselineRequest, current_user: CurrentUser, db: DbSession) -> AgentBaselineDecisionResponse:
    project = _project(project_id, current_user, db)
    evaluation = db.get(AgentEvaluationRun, request.evaluation_run_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail={"code": "agent_evaluation_not_found"})
    try:
        decision = set_baseline(db, project, current_user, evaluation, request.action, request.reason_code)
    except AgentEvaluationConflict as error:
        raise HTTPException(status_code=409, detail={"code": "agent_baseline_conflict", "message": str(error)}) from error
    return _baseline_response(decision)
