from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import StatementError

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import BillingUsageEvent, BillingUsageReservation, Workspace, WorkspaceCommercialState
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from process_architect_api.services.billing_usage import (
    BillingUsageError,
    BillingUsageLimitExceeded,
    metered_operation,
    reserve_usage,
    settle_usage,
    usage_summary,
)

from test_api import authorization, request
from test_projects_api import LEAD


PASSWORD = "correct-horse-battery-staple"


def register(email: str) -> tuple[dict[str, str], dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": PASSWORD}).json()
    return authorization(tokens), tokens


def hosted_admin(monkeypatch) -> tuple[dict[str, str], str]:
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("SERVICE_ADMIN_EMAILS", "usage-admin@example.com")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, _ = register("usage-admin@example.com")
    workspace_id = request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]
    return headers, workspace_id


def set_limit(db, workspace_id: str, metric: str, limit: int) -> Workspace:
    state = db.get(WorkspaceCommercialState, workspace_id)
    workspace = db.get(Workspace, workspace_id)
    assert state is not None and workspace is not None
    state.entitlement_overrides = {f"usage.{metric}.monthly": limit}
    db.flush()
    return workspace


def test_usage_reservation_consumption_and_retries_are_idempotent(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    now = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "export", 2)
        reservation, created = reserve_usage(
            db,
            workspace=workspace,
            settings=get_settings(),
            metric="export",
            idempotency_key="export-request-001",
            now=now,
        )
        repeated, repeated_created = reserve_usage(
            db,
            workspace=workspace,
            settings=get_settings(),
            metric="export",
            idempotency_key="export-request-001",
            now=now,
        )
        consumed, settled = settle_usage(
            db,
            reservation_id=reservation.id,
            outcome="consumed",
            reason_code="operation_completed",
            now=now,
        )
        consumed_again, settled_again = settle_usage(
            db,
            reservation_id=reservation.id,
            outcome="consumed",
            reason_code="operation_completed",
            now=now,
        )
        summary = next(item for item in usage_summary(
            db, workspace=workspace, settings=get_settings(), now=now
        ) if item.metric == "export")

        assert created is True
        assert repeated_created is False
        assert repeated.id == reservation.id
        assert settled is True
        assert settled_again is False
        assert consumed_again.id == consumed.id
        assert summary.reserved == 0
        assert summary.consumed == 1
        assert summary.remaining == 1
        assert db.scalar(select(func.count(BillingUsageEvent.id))) == 2


def test_released_or_expired_reservation_returns_capacity(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    now = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "llm_turn", 1)
        released, _ = reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="llm_turn",
            idempotency_key="llm-request-release", now=now,
        )
        settle_usage(
            db, reservation_id=released.id, outcome="released",
            reason_code="upstream_failed", now=now,
        )
        expired, _ = reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="llm_turn",
            idempotency_key="llm-request-expired", now=now - timedelta(hours=2),
        )
        current, created = reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="llm_turn",
            idempotency_key="llm-request-current", now=now,
        )
        db.flush()

        assert created is True
        assert current.status == "reserved"
        assert expired.status == "released"
        transitions = db.scalars(select(BillingUsageEvent.transition).order_by(BillingUsageEvent.created_at)).all()
        assert transitions.count("released") == 2


def test_monthly_limit_blocks_additional_reservations(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    now = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "agent_run", 1)
        reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="agent_run",
            idempotency_key="agent-run-first", now=now,
        )

        with pytest.raises(BillingUsageLimitExceeded) as captured:
            reserve_usage(
                db, workspace=workspace, settings=get_settings(), metric="agent_run",
                idempotency_key="agent-run-second", now=now,
            )

        assert captured.value.limit == 1
        assert captured.value.used == 1
        assert captured.value.requested == 1


def test_idempotency_key_cannot_change_quantity(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "runtime_publish", 10)
        reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="runtime_publish",
            idempotency_key="runtime-publication-001", quantity=1,
        )

        with pytest.raises(BillingUsageError, match="billing_usage_idempotency_conflict"):
            reserve_usage(
                db, workspace=workspace, settings=get_settings(), metric="runtime_publish",
                idempotency_key="runtime-publication-001", quantity=2,
            )


def test_hosted_admin_can_read_usage_without_idempotency_keys(monkeypatch):
    headers, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "export", 2)
        reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="export",
            idempotency_key="private-operation-key", quantity=2,
        )
        db.commit()

    summary = request(
        "GET", f"/api/v1/admin/billing/usage?workspaceId={workspace_id}", headers=headers
    )
    reservations = request("GET", "/api/v1/admin/billing/usage/reservations", headers=headers)

    assert summary.status_code == 200
    export_usage = next(item for item in summary.json()["items"] if item["metric"] == "export")
    assert export_usage["limit"] == 2
    assert export_usage["reserved"] == 2
    assert export_usage["remaining"] == 0
    assert summary.json()["alerts"] == [{
        "code": "usage_limit_exceeded",
        "severity": "critical",
        "workspaceId": workspace_id,
        "metric": "export",
        "limit": 2,
        "used": 2,
        "ratio": 1.0,
    }]
    assert reservations.status_code == 200
    assert "idempotencyKey" not in reservations.json()["items"][0]


def test_usage_transition_events_are_immutable(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "export", 5)
        reserve_usage(
            db, workspace=workspace, settings=get_settings(), metric="export",
            idempotency_key="immutable-usage-event",
        )
        db.commit()
        event = db.scalar(select(BillingUsageEvent))
        assert event is not None
        event.reason_code = "tampered"
        try:
            db.commit()
        except Exception as error:
            assert isinstance(error, StatementError) or "immutable" in str(error).lower()
            db.rollback()
        else:
            raise AssertionError("Usage event update unexpectedly succeeded.")


def test_metered_operation_retries_released_attempt_and_replays_consumed_attempt(monkeypatch):
    _, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        workspace = set_limit(db, workspace_id, "export", 3)
        db.commit()
        with pytest.raises(RuntimeError, match="generation failed"):
            with metered_operation(
                db,
                workspace_id=workspace.id,
                settings=get_settings(),
                metric="export",
                operation="export.spec",
                request_key="retryable-export-001",
            ):
                raise RuntimeError("generation failed")

        with metered_operation(
            db,
            workspace_id=workspace.id,
            settings=get_settings(),
            metric="export",
            operation="export.spec",
            request_key="retryable-export-001",
        ):
            pass
        with metered_operation(
            db,
            workspace_id=workspace.id,
            settings=get_settings(),
            metric="export",
            operation="export.spec",
            request_key="retryable-export-001",
        ):
            pass

        reservations = db.scalars(
            select(BillingUsageReservation).order_by(BillingUsageReservation.created_at)
        ).all()
        assert [item.status for item in reservations] == ["released", "consumed"]


def test_hosted_exports_consume_once_per_idempotent_request_and_enforce_limit(monkeypatch):
    headers, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        set_limit(db, workspace_id, "export", 1)
        db.commit()

    first_headers = {**headers, "Idempotency-Key": "metered-export-request-001"}
    first = request("POST", "/api/v1/exports/spec", headers=first_headers, json=LEAD)
    repeated = request("POST", "/api/v1/exports/spec", headers=first_headers, json=LEAD)
    blocked = request(
        "POST",
        "/api/v1/exports/spec",
        headers={**headers, "Idempotency-Key": "metered-export-request-002"},
        json=LEAD,
    )

    assert first.status_code == repeated.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["metric"] == "export"
    with get_session_factory()() as db:
        reservations = db.scalars(select(BillingUsageReservation)).all()
        assert len(reservations) == 1
        assert reservations[0].status == "consumed"
