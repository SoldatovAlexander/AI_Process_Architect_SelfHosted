from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import AgentRun, AgentRunEvent, Project, User
from ..config import get_settings
from .billing_usage import begin_metered_usage, finish_metered_usage


TERMINAL = {"completed", "failed", "escalated", "cancelled"}
TRANSITIONS = {
    ("created", "start"): "running", ("created", "cancel"): "cancelled",
    ("running", "request_approval"): "awaiting_approval", ("running", "complete"): "completed",
    ("running", "fail"): "failed", ("running", "escalate"): "escalated", ("running", "cancel"): "cancelled",
    ("awaiting_approval", "approve"): "running", ("awaiting_approval", "fail"): "failed",
    ("awaiting_approval", "escalate"): "escalated", ("awaiting_approval", "cancel"): "cancelled",
}


class AgentRunConflict(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timeout_expired(db: Session, run: AgentRun) -> bool:
    if run.status != "running" or not run.started_at:
        return False
    started_at = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
    if _now() <= started_at + timedelta(seconds=run.timeout_seconds):
        return False
    run.status = "failed"
    run.ended_at = _now()
    append_event(db, run, "timeout_exceeded", "system", reason_code="timeout")
    from .agent_incidents import record_incident
    record_incident(db, run, "timeout", "timeout")
    db.commit()
    db.refresh(run)
    return True


def enforce_timeout(db: Session, run: AgentRun) -> AgentRun:
    _timeout_expired(db, run)
    return run


def append_event(db: Session, run: AgentRun, event_type: str, actor_type: str, user_id: str | None = None, reason_code: str | None = None, metrics: dict | None = None) -> AgentRunEvent:
    sequence = db.scalar(select(func.coalesce(func.max(AgentRunEvent.sequence), 0)).where(AgentRunEvent.run_id == run.id)) + 1
    event = AgentRunEvent(run_id=run.id, sequence=sequence, event_type=event_type, actor_type=actor_type, reason_code=reason_code, metrics=metrics or {}, created_by_user_id=user_id)
    db.add(event)
    return event


def create_agent_run(db: Session, project: Project, user: User, runtime: str, idempotency_key: str, limits: dict, revision_id: str | None = None, *, commit: bool = True) -> tuple[AgentRun, bool]:
    existing = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id, AgentRun.idempotency_key == idempotency_key))
    if existing:
        return existing, True
    if project.target_mode != "agent" or not project.current_revision_id:
        raise AgentRunConflict("Project must be in Agent-ready mode with a current revision.")
    usage_meter = begin_metered_usage(
        db,
        workspace_id=project.workspace_id,
        settings=get_settings(),
        metric="agent_run",
        operation=f"agent-run.{project.id}.{runtime}",
        request_key=idempotency_key,
        commit=False,
    )
    run = AgentRun(project_id=project.id, revision_id=revision_id or project.current_revision_id, runtime=runtime, status="created", contract_version="1.1", idempotency_key=idempotency_key, created_by_user_id=user.id, **limits)
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id, AgentRun.idempotency_key == idempotency_key))
        if existing:
            return existing, True
        raise
    append_event(db, run, "run_created", "user", user.id, metrics={"max_steps": run.max_steps, "max_tool_calls": run.max_tool_calls, "timeout_seconds": run.timeout_seconds, "max_cost_microunits": run.max_cost_microunits})
    finish_metered_usage(
        db,
        meter=usage_meter,
        outcome="consumed",
        reason_code="agent_run_created",
        commit=False,
    )
    if commit:
        db.commit()
        db.refresh(run)
    else:
        db.flush()
    return run, False


def transition_agent_run(db: Session, run: AgentRun, user: User, action: str, reason_code: str | None) -> AgentRun:
    if _timeout_expired(db, run):
        return run
    next_status = TRANSITIONS.get((run.status, action))
    if not next_status:
        raise AgentRunConflict(f"Action {action} is not allowed from status {run.status}.")
    now = _now()
    run.status = next_status
    if action == "start" and run.started_at is None:
        run.started_at = now
    if next_status in TERMINAL:
        run.ended_at = now
    append_event(db, run, f"run_{action}", "user", user.id, reason_code=reason_code)
    if next_status in {"failed", "escalated"}:
        from .agent_incidents import record_incident
        record_incident(db, run, "runtime" if next_status == "failed" else "escalation", reason_code or next_status)
    db.commit()
    db.refresh(run)
    return run


def record_usage(db: Session, run: AgentRun, steps: int, tool_calls: int, cost_microunits: int) -> AgentRun:
    if _timeout_expired(db, run):
        return run
    if run.status != "running":
        raise AgentRunConflict("Usage can only be recorded for a running agent run.")
    run.steps_used += steps
    run.tool_calls_used += tool_calls
    run.cost_microunits += cost_microunits
    exceeded = []
    if run.steps_used > run.max_steps:
        exceeded.append("steps")
    if run.tool_calls_used > run.max_tool_calls:
        exceeded.append("tool_calls")
    if run.max_cost_microunits and run.cost_microunits > run.max_cost_microunits:
        exceeded.append("cost")
    append_event(db, run, "usage_recorded", "system", metrics={"steps": steps, "tool_calls": tool_calls, "cost_microunits": cost_microunits})
    if exceeded:
        run.status = "failed"
        run.ended_at = _now()
        append_event(db, run, "limit_exceeded", "system", reason_code="_and_".join(exceeded))
    db.commit()
    db.refresh(run)
    return run
