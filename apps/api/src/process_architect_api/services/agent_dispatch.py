from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db_models import AgentDispatchJob, AgentRun, AgentRunEvent, ProcessRevision, Project, User
from ..exporters.agents import build_agent_contract
from .agent_evaluations import calculate_pilot_gate
from .agent_runs import AgentRunConflict, append_event, create_agent_run


class AgentDispatchConflict(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_agent_run(db: Session, project: Project, user: User, runtime: str, idempotency_key: str, limits: dict, revision: ProcessRevision | None = None, *, commit: bool = True) -> tuple[AgentRun, AgentDispatchJob, bool]:
    revision = revision or db.get(ProcessRevision, project.current_revision_id)
    if not revision or not calculate_pilot_gate(db, project, revision, runtime)["pilot_ready"]:
        raise AgentDispatchConflict("Agent must pass the pilot gate before dispatch.")
    try:
        run, duplicate = create_agent_run(db, project, user, runtime, idempotency_key, limits, revision.id, commit=False)
    except AgentRunConflict as error:
        raise AgentDispatchConflict(str(error)) from error
    existing = db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == run.id))
    if existing:
        return run, existing, True
    job = AgentDispatchJob(run_id=run.id, status="queued", max_attempts=get_settings().agent_worker_max_attempts)
    db.add(job)
    append_event(db, run, "run_queued", "system")
    try:
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == run.id))
        if existing:
            return run, existing, True
        raise
    if commit:
        db.refresh(job)
        db.refresh(run)
    return run, job, duplicate


def claim_next_job(db: Session, worker_id: str, lease_seconds: int) -> AgentDispatchJob | None:
    now = _now()
    statement = select(AgentDispatchJob).join(AgentRun).where(
        AgentRun.status == "created",
        or_(
            (AgentDispatchJob.status.in_(["queued", "retry_wait"])) & (AgentDispatchJob.next_attempt_at <= now),
            (AgentDispatchJob.status == "leased") & (AgentDispatchJob.lease_expires_at < now),
        ),
    ).order_by(AgentDispatchJob.next_attempt_at, AgentDispatchJob.created_at).with_for_update(skip_locked=True).limit(1)
    job = db.scalar(statement)
    if not job:
        return None
    job.status = "leased"
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.attempt_count += 1
    job.last_error_code = None
    db.commit()
    db.refresh(job)
    return job


def dispatch_envelope(db: Session, job: AgentDispatchJob) -> tuple[AgentRun, dict[str, Any]]:
    run = db.get(AgentRun, job.run_id)
    revision = db.get(ProcessRevision, run.revision_id) if run else None
    if not run or not revision:
        raise AgentDispatchConflict("Dispatch job references missing run data.")
    contract = build_agent_contract(revision.process_ir)
    callback_base = get_settings().agent_runtime_callback_base_url.rstrip("/")
    return run, {
        "schema_version": "1",
        "run_id": run.id,
        "revision_id": run.revision_id,
        "idempotency_key": run.idempotency_key,
        "runtime": run.runtime,
        "contract": contract,
        "limits": {"max_steps": run.max_steps, "max_tool_calls": run.max_tool_calls, "timeout_seconds": run.timeout_seconds, "max_cost_microunits": run.max_cost_microunits},
        "callback_contract": {"url": f"{callback_base}/api/v1/runtime/agent-runs/{run.id}/callback" if callback_base else None, "statuses": ["awaiting_approval", "completed", "failed", "escalated"], "required_fields": ["callback_id", "status"], "content_allowed": False},
    }


def mark_dispatched(db: Session, job: AgentDispatchJob, run: AgentRun) -> None:
    now = _now()
    job.status = "dispatched"
    job.dispatched_at = now
    job.lease_owner = None
    job.lease_expires_at = None
    run.status = "running"
    run.started_at = run.started_at or now
    append_event(db, run, "run_dispatched", "system", reason_code=run.runtime)
    db.commit()


def mark_dispatch_failure(db: Session, job: AgentDispatchJob, run: AgentRun | None, error_code: str) -> None:
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error_code = error_code
    if job.attempt_count >= job.max_attempts:
        job.status = "dead_letter"
        if run and run.status == "created":
            run.status = "failed"
            run.ended_at = _now()
            append_event(db, run, "dispatch_dead_letter", "system", reason_code=error_code)
            from .agent_incidents import record_incident
            record_incident(db, run, "dispatch", error_code)
    else:
        job.status = "retry_wait"
        job.next_attempt_at = _now() + timedelta(seconds=min(300, 2 ** job.attempt_count))
        if run:
            append_event(db, run, "dispatch_retry_scheduled", "system", reason_code=error_code, metrics={"attempt": job.attempt_count})
    db.commit()


def cancel_dispatch(db: Session, job: AgentDispatchJob, run: AgentRun, user: User) -> None:
    if job.status in {"dispatched", "dead_letter", "cancelled"}:
        raise AgentDispatchConflict("Dispatch job can no longer be cancelled.")
    job.status = "cancelled"
    job.lease_owner = None
    job.lease_expires_at = None
    run.status = "cancelled"
    run.ended_at = _now()
    append_event(db, run, "dispatch_cancelled", "user", user.id)
    db.commit()


def apply_runtime_callback(db: Session, run: AgentRun, callback_id: str, status: str, reason_code: str | None, steps: int, tool_calls: int, cost_microunits: int) -> AgentRun:
    if db.scalar(select(AgentRunEvent).where(AgentRunEvent.run_id == run.id, AgentRunEvent.external_event_id == callback_id)):
        return run
    if run.status not in {"running", "awaiting_approval"}:
        raise AgentDispatchConflict("Runtime callback is not allowed for the current run state.")
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
    event = append_event(db, run, "runtime_callback", "agent", reason_code=reason_code, metrics={"steps": steps, "tool_calls": tool_calls, "cost_microunits": cost_microunits})
    event.external_event_id = callback_id
    if exceeded:
        run.status = "failed"
        run.ended_at = _now()
        append_event(db, run, "limit_exceeded", "system", reason_code="_and_".join(exceeded))
        from .agent_incidents import record_incident
        record_incident(db, run, "limit", "_and_".join(exceeded))
    else:
        run.status = status
        if status in {"completed", "failed", "escalated"}:
            run.ended_at = _now()
        if status in {"failed", "escalated"}:
            from .agent_incidents import record_incident
            record_incident(db, run, "runtime" if status == "failed" else "escalation", reason_code or status)
    db.commit()
    db.refresh(run)
    return run
