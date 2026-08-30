from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import Membership, Project, User, Workspace, WorkspaceCommercialState
from ..deployment_profiles import get_deployment_profile
from ..entitlements import EntitlementCatalog, EntitlementCatalogError, get_entitlement_catalog
from ..monitoring import record_entitlement_decision
from .licensing import reconcile_license_state


READ_ONLY_PLAN_ID = "read_only"


class EntitlementAccessError(RuntimeError):
    def __init__(self, entitlement_id: str, reason: str, *, limit: int | None = None):
        super().__init__(reason)
        self.entitlement_id = entitlement_id
        self.reason = reason
        self.limit = limit


@dataclass(frozen=True)
class EffectiveEntitlements:
    workspace_id: str
    plan_id: str
    configured_plan_id: str
    status: str
    source: str
    catalog_version: str
    values: dict[str, bool | int]
    fallback_reason: str | None
    expires_at: datetime | None
    grace_until: datetime | None


def _default_plan_id(settings: Settings) -> str:
    profile = get_deployment_profile()
    return settings.hosted_default_plan_id if profile.profile_id == "hosted" else settings.self_hosted_default_plan_id


def create_default_commercial_state(
    db: Session,
    workspace: Workspace,
    settings: Settings,
) -> WorkspaceCommercialState:
    catalog = get_entitlement_catalog()
    plan_id = _default_plan_id(settings)
    catalog.plan(plan_id)
    state = WorkspaceCommercialState(
        workspace_id=workspace.id,
        plan_id=plan_id,
        status="active",
        source="deployment",
        catalog_version=catalog.catalog_version,
        entitlement_overrides={},
    )
    db.add(state)
    db.flush()
    return state


def ensure_all_workspace_commercial_states(db: Session, settings: Settings) -> int:
    existing = set(db.scalars(select(WorkspaceCommercialState.workspace_id)))
    created = 0
    for workspace in db.scalars(select(Workspace).order_by(Workspace.id)):
        if workspace.id not in existing:
            create_default_commercial_state(db, workspace, settings)
            created += 1
    if created:
        db.commit()
    return created


def _require_workspace_membership(db: Session, workspace_id: str, user_id: str) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user_id,
        )
    )
    if membership is None:
        raise EntitlementAccessError("workspace.access", "workspace_access_denied")
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.archived_at is not None:
        raise EntitlementAccessError("workspace.access", "workspace_archived")
    return membership


def resolve_entitlement_workspace(
    db: Session,
    user: User,
    workspace_id: str | None = None,
) -> Workspace:
    if workspace_id:
        _require_workspace_membership(db, workspace_id, user.id)
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise EntitlementAccessError("workspace.access", "workspace_access_denied")
        return workspace
    if user.active_workspace_id:
        membership = db.scalar(
            select(Membership).where(
                Membership.workspace_id == user.active_workspace_id,
                Membership.user_id == user.id,
            )
        )
        active_workspace = db.get(Workspace, user.active_workspace_id)
        if membership is not None and active_workspace is not None and active_workspace.archived_at is None:
            return active_workspace
    workspaces = list(
        db.scalars(
            select(Workspace)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user.id)
            .where(Workspace.archived_at.is_(None))
            .order_by(Workspace.id)
        )
    )
    if len(workspaces) != 1:
        raise EntitlementAccessError("workspace.access", "workspace_context_required")
    return workspaces[0]


def _validate_overrides(catalog: EntitlementCatalog, overrides: dict) -> dict[str, bool | int]:
    validated: dict[str, bool | int] = {}
    for entitlement_id, value in overrides.items():
        definition = catalog.definition(entitlement_id)
        if definition.kind == "boolean" and type(value) is not bool:
            raise EntitlementCatalogError(f"Invalid boolean override for {entitlement_id}.")
        if definition.kind == "integer" and (type(value) is not int or value < -1):
            raise EntitlementCatalogError(f"Invalid integer override for {entitlement_id}.")
        validated[entitlement_id] = value
    return validated


