import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import WorkspaceCommercialState
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from process_architect_api.entitlements import get_entitlement_catalog

from test_api import authorization, request


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def register(email: str) -> tuple[dict[str, str], str]:
    tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    ).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    return headers, user["workspaces"][0]["workspace_id"]


def set_commercial_state(workspace_id: str, **values) -> None:
    with get_session_factory()() as db:
        state = db.get(WorkspaceCommercialState, workspace_id)
        assert state is not None
        for name, value in values.items():
            setattr(state, name, value)
        db.commit()


def test_catalog_defines_complete_typed_plans():
    catalog = get_entitlement_catalog()
    expected = {item.id for item in catalog.entitlements}

    assert catalog.catalog_version == "1.1"
    assert {plan.id for plan in catalog.plans} == {
        "hosted_pilot",
        "self_hosted_full",
        "read_only",
    }
    assert all(set(plan.entitlements) == expected for plan in catalog.plans)
    assert catalog.plan("read_only").entitlements["backup.export"] is True


def test_registration_creates_effective_self_hosted_entitlements():
    headers, workspace_id = register("entitlements@example.com")

    response = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["plan_id"] == "self_hosted_full"
    assert response.json()["status"] == "active"
    assert response.json()["entitlements"]["project.create"] is True
    assert response.json()["entitlements"]["export.spec"] is True
    assert response.json()["entitlements"]["export.bpmn"] is True
    assert response.json()["entitlements"]["export.n8n"] is False
    assert response.json()["entitlements"]["export.agent"] is False


def test_hosted_profile_uses_hosted_default_plan(monkeypatch):
    if not (ROOT / "config" / "deployment_profiles" / "v1" / "hosted.json").is_file():
        pytest.skip("hosted deployment profile is excluded from the self-hosted package")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    get_settings.cache_clear()
    clear_deployment_profile_cache()

    headers, workspace_id = register("hosted-entitlements@example.com")
    response = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["plan_id"] == "hosted_pilot"


def test_entitlements_are_isolated_by_workspace_membership():
    _, workspace_id = register("workspace-owner@example.com")
    foreign_headers, _ = register("foreign-user@example.com")

    response = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=foreign_headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "workspace_access_denied"


def test_read_only_fallback_blocks_project_creation_and_spec_export():
    headers, workspace_id = register("read-only@example.com")
    set_commercial_state(workspace_id, status="read_only")

    entitlements = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )
    project = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={"workspace_id": workspace_id, "name": "Blocked", "process_ir": deepcopy(LEAD)},
    )
    export = request(
        "POST",
        "/api/v1/exports/spec",
        headers=headers,
        params={"workspaceId": workspace_id},
        json=LEAD,
    )

    assert entitlements.json()["plan_id"] == "read_only"
    assert entitlements.json()["entitlements"]["backup.export"] is True
    assert project.status_code == 403
    assert project.json()["detail"]["entitlementId"] == "project.create"
    assert export.status_code == 403
    assert export.json()["detail"]["entitlementId"] == "export.spec"


def test_active_project_limit_is_enforced_server_side():
    headers, workspace_id = register("limited@example.com")
    set_commercial_state(workspace_id, entitlement_overrides={"project.max_active": 1})

    first = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={"workspace_id": workspace_id, "name": "First", "process_ir": deepcopy(LEAD)},
    )
    second = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={"workspace_id": workspace_id, "name": "Second", "process_ir": deepcopy(LEAD)},
    )

    assert first.status_code == 201
    assert second.status_code == 403
    assert second.json()["detail"] == {
        "code": "entitlement_limit_exceeded",
        "entitlementId": "project.max_active",
        "reason": "limit_reached",
        "limit": 1,
    }


def test_unknown_plan_fails_closed_without_hiding_configured_plan():
    headers, workspace_id = register("unknown-plan@example.com")
    set_commercial_state(workspace_id, plan_id="removed_plan")

    response = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["configured_plan_id"] == "removed_plan"
    assert response.json()["plan_id"] == "read_only"
    assert response.json()["fallback_reason"] == "plan_not_found"


def test_expired_term_uses_grace_then_fails_closed():
    headers, workspace_id = register("grace@example.com")
    now = datetime.now(timezone.utc)
    set_commercial_state(
        workspace_id,
        status="active",
        expires_at=now - timedelta(minutes=1),
        grace_until=now + timedelta(days=2),
    )

    grace = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )
    assert grace.json()["status"] == "grace"
    assert grace.json()["plan_id"] == "self_hosted_full"

    set_commercial_state(workspace_id, grace_until=now - timedelta(minutes=1))
    expired = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/entitlements",
        headers=headers,
    )
    assert expired.json()["status"] == "expired"
    assert expired.json()["plan_id"] == "read_only"
    assert expired.json()["fallback_reason"] == "term_expired"
