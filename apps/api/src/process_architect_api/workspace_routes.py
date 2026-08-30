from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .db_models import AdminAuditEvent, Membership, User, Workspace, WorkspaceInvitation, utc_now
from .config import Settings, get_settings
from .localization import normalize_locale
from .services.administration import add_admin_audit_event
from .services.activity_reports import activity_report
from .services.entitlements import effective_workspace_entitlements
from .services.workspaces import WorkspaceAccessDenied, WorkspaceArchived, create_workspace, require_membership


router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class WorkspaceUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Workspace name cannot be blank.")
        return normalized


class WorkspaceCreateRequest(WorkspaceUpdateRequest):
    default_locale: str = Field(default="ru", min_length=2, max_length=35)

    @field_validator("default_locale")
    @classmethod
    def normalize_default_locale(cls, value: str) -> str:
        return normalize_locale(value)


class WorkspaceInvitationCreateRequest(BaseModel):
    email: EmailStr
    expires_in_days: int = Field(default=7, ge=1, le=30)


class WorkspaceInvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class WorkspaceMemberRoleRequest(BaseModel):
    role: str = Field(pattern="^(owner|member)$")


class WorkspaceOwnershipTransferRequest(BaseModel):
    target_user_id: str = Field(min_length=36, max_length=36)


def _workspace_membership_payload(workspace: Workspace, role: str = "owner") -> dict:
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "role": role,
        "default_locale": workspace.default_locale,
        "status": "archived" if workspace.archived_at is not None else "active",
        "archived_at": workspace.archived_at,
    }


def _require_owner(
    db: Session,
    workspace_id: str,
    user_id: str,
    *,
    allow_archived: bool = False,
) -> Membership:
    try:
        membership = require_membership(db, workspace_id, user_id, allow_archived=allow_archived)
    except WorkspaceArchived as error:
        raise HTTPException(status_code=409, detail={"code": "workspace_archived"}) from error
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    return membership


def _lock_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == workspace_id).with_for_update()
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"})
    return workspace


def _member_payload(user: User, membership: Membership) -> dict:
    return {
        "userId": user.id,
        "email": user.email,
        "role": membership.role,
        "joinedAt": membership.created_at,
    }


def _invitation_payload(invitation: WorkspaceInvitation) -> dict:
    return {
        "id": invitation.id,
        "workspaceId": invitation.workspace_id,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expiresAt": invitation.expires_at,
        "createdAt": invitation.created_at,
    }


def _owner_count(db: Session, workspace_id: str) -> int:
    return int(db.scalar(select(func.count(Membership.id)).where(
        Membership.workspace_id == workspace_id,
        Membership.role == "owner",
    )) or 0)


def _expires_at(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _active_workspace_count(db: Session, user_id: str) -> int:
    return int(db.scalar(
        select(func.count(Membership.id))
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user_id, Workspace.archived_at.is_(None))
    ) or 0)


def _workspace_member_limit(db: Session, workspace: Workspace, settings: Settings) -> int:
    value = effective_workspace_entitlements(db, workspace, settings).values["workspace.max_members"]
    if type(value) is not int:
        raise HTTPException(status_code=500, detail={"code": "workspace_member_limit_invalid"})
    return value


def _fallback_workspace_id(db: Session, user_id: str, excluded_workspace_id: str) -> str | None:
    return db.scalar(
        select(Workspace.id)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(
            Membership.user_id == user_id,
            Workspace.id != excluded_workspace_id,
            Workspace.archived_at.is_(None),
        )
        .order_by(Membership.created_at, Workspace.id)
        .limit(1)
    )


@router.post("")
def create_user_workspace(
    request: WorkspaceCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    workspace_count = _active_workspace_count(db, current_user.id)
    if workspace_count >= settings.max_workspaces_per_user:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "workspace_limit_reached",
                "limit": settings.max_workspaces_per_user,
            },
        )
    workspace = create_workspace(
        db,
        user=current_user,
        name=request.name,
        default_locale=request.default_locale,
    )
    current_user.active_workspace_id = workspace.id
    add_admin_audit_event(
        db,
        actor=current_user,
        action="workspace.created",
        target_type="workspace",
        target_id=workspace.id,
        reason="workspace_owner_create",
        details={"name": workspace.name, "defaultLocale": workspace.default_locale},
        workspace_id=workspace.id,
    )
    db.commit()
    db.refresh(workspace)
    return _workspace_membership_payload(workspace)


