from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db_models import AgentPackageDelivery, AgentRun, LLMUsageRecord, N8nPublication, ProcessRevision, Project, Workspace
from ..readiness import calculate_readiness


@dataclass(frozen=True)
class ActivityMetrics:
    workflows_created: int = 0
    workflows_ready: int = 0
    workflows_in_progress: int = 0
    n8n_publications: int = 0
    agent_deliveries: int = 0
    agent_runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_picousd: int = 0
    unpriced_llm_records: int = 0

    def payload(self) -> dict:
        result = asdict(self)
        result["total_tokens"] = self.input_tokens + self.output_tokens
        return {_camel_case(key): value for key, value in result.items()}


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.title() for part in tail)


def current_month(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    start = current.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def normalize_period(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    default_start, default_end = current_month()
    start = _aware(start or default_start)
    end = _aware(end or default_end)
    if end <= start:
        raise ValueError("report_period_invalid")
    if (end - start).days > 366:
        raise ValueError("report_period_too_long")
    return start, end


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


def workspace_activity(db: Session, workspace: Workspace, *, start: datetime, end: datetime) -> dict:
    projects = db.scalars(
        select(Project).where(Project.workspace_id == workspace.id, Project.created_at < end)
    ).all()
    workflows_ready = 0
    workflows_in_progress = 0
    for project in projects:
        if project.status == "archived":
            continue
        revision = db.scalar(
            select(ProcessRevision)
            .where(ProcessRevision.project_id == project.id, ProcessRevision.created_at < end)
            .order_by(ProcessRevision.version_number.desc())
            .limit(1)
        )
        if revision is not None and calculate_readiness(revision.process_ir, revision.id).draft_ready:
            workflows_ready += 1
        else:
            workflows_in_progress += 1

    llm = db.execute(
        select(
            func.coalesce(func.sum(LLMUsageRecord.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageRecord.output_tokens), 0),
            func.coalesce(func.sum(LLMUsageRecord.estimated_cost_picousd), 0),
            func.sum(case((LLMUsageRecord.estimated_cost_picousd.is_(None), 1), else_=0)),
        ).where(
            LLMUsageRecord.workspace_id == workspace.id,
            LLMUsageRecord.created_at >= start,
            LLMUsageRecord.created_at < end,
        )
    ).one()
    project_ids = [project.id for project in projects]
    metrics = ActivityMetrics(
        workflows_created=_count(db, select(func.count(Project.id)).where(
            Project.workspace_id == workspace.id, Project.created_at >= start, Project.created_at < end
        )),
        workflows_ready=workflows_ready,
        workflows_in_progress=workflows_in_progress,
        n8n_publications=0 if not project_ids else _count(db, select(func.count(N8nPublication.id)).where(
            N8nPublication.project_id.in_(project_ids), N8nPublication.published_at >= start, N8nPublication.published_at < end
        )),
        agent_deliveries=0 if not project_ids else _count(db, select(func.count(AgentPackageDelivery.id)).where(
            AgentPackageDelivery.project_id.in_(project_ids), AgentPackageDelivery.stored_at >= start, AgentPackageDelivery.stored_at < end
        )),
        agent_runs=0 if not project_ids else _count(db, select(func.count(AgentRun.id)).where(
            AgentRun.project_id.in_(project_ids), AgentRun.created_at >= start, AgentRun.created_at < end
        )),
        input_tokens=int(llm[0] or 0),
        output_tokens=int(llm[1] or 0),
        estimated_cost_picousd=int(llm[2] or 0),
        unpriced_llm_records=int(llm[3] or 0),
    )
    return {"workspaceId": workspace.id, "workspaceName": workspace.name, **metrics.payload()}


def activity_report(
    db: Session,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    workspace_id: str | None = None,
) -> dict:
    start, end = normalize_period(start, end)
    query = select(Workspace).where(Workspace.archived_at.is_(None)).order_by(Workspace.name, Workspace.id)
    if workspace_id is not None:
        query = query.where(Workspace.id == workspace_id)
    rows = [workspace_activity(db, workspace, start=start, end=end) for workspace in db.scalars(query).all()]
    metric_keys = list(ActivityMetrics().payload())
    summary = {key: sum(int(row[key]) for row in rows) for key in metric_keys}
    return {
        "periodStart": start,
        "periodEnd": end,
        "generatedAt": datetime.now(timezone.utc),
        "summary": summary,
        "workspaces": rows,
    }
