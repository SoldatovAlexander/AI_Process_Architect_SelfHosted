from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Iterator

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import BillingUsageEvent, BillingUsageReservation, Workspace
from ..deployment_profiles import get_deployment_profile
from ..entitlements import EntitlementCatalogError
from ..monitoring import record_usage_transition
from .entitlements import effective_workspace_entitlements


USAGE_ENTITLEMENTS = {
    "llm_turn": "usage.llm_turn.monthly",
    "export": "usage.export.monthly",
    "runtime_publish": "usage.runtime_publish.monthly",
    "agent_run": "usage.agent_run.monthly",
}
REASON_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")


class BillingUsageError(RuntimeError):
    pass


class BillingUsageLimitExceeded(BillingUsageError):
    def __init__(self, metric: str, limit: int, used: int, requested: int):
        super().__init__("billing_usage_limit_reached")
        self.metric = metric
        self.limit = limit
        self.used = used
        self.requested = requested


class BillingUsageConflict(BillingUsageError):
    pass


@dataclass(frozen=True)
class UsageSummary:
    metric: str
    entitlement_id: str
    period_start: datetime
    period_end: datetime
    limit: int
    reserved: int
    consumed: int

    @property
    def remaining(self) -> int | None:
        if self.limit < 0:
            return None
        return max(self.limit - self.reserved - self.consumed, 0)


@dataclass(frozen=True)
class MeteredUsage:
    reservation_id: str
    metric: str
    settle_required: bool = True


def monthly_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    start = datetime(value.year, value.month, 1, tzinfo=timezone.utc)
    end = datetime(value.year + 1, 1, 1, tzinfo=timezone.utc) if value.month == 12 else datetime(
        value.year, value.month + 1, 1, tzinfo=timezone.utc
    )
    return start, end


def _same_instant(left: datetime, right: datetime) -> bool:
    left_value = left.replace(tzinfo=timezone.utc) if left.tzinfo is None else left.astimezone(timezone.utc)
    right_value = right.replace(tzinfo=timezone.utc) if right.tzinfo is None else right.astimezone(timezone.utc)
    return left_value == right_value


def _entitlement_id(metric: str) -> str:
    try:
        return USAGE_ENTITLEMENTS[metric]
    except KeyError as error:
        raise BillingUsageError("billing_usage_metric_unknown") from error


def _validate_reason_code(reason_code: str) -> None:
    if not REASON_CODE_PATTERN.fullmatch(reason_code):
        raise BillingUsageError("billing_usage_reason_code_invalid")


def release_expired_reservations(
    db: Session,
    *,
    workspace_id: str,
    now: datetime,
) -> int:
    expired = db.scalars(
        select(BillingUsageReservation)
        .where(
            BillingUsageReservation.workspace_id == workspace_id,
            BillingUsageReservation.status == "reserved",
            BillingUsageReservation.expires_at <= now,
        )
        .with_for_update()
    ).all()
    for reservation in expired:
        reservation.status = "released"
        reservation.settled_at = now
        db.add(BillingUsageEvent(
            reservation_id=reservation.id,
            transition="released",
            quantity=reservation.quantity,
            reason_code="reservation_expired",
        ))
        record_usage_transition(reservation.metric, "released")
    if expired:
        db.flush()
    return len(expired)


def usage_summary(
    db: Session,
    *,
    workspace: Workspace,
    settings: Settings,
    now: datetime | None = None,
) -> list[UsageSummary]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    period_start, period_end = monthly_period(current)
    effective = effective_workspace_entitlements(db, workspace, settings)
    grouped = {
        (status, metric): int(quantity)
        for status, metric, quantity in db.execute(
            select(
                BillingUsageReservation.status,
                BillingUsageReservation.metric,
                func.sum(BillingUsageReservation.quantity),
            )
            .where(
                BillingUsageReservation.workspace_id == workspace.id,
                BillingUsageReservation.period_start == period_start,
                or_(
                    BillingUsageReservation.status == "consumed",
                    (
                        (BillingUsageReservation.status == "reserved")
                        & (BillingUsageReservation.expires_at > current)
                    ),
                ),
            )
            .group_by(BillingUsageReservation.status, BillingUsageReservation.metric)
        )
    }
    summaries: list[UsageSummary] = []
    for metric, entitlement_id in USAGE_ENTITLEMENTS.items():
        limit = effective.values.get(entitlement_id)
        if type(limit) is not int:
            raise EntitlementCatalogError(f"{entitlement_id} must be an integer entitlement.")
        summaries.append(UsageSummary(
            metric=metric,
            entitlement_id=entitlement_id,
            period_start=period_start,
            period_end=period_end,
            limit=limit,
            reserved=grouped.get(("reserved", metric), 0),
            consumed=grouped.get(("consumed", metric), 0),
        ))
    return summaries


