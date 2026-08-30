from __future__ import annotations

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db_models import AgentBaselineDecision, AgentEvaluationRun, ProcessRevision, Project, User
from ..exporters.agents import build_agent_contract, build_evaluation_suite, calculate_agent_readiness


class AgentEvaluationConflict(RuntimeError):
    pass


def _fingerprint() -> str:
    settings = get_settings()
    value = f"deepseek:{settings.deepseek_model}".encode()
    return sha256(value).hexdigest()


def required_scenarios(revision: ProcessRevision) -> list[str]:
    contract = build_agent_contract(revision.process_ir)
    return [item["id"] for item in build_evaluation_suite(contract)["scenarios"]]


def create_evaluation(
    db: Session,
    project: Project,
    revision: ProcessRevision,
    user: User,
    runtime: str,
    results: list[dict],
    cost_microunits: int,
    duration_ms: int,
) -> AgentEvaluationRun:
    if project.target_mode != "agent":
        raise AgentEvaluationConflict("Project must be in Agent-ready mode.")
    required = required_scenarios(revision)
    submitted = [item["scenario_id"] for item in results]
    if len(submitted) != len(set(submitted)) or set(submitted) != set(required):
        raise AgentEvaluationConflict("Evaluation results must cover the exact current scenario suite once.")
    ordered = sorted(results, key=lambda item: required.index(item["scenario_id"]))
    passed_count = sum(bool(item["passed"]) for item in ordered)
    run = AgentEvaluationRun(
        project_id=project.id,
        revision_id=revision.id,
        runtime=runtime,
        suite_version="1",
        status="passed" if passed_count == len(ordered) else "failed",
        model_fingerprint=_fingerprint(),
        results=ordered,
        passed_count=passed_count,
        total_count=len(ordered),
        cost_microunits=cost_microunits,
        duration_ms=duration_ms,
        created_by_user_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def set_baseline(db: Session, project: Project, user: User, evaluation: AgentEvaluationRun, action: str, reason_code: str) -> AgentBaselineDecision:
    if evaluation.project_id != project.id or evaluation.status != "passed":
        raise AgentEvaluationConflict("Only a successful evaluation from this project can become the baseline.")
    decision = AgentBaselineDecision(
        project_id=project.id,
        evaluation_run_id=evaluation.id,
        runtime=evaluation.runtime,
        action=action,
        reason_code=reason_code,
        created_by_user_id=user.id,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def latest_evaluation(db: Session, project_id: str, revision_id: str, runtime: str) -> AgentEvaluationRun | None:
    return db.scalar(select(AgentEvaluationRun).where(
        AgentEvaluationRun.project_id == project_id,
        AgentEvaluationRun.revision_id == revision_id,
        AgentEvaluationRun.runtime == runtime,
    ).order_by(AgentEvaluationRun.created_at.desc(), AgentEvaluationRun.id.desc()))


def current_baseline(db: Session, project_id: str, runtime: str) -> tuple[AgentBaselineDecision, AgentEvaluationRun] | None:
    decision = db.scalar(select(AgentBaselineDecision).where(
        AgentBaselineDecision.project_id == project_id,
        AgentBaselineDecision.runtime == runtime,
    ).order_by(AgentBaselineDecision.created_at.desc(), AgentBaselineDecision.id.desc()))
    if not decision:
        return None
    evaluation = db.get(AgentEvaluationRun, decision.evaluation_run_id)
    return (decision, evaluation) if evaluation else None


def calculate_pilot_gate(db: Session, project: Project, revision: ProcessRevision, runtime: str) -> dict:
    readiness = calculate_agent_readiness(revision.process_ir)
    scenarios = required_scenarios(revision)
    latest = latest_evaluation(db, project.id, revision.id, runtime)
    baseline_pair = current_baseline(db, project.id, runtime)
    blockers = list(readiness["blockers"])
    status = "not_ready"
    if readiness["agentReady"]:
        if not latest:
            status, blockers = "evaluation_required", ["evaluation_required"]
        elif latest.status != "passed":
            status, blockers = "regression", ["evaluation_failed"]
        elif not baseline_pair:
            status, blockers = "approval_required", ["baseline_approval_required"]
        else:
            _, baseline_eval = baseline_pair
            if latest.model_fingerprint != baseline_eval.model_fingerprint:
                status, blockers = "model_change", ["model_change_review_required"]
            elif latest.id != baseline_eval.id and baseline_eval.cost_microunits > 0 and latest.cost_microunits > baseline_eval.cost_microunits * 1.25:
                status, blockers = "regression", ["evaluation_cost_regression"]
            elif latest.id != baseline_eval.id and baseline_eval.duration_ms > 0 and latest.duration_ms > baseline_eval.duration_ms * 1.25:
                status, blockers = "regression", ["evaluation_duration_regression"]
            elif latest.id != baseline_eval.id:
                status, blockers = "approval_required", ["baseline_approval_required"]
            else:
                status, blockers = "ready", []
    return {
        "scope": "agent_pilot",
        "runtime": runtime,
        "status": status,
        "pilot_ready": status == "ready",
        "blockers": blockers,
        "required_scenarios": scenarios,
        "latest_evaluation": latest,
        "baseline": baseline_pair[0] if baseline_pair else None,
    }
