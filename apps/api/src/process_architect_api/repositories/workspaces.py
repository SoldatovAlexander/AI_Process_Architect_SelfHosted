from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db_models import Membership, Workspace


def find_membership(db: Session, workspace_id: str, user_id: str) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )


def list_user_workspaces(db: Session, user_id: str) -> list[Workspace]:
    return list(
        db.scalars(
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
            .order_by(Workspace.created_at)
        )
    )
