from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db_models import RefreshSession, User, Workspace


TEST_EMAIL_PREFIXES = ("e2e-", "playwright-", "opencode-")
SAFE_ENVIRONMENTS = {"development", "test", "e2e"}


def test_user_query():
    return select(User).where(or_(*(User.email.ilike(f"{prefix}%") for prefix in TEST_EMAIL_PREFIXES)))


def preview_e2e_cleanup(db: Session) -> dict:
    users = db.scalars(test_user_query().order_by(User.created_at)).all()
    user_ids = [user.id for user in users]
    workspaces = [] if not user_ids else db.scalars(
        select(Workspace).where(Workspace.created_by_user_id.in_(user_ids), Workspace.archived_at.is_(None))
    ).all()
    sessions = 0 if not user_ids else db.scalar(
        select(func.count(RefreshSession.id)).where(RefreshSession.user_id.in_(user_ids), RefreshSession.revoked_at.is_(None))
    ) or 0
    return {
        "matched_users": len(users),
        "active_workspaces": len(workspaces),
        "active_sessions": sessions,
        "users": [{"id": user.id, "email": user.email} for user in users],
    }


def apply_e2e_cleanup(db: Session) -> dict:
    preview = preview_e2e_cleanup(db)
    users = db.scalars(test_user_query()).all()
    user_ids = [user.id for user in users]
    if not user_ids:
        return preview | {"archived_workspaces": 0, "revoked_sessions": 0, "disabled_users": 0}

    now = datetime.now(timezone.utc)
    workspaces = db.scalars(
        select(Workspace).where(Workspace.created_by_user_id.in_(user_ids), Workspace.archived_at.is_(None))
    ).all()
    for workspace in workspaces:
        workspace.archived_at = now
        workspace.archived_by_user_id = None

    sessions = db.scalars(
        select(RefreshSession).where(RefreshSession.user_id.in_(user_ids), RefreshSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = now

    for user in users:
        user.is_active = False
        user.active_workspace_id = None

    db.commit()
    return preview | {
        "archived_workspaces": len(workspaces),
        "revoked_sessions": len(sessions),
        "disabled_users": len(users),
    }
