from datetime import datetime, timedelta, timezone

import httpx

from process_architect_api.agent_worker import process_one
from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import AgentDispatchJob, AgentRun
from process_architect_api.services.agent_dispatch import claim_next_job, mark_dispatch_failure
from test_agent_evaluations import create_ready_project, gate, submit
from test_api import request


def approved_project(email: str, runtime: str = "openclaw") -> tuple[dict, dict]:
    headers, project = create_ready_project(email)
    current_gate = gate(headers, project, runtime)
    evaluation = submit(headers, project, current_gate, runtime=runtime)
    response = request(
        "POST",
        f"/api/v1/projects/{project['id']}/agent-baselines",
        headers=headers,
        json={"evaluation_run_id": evaluation["id"]},
    )
    assert response.status_code == 201
    return headers, project


def dispatch(headers: dict, project: dict, key: str = "dispatch-test-key") -> dict:
    response = request(
        "POST",
        f"/api/v1/projects/{project['id']}/agent-dispatches",
        headers=headers,
        json={"runtime": "openclaw", "idempotency_key": key},
    )
    assert response.status_code == 201
    return response.json()


def test_dispatch_requires_pilot_gate_and_is_idempotent():
    headers, project = create_ready_project("dispatch-gate@example.com")
    blocked = request(
        "POST",
        f"/api/v1/projects/{project['id']}/agent-dispatches",
        headers=headers,
        json={"runtime": "openclaw", "idempotency_key": "blocked-dispatch"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "agent_dispatch_blocked"

    current_gate = gate(headers, project)
    evaluation = submit(headers, project, current_gate)
    request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": evaluation["id"]})
    first = dispatch(headers, project, "same-dispatch-key")
    duplicate = request(
        "POST",
        f"/api/v1/projects/{project['id']}/agent-dispatches",
        headers=headers,
        json={"runtime": "openclaw", "idempotency_key": "same-dispatch-key"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["job"]["id"] == first["job"]["id"]
    assert first["run"]["events"][-1]["event_type"] == "run_queued"


def test_worker_dispatches_minimal_revision_bound_envelope(monkeypatch):
    headers, project = approved_project("dispatch-worker@example.com")
    queued = dispatch(headers, project)
    delivered: dict = {}

    def fake_post(url, *, json, headers, timeout):
        delivered.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return httpx.Response(200, json={"status": "accepted"}, request=httpx.Request("POST", url))

    monkeypatch.setenv("OPENCLAW_RUNTIME_URL", "https://runtime.invalid/runs")
    monkeypatch.setenv("OPENCLAW_RUNTIME_TOKEN", "runtime-secret")
    monkeypatch.setenv("AGENT_RUNTIME_CALLBACK_BASE_URL", "https://architect.invalid")
    get_settings.cache_clear()
    assert process_one("worker-test", post=fake_post) is True

    status = request("GET", f"/api/v1/agent-dispatches/{queued['job']['id']}", headers=headers).json()
    assert status["job"]["status"] == "dispatched"
    assert status["run"]["status"] == "running"
    assert delivered["headers"]["Idempotency-Key"] == "dispatch-test-key"
    assert delivered["headers"]["Authorization"] == "Bearer runtime-secret"
    assert delivered["json"]["run_id"] == queued["run"]["id"]
    assert delivered["json"]["revision_id"] == project["current_revision_id"]
    assert delivered["json"]["callback_contract"]["content_allowed"] is False
    assert "runtime-secret" not in str(delivered["json"])


def test_disabled_worker_preserves_queued_dispatch(monkeypatch):
    headers, project = approved_project("dispatch-paused@example.com")
    queued = dispatch(headers, project)
    monkeypatch.setenv("AGENT_WORKER_DISPATCH_ENABLED", "false")
    get_settings.cache_clear()

    assert process_one("worker-paused") is False

    status = request("GET", f"/api/v1/agent-dispatches/{queued['job']['id']}", headers=headers).json()
    assert status["job"]["status"] == "queued"
    assert status["run"]["status"] == "created"


def test_expired_lease_is_reclaimed_and_failures_reach_dead_letter():
    headers, project = approved_project("dispatch-retry@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        first = claim_next_job(db, "worker-a", 30)
        assert first and first.id == queued["job"]["id"]
        first.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    with get_session_factory()() as db:
        reclaimed = claim_next_job(db, "worker-b", 30)
        assert reclaimed and reclaimed.attempt_count == 2
        reclaimed.max_attempts = 2
        run = db.get(AgentRun, reclaimed.run_id)
        mark_dispatch_failure(db, reclaimed, run, "runtime_unavailable")
        assert reclaimed.status == "dead_letter"
        assert run.status == "failed"


def test_runtime_callback_is_secret_protected_content_free_and_enforces_limits(monkeypatch):
    headers, project = approved_project("dispatch-callback@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        job = db.get(AgentDispatchJob, queued["job"]["id"])
        run = db.get(AgentRun, job.run_id)
        run.status = "running"
        job.status = "dispatched"
        db.commit()

    monkeypatch.setenv("AGENT_RUNTIME_CALLBACK_TOKEN", "callback-secret")
    get_settings.cache_clear()
    path = f"/api/v1/runtime/agent-runs/{queued['run']['id']}/callback"
    assert request("POST", path, json={"callback_id": "callback-1", "status": "completed"}).status_code == 401
    rejected = request("POST", path, headers={"Authorization": "Bearer callback-secret"}, json={"callback_id": "callback-1", "status": "completed", "content": "must not be stored"})
    assert rejected.status_code == 422
    exceeded = request(
        "POST",
        path,
        headers={"Authorization": "Bearer callback-secret"},
        json={"callback_id": "callback-limit-1", "status": "completed", "reason_code": "done", "steps": 21, "tool_calls": 0, "cost_microunits": 0},
    )
    assert exceeded.status_code == 200
    assert exceeded.json()["status"] == "failed"
    assert exceeded.json()["events"][-1]["event_type"] == "limit_exceeded"


def test_runtime_callback_replay_is_idempotent(monkeypatch):
    headers, project = approved_project("dispatch-callback-replay@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        job = db.get(AgentDispatchJob, queued["job"]["id"])
        run = db.get(AgentRun, job.run_id)
        run.status = "running"
        job.status = "dispatched"
        db.commit()
    monkeypatch.setenv("AGENT_RUNTIME_CALLBACK_TOKEN", "callback-secret")
    get_settings.cache_clear()
    path = f"/api/v1/runtime/agent-runs/{queued['run']['id']}/callback"
    payload = {"callback_id": "runtime-event-001", "status": "awaiting_approval", "steps": 2, "tool_calls": 1}
    first = request("POST", path, headers={"Authorization": "Bearer callback-secret"}, json=payload)
    second = request("POST", path, headers={"Authorization": "Bearer callback-secret"}, json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["usage"] == {"steps": 2, "tool_calls": 1, "cost_microunits": 0}


def test_worker_managed_run_rejects_manual_state_and_usage_changes():
    headers, project = approved_project("dispatch-manual-bypass@example.com")
    queued = dispatch(headers, project)
    run_id = queued["run"]["id"]
    transition = request("POST", f"/api/v1/agent-runs/{run_id}/transitions", headers=headers, json={"action": "start"})
    usage = request("POST", f"/api/v1/agent-runs/{run_id}/usage", headers=headers, json={"steps": 1})
    assert transition.status_code == 409
    assert transition.json()["detail"]["code"] == "worker_managed_run"
    assert usage.status_code == 409


def test_incident_can_be_resolved_without_replay():
    headers, project = approved_project("incident-resolve@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        job = db.get(AgentDispatchJob, queued["job"]["id"])
        job.attempt_count = job.max_attempts
        run = db.get(AgentRun, job.run_id)
        mark_dispatch_failure(db, job, run, "runtime_unavailable")
    failed = request("GET", f"/api/v1/agent-runs/{queued['run']['id']}", headers=headers).json()
    assert failed["incident_category"] == "dispatch"
    incidents = request("GET", f"/api/v1/projects/{project['id']}/agent-incidents", headers=headers)
    assert incidents.status_code == 200
    assert incidents.json()[0]["reason_code"] == "runtime_unavailable"
    resolved = request("POST", f"/api/v1/agent-incidents/{failed['incident_id']}/resolve", headers=headers, json={"resolution_code": "reviewed_no_retry"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert request("POST", f"/api/v1/agent-incidents/{failed['incident_id']}/resolve", headers=headers, json={"resolution_code": "reviewed_no_retry"}).status_code == 409


def test_incident_replay_creates_linked_run_and_is_idempotent():
    headers, project = approved_project("incident-replay@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        job = db.get(AgentDispatchJob, queued["job"]["id"])
        job.attempt_count = job.max_attempts
        run = db.get(AgentRun, job.run_id)
        mark_dispatch_failure(db, job, run, "runtime_unavailable")
    failed = request("GET", f"/api/v1/agent-runs/{queued['run']['id']}", headers=headers).json()
    payload = {"revision": "original", "resolution_code": "configuration_fixed", "idempotency_key": "incident-replay-001"}
    first = request("POST", f"/api/v1/agent-incidents/{failed['incident_id']}/replay", headers=headers, json=payload)
    second = request("POST", f"/api/v1/agent-incidents/{failed['incident_id']}/replay", headers=headers, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["incident"]["status"] == "replayed"
    assert first.json()["dispatch"]["run"]["revision_id"] == queued["run"]["revision_id"]
    assert first.json()["dispatch"]["run"]["id"] == second.json()["dispatch"]["run"]["id"]
    assert first.json()["dispatch"]["job"]["status"] == "queued"


def test_incident_replay_current_revision_requires_its_own_pilot_approval():
    headers, project = approved_project("incident-revision-gate@example.com")
    queued = dispatch(headers, project)
    with get_session_factory()() as db:
        job = db.get(AgentDispatchJob, queued["job"]["id"])
        job.attempt_count = job.max_attempts
        run = db.get(AgentRun, job.run_id)
        mark_dispatch_failure(db, job, run, "runtime_unavailable")
    failed = request("GET", f"/api/v1/agent-runs/{queued['run']['id']}", headers=headers).json()
    current = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    changed_ir = current["current_revision"]["process_ir"]
    changed_ir["process"]["description"] = "Reviewed after incident"
    patch = request("POST", f"/api/v1/projects/{project['id']}/revisions", headers=headers, json={"base_revision_id": current["current_revision_id"], "patch": [{"op": "replace", "path": "/process/description", "value": "Reviewed after incident"}]})
    assert patch.status_code == 201
    replay = request("POST", f"/api/v1/agent-incidents/{failed['incident_id']}/replay", headers=headers, json={"revision": "current", "resolution_code": "process_revised", "idempotency_key": "incident-current-001"})
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "agent_incident_replay_blocked"
