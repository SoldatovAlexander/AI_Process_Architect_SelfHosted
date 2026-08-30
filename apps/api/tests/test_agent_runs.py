from copy import deepcopy
from datetime import datetime, timedelta, timezone

from process_architect_api.database import get_session_factory
from process_architect_api.config import get_settings
from process_architect_api.db_models import AgentRun, BillingUsageReservation
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from test_api import authorization, request
from test_projects_api import LEAD


def create_agent_project(email: str = "agent-run-owner@example.com") -> tuple[dict, dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    process_ir = deepcopy(LEAD)
    task = next(item for item in process_ir["steps"] if item["type"] == "system_task")
    task["systemId"] = "system_website"
    task["execution"] = {"performedBy": "ai", "autonomy": "supervised", "approvalRequired": True, "restrictions": ["No direct state changes"]}
    project = request("POST", "/api/v1/projects", headers=headers, json={"workspace_id": user["workspaces"][0]["workspace_id"], "name": "Governed agent", "target_mode": "agent", "process_ir": process_ir}).json()
    return headers, project


def test_agent_run_lifecycle_is_idempotent_metered_and_audited_without_content(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, project = create_agent_project()
    payload = {"runtime": "openclaw", "idempotency_key": "demo-run-001", "limits": {"max_steps": 3, "max_tool_calls": 2, "timeout_seconds": 60, "max_cost_microunits": 1000}}
    created = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json=payload)
    assert created.status_code == 201
    run = created.json()
    assert run["revision_id"] == project["current_revision_id"]
    assert run["events"][0]["event_type"] == "run_created"

    duplicate = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == run["id"]

    started = request("POST", f"/api/v1/agent-runs/{run['id']}/transitions", headers=headers, json={"action": "start"})
    assert started.json()["status"] == "running"
    used = request("POST", f"/api/v1/agent-runs/{run['id']}/usage", headers=headers, json={"steps": 1, "tool_calls": 1, "cost_microunits": 200})
    assert used.json()["usage"] == {"steps": 1, "tool_calls": 1, "cost_microunits": 200}
    waiting = request("POST", f"/api/v1/agent-runs/{run['id']}/transitions", headers=headers, json={"action": "request_approval", "reason_code": "external_write"})
    assert waiting.json()["status"] == "awaiting_approval"
    approved = request("POST", f"/api/v1/agent-runs/{run['id']}/transitions", headers=headers, json={"action": "approve"})
    assert approved.json()["status"] == "running"
    completed = request("POST", f"/api/v1/agent-runs/{run['id']}/transitions", headers=headers, json={"action": "complete"})
    assert completed.json()["status"] == "completed"
    assert [event["sequence"] for event in completed.json()["events"]] == list(range(1, 7))
    serialized = str(completed.json())
    assert "prompt" not in serialized and "result" not in serialized and "password" not in serialized

    invalid = request("POST", f"/api/v1/agent-runs/{run['id']}/transitions", headers=headers, json={"action": "start"})
    assert invalid.status_code == 409
    with get_session_factory()() as db:
        reservation = db.query(BillingUsageReservation).one()
        assert reservation.metric == "agent_run"
        assert reservation.status == "consumed"


def test_agent_run_limits_fail_closed_and_access_isolated():
    headers, project = create_agent_project("agent-limit-owner@example.com")
    created = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json={"runtime": "hermes", "idempotency_key": "limit-run-001", "limits": {"max_steps": 1, "max_tool_calls": 1, "timeout_seconds": 30, "max_cost_microunits": 10}}).json()
    request("POST", f"/api/v1/agent-runs/{created['id']}/transitions", headers=headers, json={"action": "start"})
    exceeded = request("POST", f"/api/v1/agent-runs/{created['id']}/usage", headers=headers, json={"steps": 2, "tool_calls": 0, "cost_microunits": 0}).json()
    assert exceeded["status"] == "failed"
    assert exceeded["events"][-1]["event_type"] == "limit_exceeded"
    assert exceeded["events"][-1]["reason_code"] == "steps"

    other_tokens = request("POST", "/api/v1/auth/register", json={"email": "agent-run-outsider@example.com", "password": "correct-horse-battery-staple"}).json()
    other_headers = authorization(other_tokens)
    assert request("GET", f"/api/v1/agent-runs/{created['id']}", headers=other_headers).status_code == 404


def test_non_agent_project_cannot_create_agent_run():
    headers, project = create_agent_project("process-mode-owner@example.com")
    request("PATCH", f"/api/v1/projects/{project['id']}/target-mode", headers=headers, json={"target_mode": "process"})
    response = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json={"runtime": "openclaw", "idempotency_key": "blocked-run-001"})
    assert response.status_code == 409


def test_timeout_is_enforced_before_next_operation():
    headers, project = create_agent_project("agent-timeout-owner@example.com")
    created = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json={"runtime": "openclaw", "idempotency_key": "timeout-run-001", "limits": {"max_steps": 3, "max_tool_calls": 2, "timeout_seconds": 10, "max_cost_microunits": 0}}).json()
    request("POST", f"/api/v1/agent-runs/{created['id']}/transitions", headers=headers, json={"action": "start"})
    with get_session_factory()() as db:
        run = db.get(AgentRun, created["id"])
        run.started_at = datetime.now(timezone.utc) - timedelta(seconds=20)
        db.commit()
    timed_out = request("POST", f"/api/v1/agent-runs/{created['id']}/usage", headers=headers, json={"steps": 1}).json()
    assert timed_out["status"] == "failed"
    assert timed_out["events"][-1]["event_type"] == "timeout_exceeded"
