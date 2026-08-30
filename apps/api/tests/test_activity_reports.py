import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import AgentPackageDelivery, AgentRun, BillingUsageReservation, LLMUsageRecord, N8nPublication, RuntimeConnectionProfile
from process_architect_api.deployment_profiles import clear_deployment_profile_cache

from test_api import authorization, request


ROOT = Path(__file__).resolve().parents[3]
PROCESS_IR = json.loads((ROOT / "02_architecture/examples/lead-intake.process-ir.json").read_text())
PASSWORD = "correct-horse-battery-staple"


def _register(email: str) -> tuple[dict[str, str], dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": PASSWORD}).json()
    headers = authorization(tokens)
    return headers, request("GET", "/api/v1/auth/me", headers=headers).json()


def test_activity_report_is_available_globally_and_per_workspace(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("SERVICE_ADMIN_EMAILS", "report-admin@example.com")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, identity = _register("report-admin@example.com")
    workspace_id = identity["active_workspace_id"]
    user_id = identity["id"]
    project = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={"workspace_id": workspace_id, "name": "Lead intake", "process_ir": PROCESS_IR},
    ).json()
    now = datetime.now(timezone.utc)

    with get_session_factory()() as db:
        n8n = RuntimeConnectionProfile(
            workspace_id=workspace_id, name="n8n", kind="n8n", endpoint_url="https://n8n.example.test",
            secret_ref="N8N_KEY", n8n_minor="2.32", status="verified", created_by_user_id=user_id,
        )
        agent = RuntimeConnectionProfile(
            workspace_id=workspace_id, name="agent", kind="openclaw", endpoint_url="https://agent.example.test",
            secret_ref="AGENT_KEY", status="verified", created_by_user_id=user_id,
        )
        db.add_all([n8n, agent])
        db.flush()
        db.add(N8nPublication(
            project_id=project["id"], revision_id=project["current_revision_id"], profile_id=n8n.id,
            idempotency_key="report-n8n", workflow_sha256="a" * 64, status="published",
            created_by_user_id=user_id, published_at=now,
        ))
        db.add(AgentPackageDelivery(
            project_id=project["id"], revision_id=project["current_revision_id"], profile_id=agent.id,
            runtime="openclaw", idempotency_key="report-agent", package_sha256="b" * 64,
            package_size=100, file_count=2, status="stored", created_by_user_id=user_id, stored_at=now,
        ))
        db.add(AgentRun(
            project_id=project["id"], revision_id=project["current_revision_id"], runtime="openclaw",
            idempotency_key="report-run", status="completed", created_by_user_id=user_id,
        ))
        reservation = BillingUsageReservation(
            workspace_id=workspace_id, metric="llm_turn", idempotency_key="report-llm", quantity=1,
            status="consumed", period_start=now.replace(day=1), period_end=now + timedelta(days=31),
            expires_at=now + timedelta(hours=1), settled_at=now,
        )
        db.add(reservation)
        db.flush()
        db.add(LLMUsageRecord(
            workspace_id=workspace_id, reservation_id=reservation.id, operation="analyst.turn",
            provider="test", model="test", outcome="success", request_count=1,
            input_tokens=120, cache_hit_tokens=0, cache_miss_tokens=120, output_tokens=30,
            estimated_cost_picousd=250_000_000, pricing_catalog_version="test",
            pricing_basis="cache_miss_assumed", created_at=now,
        ))
        db.commit()

    workspace_report = request("GET", f"/api/v1/workspaces/{workspace_id}/activity-report", headers=headers)
    admin_report = request("GET", "/api/v1/admin/reports/activity", headers=headers)

    assert workspace_report.status_code == 200
    assert admin_report.status_code == 200
    summary = workspace_report.json()["summary"]
    assert summary["workflowsCreated"] == 1
    assert summary["workflowsInProgress"] == 1
    assert summary["n8nPublications"] == 1
    assert summary["agentDeliveries"] == 1
    assert summary["agentRuns"] == 1
    assert summary["inputTokens"] == 120
    assert summary["outputTokens"] == 30
    assert summary["totalTokens"] == 150
    assert admin_report.json()["workspaces"][0]["workspaceId"] == workspace_id


def test_workspace_report_rejects_non_member_and_invalid_period():
    owner_headers, owner = _register("report-owner@example.com")
    stranger_headers, _ = _register("report-stranger@example.com")
    workspace_id = owner["active_workspace_id"]

    denied = request("GET", f"/api/v1/workspaces/{workspace_id}/activity-report", headers=stranger_headers)
    invalid = request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/activity-report?periodStart=2026-08-02T00:00:00Z&periodEnd=2026-08-01T00:00:00Z",
        headers=owner_headers,
    )

    assert denied.status_code == 404
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "report_period_invalid"