def reserve_usage(
    db: Session,
    *,
    workspace: Workspace,
    settings: Settings,
    metric: str,
    idempotency_key: str,
    quantity: int = 1,
    now: datetime | None = None,
) -> tuple[BillingUsageReservation, bool]:
    _entitlement_id(metric)
    if not 1 <= quantity <= 1_000_000:
        raise BillingUsageError("billing_usage_quantity_invalid")
    if not 8 <= len(idempotency_key) <= 128:
        raise BillingUsageError("billing_usage_idempotency_key_invalid")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    period_start, period_end = monthly_period(current)

    db.scalar(select(Workspace.id).where(Workspace.id == workspace.id).with_for_update())
    release_expired_reservations(db, workspace_id=workspace.id, now=current)
    existing = db.scalar(select(BillingUsageReservation).where(
        BillingUsageReservation.workspace_id == workspace.id,
        BillingUsageReservation.metric == metric,
        BillingUsageReservation.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if existing.quantity != quantity or not _same_instant(existing.period_start, period_start):
            raise BillingUsageError("billing_usage_idempotency_conflict")
        return existing, False

    summary = next(item for item in usage_summary(
        db, workspace=workspace, settings=settings, now=current
    ) if item.metric == metric)
    used = summary.reserved + summary.consumed
    if summary.limit >= 0 and used + quantity > summary.limit:
        raise BillingUsageLimitExceeded(metric, summary.limit, used, quantity)

    reservation = BillingUsageReservation(
        workspace_id=workspace.id,
        metric=metric,
        idempotency_key=idempotency_key,
        quantity=quantity,
        status="reserved",
        period_start=period_start,
        period_end=period_end,
        expires_at=current + timedelta(minutes=settings.billing_usage_reservation_minutes),
    )
    db.add(reservation)
    db.flush()
    db.add(BillingUsageEvent(
        reservation_id=reservation.id,
        transition="reserved",
        quantity=quantity,
        reason_code="operation_reserved",
    ))
    record_usage_transition(metric, "reserved")
    db.flush()
    return reservation, True


def settle_usage(
    db: Session,
    *,
    reservation_id: str,
    outcome: str,
    reason_code: str,
    now: datetime | None = None,
) -> tuple[BillingUsageReservation, bool]:
    if outcome not in {"consumed", "released"}:
        raise BillingUsageError("billing_usage_outcome_invalid")
    _validate_reason_code(reason_code)
    reservation = db.scalar(
        select(BillingUsageReservation)
        .where(BillingUsageReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise BillingUsageError("billing_usage_reservation_not_found")
    if reservation.status == outcome:
        return reservation, False
    if reservation.status != "reserved":
        raise BillingUsageError("billing_usage_settlement_conflict")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    reservation.status = outcome
    reservation.settled_at = current
    db.add(BillingUsageEvent(
        reservation_id=reservation.id,
        transition=outcome,
        quantity=reservation.quantity,
        reason_code=reason_code,
    ))
    record_usage_transition(reservation.metric, outcome)
    db.flush()
    return reservation, True


def metering_idempotency_key(operation: str, request_key: str) -> str:
    operation_slug = re.sub(r"[^a-z0-9_.-]+", "-", operation.lower()).strip("-")[:32] or "operation"
    digest = sha256(f"{operation}\0{request_key}".encode("utf-8")).hexdigest()
    return f"{operation_slug}:{digest}"


def begin_metered_usage(
    db: Session,
    *,
    workspace_id: str,
    settings: Settings,
    metric: str,
    operation: str,
    request_key: str,
    commit: bool = True,
) -> MeteredUsage | None:
    if not get_deployment_profile().administration.billing_enabled:
        return None
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.archived_at is not None:
        raise BillingUsageError("billing_usage_workspace_not_found")
    base_key = metering_idempotency_key(operation, request_key)
    reservation, created = reserve_usage(
        db,
        workspace=workspace,
        settings=settings,
        metric=metric,
        idempotency_key=base_key,
    )
    if reservation.status == "released":
        retries = list(db.scalars(
            select(BillingUsageReservation)
            .where(
                BillingUsageReservation.workspace_id == workspace_id,
                BillingUsageReservation.metric == metric,
                BillingUsageReservation.idempotency_key.like(f"{base_key}:r%"),
            )
            .order_by(BillingUsageReservation.created_at)
        ))
        active_retry = next((item for item in reversed(retries) if item.status != "released"), None)
        if active_retry is not None:
            reservation = active_retry
            created = False
        else:
            reservation, created = reserve_usage(
                db,
                workspace=workspace,
                settings=settings,
                metric=metric,
                idempotency_key=f"{base_key}:r{len(retries) + 1}",
            )
    if not created and reservation.status == "reserved":
        raise BillingUsageConflict("billing_usage_operation_in_progress")
    settle_required = reservation.status != "consumed"
    if commit:
        db.commit()
        db.refresh(reservation)
    else:
        db.flush()
    return MeteredUsage(
        reservation_id=reservation.id,
        metric=metric,
        settle_required=settle_required,
    )


def finish_metered_usage(
    db: Session,
    *,
    meter: MeteredUsage | None,
    outcome: str,
    reason_code: str,
    commit: bool = True,
) -> None:
    if meter is None or not meter.settle_required:
        return
    settle_usage(
        db,
        reservation_id=meter.reservation_id,
        outcome=outcome,
        reason_code=reason_code,
    )
    if commit:
        db.commit()
    else:
        db.flush()


@contextmanager
def metered_operation(
    db: Session,
    *,
    workspace_id: str,
    settings: Settings,
    metric: str,
    operation: str,
    request_key: str,
) -> Iterator[MeteredUsage | None]:
    meter = begin_metered_usage(
        db,
        workspace_id=workspace_id,
        settings=settings,
        metric=metric,
        operation=operation,
        request_key=request_key,
    )
    try:
        yield meter
    except Exception:
        db.rollback()
        finish_metered_usage(
            db,
            meter=meter,
            outcome="released",
            reason_code="operation_failed",
        )
        raise
    else:
        finish_metered_usage(
            db,
            meter=meter,
            outcome="consumed",
            reason_code="operation_completed",
        )
