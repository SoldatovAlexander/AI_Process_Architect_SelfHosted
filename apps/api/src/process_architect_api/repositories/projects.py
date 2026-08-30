from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import Membership, ProcessRevision, Project, Workspace


def find_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def lock_project(db: Session, project_id: str) -> Project | None:
    return db.scalar(
        select(Project).where(Project.id == project_id).with_for_update()
    )


def list_user_projects(
    db: Session,
    user_id: str,
    workspace_id: str | None = None,
) -> list[Project]:
    statement = (
        select(Project)
        .join(Membership, Membership.workspace_id == Project.workspace_id)
        .join(Workspace, Workspace.id == Project.workspace_id)
        .where(Membership.user_id == user_id)
        .where(Workspace.archived_at.is_(None))
        .order_by(Project.updated_at.desc(), Project.created_at.desc())
    )
    if workspace_id is not None:
        statement = statement.where(Project.workspace_id == workspace_id)
    return list(db.scalars(statement))


def find_revision(db: Session, revision_id: str) -> ProcessRevision | None:
    return db.get(ProcessRevision, revision_id)


def list_project_revisions(db: Session, project_id: str) -> list[ProcessRevision]:
    return list(
        db.scalars(
            select(ProcessRevision)
            .where(ProcessRevision.project_id == project_id)
            .order_by(ProcessRevision.version_number)
        )
    )
