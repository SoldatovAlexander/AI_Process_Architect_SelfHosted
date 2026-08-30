from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import AdminAuditEvent, User


ROLE_PERMISSIONS = {
    "service_admin": {"admin.read", "users.manage", "commercial.manage", "audit.read"},
    "support": {"admin.read", "audit.read"},
    "billing_admin": {"admin.read", "commercial.manage", "audit.read"},
    "viewer": {"admin.read", "audit.read"},
    "user": set(),
}


class AdminAccessDenied(RuntimeError):
    pass


def require_admin_permission(user: User, permission: str) -> None:
    if permission not in ROLE_PERMISSIONS.get(user.service_role, set()):
        raise AdminAccessDenied(permission)


def bootstrap_service_admins(db: Session, settings: Settings) -> int:
    emails = settings.service_admin_email_set
    if not emails:
        return 0
    changed = 0
    for user in db.scalars(select(User).where(User.email.in_(emails))):
        if user.service_role != "service_admin":
            user.service_role = "service_admin"
            changed += 1
    if changed:
        db.commit()
    return changed


def add_admin_audit_event(
    db: Session,
    *,
    actor: User,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    details: dict,
    workspace_id: str | None = None,
) -> AdminAuditEvent:
    event = AdminAuditEvent(
        actor_user_id=actor.id,
        workspace_id=workspace_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        details=details,
    )
    db.add(event)
    return event