@router.put("/{workspace_id}/active")
def activate_workspace(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    try:
        membership = require_membership(db, workspace_id, current_user.id)
    except WorkspaceArchived as error:
        raise HTTPException(status_code=409, detail={"code": "workspace_archived"}) from error
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"})
    current_user.active_workspace_id = workspace.id
    db.commit()
    return _workspace_membership_payload(workspace, membership.role)


@router.get("/{workspace_id}/members")
def list_workspace_members(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    try:
        require_membership(db, workspace_id, current_user.id)
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    rows = db.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(Membership.role.desc(), User.email)
    ).all()
    return [_member_payload(user, membership) for user, membership in rows]


@router.get("/{workspace_id}/activity-report")
def get_workspace_activity_report(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
    period_start: Annotated[datetime | None, Query(alias="periodStart")] = None,
    period_end: Annotated[datetime | None, Query(alias="periodEnd")] = None,
) -> dict:
    try:
        require_membership(db, workspace_id, current_user.id)
    except WorkspaceArchived as error:
        raise HTTPException(status_code=409, detail={"code": "workspace_archived"}) from error
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    try:
        return activity_report(db, start=period_start, end=period_end, workspace_id=workspace_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"code": str(error)}) from error


@router.get("/{workspace_id}/invitations")
def list_workspace_invitations(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    _require_owner(db, workspace_id, current_user.id)
    now = utc_now()
    invitations = list(db.scalars(
        select(WorkspaceInvitation)
        .where(WorkspaceInvitation.workspace_id == workspace_id)
        .order_by(WorkspaceInvitation.created_at.desc())
    ))
    changed = False
    for invitation in invitations:
        if invitation.status == "pending" and _expires_at(invitation.expires_at) <= now:
            invitation.status = "expired"
            changed = True
    if changed:
        db.commit()
    return [_invitation_payload(item) for item in invitations]


@router.post("/{workspace_id}/invitations")
def create_workspace_invitation(
    workspace_id: str,
    request: WorkspaceInvitationCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    _require_owner(db, workspace_id, current_user.id)
    workspace = _lock_workspace(db, workspace_id)
    member_limit = _workspace_member_limit(db, workspace, settings)
    if member_limit >= 0:
        member_count = db.scalar(select(func.count(Membership.id)).where(
            Membership.workspace_id == workspace_id
        )) or 0
        pending_count = db.scalar(select(func.count(WorkspaceInvitation.id)).where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.status == "pending",
            WorkspaceInvitation.expires_at > utc_now(),
        )) or 0
        if member_count + pending_count >= member_limit:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_member_limit_reached", "limit": member_limit},
            )
    email = str(request.email).strip().lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user and db.scalar(select(Membership).where(
        Membership.workspace_id == workspace_id,
        Membership.user_id == existing_user.id,
    )):
        raise HTTPException(status_code=409, detail={"code": "workspace_member_exists"})
    pending = db.scalar(select(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.email == email,
        WorkspaceInvitation.status == "pending",
        WorkspaceInvitation.expires_at > utc_now(),
    ))
    if pending:
        raise HTTPException(status_code=409, detail={"code": "workspace_invitation_pending"})
    token = secrets.token_urlsafe(32)
    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        email=email,
        role="member",
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        status="pending",
        invited_by_user_id=current_user.id,
        expires_at=utc_now() + timedelta(days=request.expires_in_days),
    )
    db.add(invitation)
    db.flush()
    add_admin_audit_event(
        db,
        actor=current_user,
        action="workspace.invitation_created",
        target_type="workspace_invitation",
        target_id=invitation.id,
        reason="workspace_owner_invite",
        details={"workspaceId": workspace_id, "email": email, "expiresAt": invitation.expires_at.isoformat()},
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(invitation)
    return {**_invitation_payload(invitation), "acceptanceToken": token}


@router.delete("/{workspace_id}/invitations/{invitation_id}")
def revoke_workspace_invitation(
    workspace_id: str,
    invitation_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_owner(db, workspace_id, current_user.id)
    _lock_workspace(db, workspace_id)
    invitation = db.scalar(select(WorkspaceInvitation).where(
        WorkspaceInvitation.id == invitation_id,
        WorkspaceInvitation.workspace_id == workspace_id,
    ))
    if invitation is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_invitation_not_found"})
    if invitation.status == "pending":
        invitation.status = "revoked"
        invitation.revoked_at = utc_now()
        add_admin_audit_event(
            db, actor=current_user, action="workspace.invitation_revoked",
            target_type="workspace_invitation", target_id=invitation.id,
            reason="workspace_owner_revoke", details={"workspaceId": workspace_id},
            workspace_id=workspace_id,
        )
        db.commit()
    return _invitation_payload(invitation)


@router.post("/invitations/accept")
def accept_workspace_invitation(
    request: WorkspaceInvitationAcceptRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    invitation = db.scalar(
        select(WorkspaceInvitation).where(WorkspaceInvitation.token_hash == token_hash).with_for_update()
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_invitation_not_found"})
    if invitation.email != current_user.email:
        raise HTTPException(status_code=403, detail={"code": "workspace_invitation_email_mismatch"})
    if invitation.status != "pending":
        raise HTTPException(status_code=409, detail={"code": f"workspace_invitation_{invitation.status}"})
    if _expires_at(invitation.expires_at) <= utc_now():
        invitation.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail={"code": "workspace_invitation_expired"})
    workspace = _lock_workspace(db, invitation.workspace_id)
    if workspace.archived_at is not None:
        raise HTTPException(status_code=409, detail={"code": "workspace_archived"})
    membership = db.scalar(select(Membership).where(
        Membership.workspace_id == invitation.workspace_id,
        Membership.user_id == current_user.id,
    ))
    if membership is None:
        member_limit = _workspace_member_limit(db, workspace, settings)
        member_count = db.scalar(select(func.count(Membership.id)).where(
            Membership.workspace_id == invitation.workspace_id
        )) or 0
        if member_limit >= 0 and member_count >= member_limit:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_member_limit_reached", "limit": member_limit},
            )
        if _active_workspace_count(db, current_user.id) >= settings.max_workspaces_per_user:
            raise HTTPException(
                status_code=409,
                detail={"code": "workspace_limit_reached", "limit": settings.max_workspaces_per_user},
            )
        membership = Membership(
            workspace_id=invitation.workspace_id,
            user_id=current_user.id,
            role=invitation.role,
        )
        db.add(membership)
        db.flush()
    invitation.status = "accepted"
    invitation.accepted_by_user_id = current_user.id
    invitation.accepted_at = utc_now()
    current_user.active_workspace_id = invitation.workspace_id
    add_admin_audit_event(
        db, actor=current_user, action="workspace.invitation_accepted",
        target_type="workspace_invitation", target_id=invitation.id,
        reason="workspace_member_accept", details={"workspaceId": invitation.workspace_id},
        workspace_id=invitation.workspace_id,
    )
    db.commit()
    workspace = db.get(Workspace, invitation.workspace_id)
    return _workspace_membership_payload(workspace, membership.role)


@router.patch("/{workspace_id}/members/{user_id}")
def update_workspace_member_role(
    workspace_id: str,
    user_id: str,
    request: WorkspaceMemberRoleRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_owner(db, workspace_id, current_user.id)
    _lock_workspace(db, workspace_id)
    membership = db.scalar(select(Membership).where(
        Membership.workspace_id == workspace_id,
        Membership.user_id == user_id,
    ).with_for_update())
    target = db.get(User, user_id)
    if membership is None or target is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_member_not_found"})
    if membership.role == "owner" and request.role == "member" and _owner_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=409, detail={"code": "workspace_last_owner"})
    previous_role = membership.role
    membership.role = request.role
    if previous_role != membership.role:
        add_admin_audit_event(
            db, actor=current_user, action="workspace.member_role_updated",
            target_type="membership", target_id=membership.id,
            reason="workspace_owner_role_change",
            details={"workspaceId": workspace_id, "before": previous_role, "after": membership.role},
            workspace_id=workspace_id,
        )
        db.commit()
    return _member_payload(target, membership)


@router.post("/{workspace_id}/ownership-transfer")
def transfer_workspace_ownership(
    workspace_id: str,
    request: WorkspaceOwnershipTransferRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    current_membership = _require_owner(db, workspace_id, current_user.id)
    _lock_workspace(db, workspace_id)
    target_membership = db.scalar(select(Membership).where(
        Membership.workspace_id == workspace_id,
        Membership.user_id == request.target_user_id,
    ).with_for_update())
    if target_membership is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_member_not_found"})
    if target_membership.user_id == current_user.id:
        raise HTTPException(status_code=409, detail={"code": "workspace_ownership_unchanged"})
    target_membership.role = "owner"
    current_membership.role = "member"
    add_admin_audit_event(
        db, actor=current_user, action="workspace.ownership_transferred",
        target_type="workspace", target_id=workspace_id,
        reason="workspace_owner_transfer", details={"newOwnerUserId": target_membership.user_id},
        workspace_id=workspace_id,
    )
    db.commit()
    return list_workspace_members(workspace_id, current_user, db)


@router.delete("/{workspace_id}/members/{user_id}")
def remove_workspace_member(
    workspace_id: str,
    user_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    try:
        actor_membership = require_membership(db, workspace_id, current_user.id)
    except WorkspaceAccessDenied as error:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"}) from error
    _lock_workspace(db, workspace_id)
    if current_user.id != user_id and actor_membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})
    membership = db.scalar(select(Membership).where(
        Membership.workspace_id == workspace_id,
        Membership.user_id == user_id,
    ).with_for_update())
    target = db.get(User, user_id)
    if membership is None or target is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_member_not_found"})
    if membership.role == "owner" and _owner_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=409, detail={"code": "workspace_last_owner"})
    membership_id = membership.id
    db.delete(membership)
    db.flush()
    if target.active_workspace_id == workspace_id:
        target.active_workspace_id = _fallback_workspace_id(db, target.id, workspace_id)
    add_admin_audit_event(
        db, actor=current_user, action="workspace.member_removed",
        target_type="membership", target_id=membership_id,
        reason="workspace_member_leave" if current_user.id == user_id else "workspace_owner_remove",
        details={"workspaceId": workspace_id, "removedUserId": user_id},
        workspace_id=workspace_id,
    )
    db.commit()
    return {"removed": True, "userId": user_id}


@router.post("/{workspace_id}/archive")
def archive_workspace(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_owner(db, workspace_id, current_user.id)
    workspace = _lock_workspace(db, workspace_id)
    if workspace.archived_at is not None:
        return _workspace_membership_payload(workspace)
    now = utc_now()
    workspace.archived_at = now
    workspace.archived_by_user_id = current_user.id
    for invitation in db.scalars(select(WorkspaceInvitation).where(
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.status == "pending",
    )):
        invitation.status = "revoked"
        invitation.revoked_at = now
    user_ids = list(db.scalars(select(Membership.user_id).where(
        Membership.workspace_id == workspace_id
    )))
    for user in db.scalars(select(User).where(User.id.in_(user_ids))):
        if user.active_workspace_id == workspace_id:
            user.active_workspace_id = _fallback_workspace_id(db, user.id, workspace_id)
    add_admin_audit_event(
        db,
        actor=current_user,
        action="workspace.archived",
        target_type="workspace",
        target_id=workspace_id,
        reason="workspace_owner_archive",
        details={"memberCount": len(user_ids)},
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(workspace)
    return _workspace_membership_payload(workspace)


@router.post("/{workspace_id}/restore")
def restore_workspace(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    membership = _require_owner(db, workspace_id, current_user.id, allow_archived=True)
    workspace = _lock_workspace(db, workspace_id)
    if workspace.archived_at is None:
        return _workspace_membership_payload(workspace, membership.role)
    member_ids = list(db.scalars(select(Membership.user_id).where(
        Membership.workspace_id == workspace_id
    )))
    blocked_members = sum(
        1 for user_id in member_ids
        if _active_workspace_count(db, user_id) >= settings.max_workspaces_per_user
    )
    if blocked_members:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "workspace_restore_member_limit",
                "limit": settings.max_workspaces_per_user,
                "blockedMembers": blocked_members,
            },
        )
    workspace.archived_at = None
    workspace.archived_by_user_id = None
    if current_user.active_workspace_id is None:
        current_user.active_workspace_id = workspace.id
    add_admin_audit_event(
        db,
        actor=current_user,
        action="workspace.restored",
        target_type="workspace",
        target_id=workspace_id,
        reason="workspace_owner_restore",
        details={"memberCount": len(member_ids)},
        workspace_id=workspace_id,
    )
    db.commit()
    db.refresh(workspace)
    return _workspace_membership_payload(workspace, membership.role)


@router.get("/{workspace_id}/audit-events")
def list_workspace_audit_events(
    workspace_id: str,
    current_user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    _require_owner(db, workspace_id, current_user.id, allow_archived=True)
    events = db.scalars(
        select(AdminAuditEvent)
        .where(AdminAuditEvent.workspace_id == workspace_id)
        .order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
        .limit(limit)
    )
    return [{
        "id": event.id,
        "actorUserId": event.actor_user_id,
        "action": event.action,
        "targetType": event.target_type,
        "targetId": event.target_id,
        "reason": event.reason,
        "details": event.details,
        "createdAt": event.created_at,
    } for event in events]


@router.patch("/{workspace_id}")
def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    _require_owner(db, workspace_id, current_user.id)
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail={"code": "workspace_not_found"})
    previous_name = workspace.name
    if previous_name == request.name:
        return {"id": workspace.id, "name": workspace.name, "defaultLocale": workspace.default_locale}
    workspace.name = request.name
    add_admin_audit_event(
        db,
        actor=current_user,
        action="workspace.renamed",
        target_type="workspace",
        target_id=workspace.id,
        reason="workspace_owner_rename",
        details={"before": {"name": previous_name}, "after": {"name": workspace.name}},
        workspace_id=workspace.id,
    )
    db.commit()
    db.refresh(workspace)
    return {"id": workspace.id, "name": workspace.name, "defaultLocale": workspace.default_locale}