def _effective_status(state: WorkspaceCommercialState, now: datetime) -> tuple[str, str | None]:
    status = state.status
    effective_from = state.effective_from
    expires_at = state.expires_at
    grace_until = state.grace_until
    if effective_from and effective_from.tzinfo is None:
        effective_from = effective_from.replace(tzinfo=timezone.utc)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if grace_until and grace_until.tzinfo is None:
        grace_until = grace_until.replace(tzinfo=timezone.utc)
    if effective_from and now < effective_from:
        return "read_only", "term_not_started"
    if status in {"trial", "active"} and expires_at and now >= expires_at:
        if grace_until and now < grace_until:
            return "grace", "term_expired"
        return "expired", "term_expired"
    if status == "grace":
        if grace_until is None or now >= grace_until:
            return "expired", "grace_expired"
        return "grace", None
    if status in {"read_only", "expired", "revoked"}:
        return status, status
    return status, None


def effective_workspace_entitlements(
    db: Session,
    workspace: Workspace,
    settings: Settings,
) -> EffectiveEntitlements:
    catalog = get_entitlement_catalog()
    state = db.get(WorkspaceCommercialState, workspace.id)
    if state is None:
        state = create_default_commercial_state(db, workspace, settings)
        db.commit()
        db.refresh(state)
    if state.source == "license":
        reconcile_license_state(db, workspace.id, settings)
        db.refresh(state)
    effective_status, fallback_reason = _effective_status(state, datetime.now(timezone.utc))
    use_fallback = effective_status in {"read_only", "expired", "revoked"}
    if state.catalog_version != catalog.catalog_version:
        use_fallback = True
        fallback_reason = "catalog_version_mismatch"
    configured_plan_id = state.plan_id
    try:
        configured_plan = catalog.plan(configured_plan_id)
    except EntitlementCatalogError:
        configured_plan = None
        use_fallback = True
        fallback_reason = "plan_not_found"
    if use_fallback:
        effective_plan = catalog.plan(READ_ONLY_PLAN_ID)
    else:
        if configured_plan is None:
            raise EntitlementCatalogError("Configured plan resolution failed.")
        effective_plan = configured_plan
    values = dict(effective_plan.entitlements)
    if not use_fallback:
        values.update(_validate_overrides(catalog, state.entitlement_overrides or {}))
    return EffectiveEntitlements(
        workspace_id=workspace.id,
        plan_id=effective_plan.id,
        configured_plan_id=configured_plan_id,
        status=effective_status,
        source=state.source,
        catalog_version=catalog.catalog_version,
        values=values,
        fallback_reason=fallback_reason,
        expires_at=state.expires_at,
        grace_until=state.grace_until,
    )


def require_boolean_entitlement(
    db: Session,
    *,
    user: User,
    settings: Settings,
    entitlement_id: str,
    workspace_id: str | None = None,
) -> EffectiveEntitlements:
    workspace = resolve_entitlement_workspace(db, user, workspace_id)
    effective = effective_workspace_entitlements(db, workspace, settings)
    value = effective.values.get(entitlement_id)
    if value is not True:
        record_entitlement_decision(entitlement_id, "denied")
        raise EntitlementAccessError(entitlement_id, effective.fallback_reason or "not_in_plan")
    record_entitlement_decision(entitlement_id, "allowed")
    return effective


def require_project_creation(
    db: Session,
    *,
    user: User,
    settings: Settings,
    workspace_id: str,
) -> EffectiveEntitlements:
    workspace = resolve_entitlement_workspace(db, user, workspace_id)
    db.scalar(select(Workspace.id).where(Workspace.id == workspace.id).with_for_update())
    effective = require_boolean_entitlement(
        db,
        user=user,
        settings=settings,
        workspace_id=workspace_id,
        entitlement_id="project.create",
    )
    limit = effective.values["project.max_active"]
    if type(limit) is not int:
        raise EntitlementCatalogError("project.max_active must be an integer entitlement.")
    if limit >= 0:
        active_count = db.scalar(
            select(func.count(Project.id)).where(
                Project.workspace_id == workspace_id,
                Project.status != "archived",
            )
        ) or 0
        if active_count >= limit:
            record_entitlement_decision("project.max_active", "denied")
            raise EntitlementAccessError("project.max_active", "limit_reached", limit=limit)
        record_entitlement_decision("project.max_active", "allowed")
    return effective
