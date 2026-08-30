from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import AgentIncident, AgentRun, ProcessRevision, Project, User


class AgentIncidentConflict(RuntimeError):
    pass


def record_incident(db: Session, run: AgentRun, category: str, reason_code: str) -> AgentIncident:
    existing = db.scalar(select(AgentIncident).where(AgentIncident.run_id == run.id))
    if existing:
        return existing
    incident = AgentIncident(project_id=run.project_id, run_id=run.id, category=category, reason_code=reason_code)
    db.add(incident)
    return incident


def resolve_incident(db: Session, incident: AgentIncident, user: User, resolution_code: str) -> AgentIncident:
    if incident.status != "open":
        raise AgentIncidentConflict("Only an open incident can be resolved.")
    incident.status = "resolved"
    incident.resolution_code = resolution_code
    incident.resolved_by_user_id = user.id
    incident.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return incident


def replay_incident(db: Session, incident: AgentIncident, project: Project, user: User, revision_choice: str, resolution_code: str, idempotency_key: str):
    if incident.status == "replayed" and incident.replay_run_id:
        replay = db.get(AgentRun, incident.replay_run_id)
        if replay and replay.idempotency_key == idempotency_key:
            from ..db_models import AgentDispatchJob
            job = db.scalar(select(AgentDispatchJob).where(AgentDispatchJob.run_id == replay.id))
            if job:
                return incident, replay, job
    if incident.status != "open":
        raise AgentIncidentConflict("Only an open incident can be replayed.")
    original = db.get(AgentRun, incident.run_id)
    if not original:
        raise AgentIncidentConflict("The incident source run no longer exists.")
    revision_id = original.revision_id if revision_choice == "original" else project.current_revision_id
    revision = db.get(ProcessRevision, revision_id)
    if not revision or revision.project_id != project.id:
        raise AgentIncidentConflict("The selected revision is unavailable.")
    conflicting_run = db.scalar(select(AgentRun).where(AgentRun.project_id == project.id, AgentRun.idempotency_key == idempotency_key))
    if conflicting_run:
        raise AgentIncidentConflict("The replay idempotency key is already used by another run.")
    from .agent_dispatch import AgentDispatchConflict, enqueue_agent_run

    try:
        run, job, _ = enqueue_agent_run(
            db, project, user, original.runtime, idempotency_key,
            {"max_steps": original.max_steps, "max_tool_calls": original.max_tool_calls, "timeout_seconds": original.timeout_seconds, "max_cost_microunits": original.max_cost_microunits},
            revision=revision, commit=False,
        )
    except AgentDispatchConflict as error:
        raise AgentIncidentConflict(str(error)) from error
    incident.status = "replayed"
    incident.resolution_code = resolution_code
    incident.replay_run_id = run.id
    incident.resolved_by_user_id = user.id
    incident.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return incident, run, job
