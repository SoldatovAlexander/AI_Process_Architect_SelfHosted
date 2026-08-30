from process_architect_api.config import get_settings
from test_api import authorization, request
from test_agent_exports import agent_process


def create_ready_project(email: str) -> tuple[dict, dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    process_ir = agent_process()
    task = next(item for item in process_ir["steps"] if item.get("execution", {}).get("performedBy") == "ai")
    task["inputs"] = task.get("inputs") or [process_ir["dataObjects"][0]["id"]]
    task["outputs"] = task.get("outputs") or [process_ir["dataObjects"][0]["id"]]
    task["agentConfig"] = {
        "knowledgeSources": ["Approved CRM lead policy"], "allowedStateIds": [],
        "stopConditions": ["Required input is missing", "Human approval is denied"],
        "auditEvents": ["tool_call", "human_review", "escalation", "error"],
        "escalation": {"missingSource": "process owner", "conflictingSources": "process owner", "lowConfidence": "human reviewer", "riskyAction": "human reviewer"},
    }
    for question in process_ir["openQuestions"]:
        question["blocksAutomationReady"] = False
    project = request("POST", "/api/v1/projects", headers=headers, json={"workspace_id": user["workspaces"][0]["workspace_id"], "name": "Pilot-ready agent", "target_mode": "agent", "process_ir": process_ir}).json()
    return headers, project


def gate(headers: dict, project: dict, runtime: str = "openclaw") -> dict:
    response = request("GET", f"/api/v1/projects/{project['id']}/agent-pilot-gate?runtime={runtime}", headers=headers)
    assert response.status_code == 200
    return response.json()


def submit(headers: dict, project: dict, pilot_gate: dict, *, passed: bool = True, runtime: str = "openclaw", cost: int = 420, duration: int = 1250) -> dict:
    response = request("POST", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=headers, json={
        "runtime": runtime,
        "results": [{"scenario_id": scenario_id, "passed": passed, "reason_code": None if passed else "assertion_failed"} for scenario_id in pilot_gate["required_scenarios"]],
        "duration_ms": duration,
        "cost_microunits": cost,
    })
    assert response.status_code == 201
    return response.json()


def test_pilot_gate_requires_evidence_and_explicit_baseline_approval():
    headers, project = create_ready_project("agent-eval-owner@example.com")
    initial = gate(headers, project)
    assert initial["status"] == "evaluation_required"
    assert initial["pilot_ready"] is False
    assert {"happy_path", "missing_required_data", "conflicting_sources", "approval_required"} <= set(initial["required_scenarios"])

    evaluation = submit(headers, project, initial)
    waiting = gate(headers, project)
    assert waiting["status"] == "approval_required"
    assert waiting["latest_evaluation"]["passed_count"] == waiting["latest_evaluation"]["total_count"]
    assert "model" not in str(waiting).lower()

    approved = request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": evaluation["id"], "action": "approve", "reason_code": "pilot_approved"})
    assert approved.status_code == 201
    ready = gate(headers, project)
    assert ready["status"] == "ready"
    assert ready["pilot_ready"] is True


def test_failed_evaluation_blocks_pilot_and_incomplete_suite_is_rejected():
    headers, project = create_ready_project("agent-regression-owner@example.com")
    initial = gate(headers, project)
    incomplete = request("POST", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=headers, json={"runtime": "openclaw", "results": [{"scenario_id": initial["required_scenarios"][0], "passed": True}]})
    assert incomplete.status_code == 409
    submit(headers, project, initial, passed=False)
    regressed = gate(headers, project)
    assert regressed["status"] == "regression"
    assert regressed["blockers"] == ["evaluation_failed"]


def test_model_change_requires_new_baseline_and_supports_rollback(monkeypatch):
    headers, project = create_ready_project("agent-model-change@example.com")
    initial = gate(headers, project)
    first = submit(headers, project, initial)
    request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": first["id"]})

    monkeypatch.setenv("DEEPSEEK_MODEL", "changed-model-for-test")
    get_settings.cache_clear()
    second = submit(headers, project, gate(headers, project))
    changed = gate(headers, project)
    assert changed["status"] == "model_change"
    assert "changed-model-for-test" not in str(changed)

    rolled_back = request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": first["id"], "action": "rollback", "reason_code": "model_regression"})
    assert rolled_back.status_code == 201
    after_rollback = gate(headers, project)
    assert after_rollback["status"] == "model_change"
    assert after_rollback["latest_evaluation"]["id"] == second["id"]


def test_evaluation_access_isolated_and_non_agent_project_rejected():
    headers, project = create_ready_project("agent-eval-isolation@example.com")
    initial = gate(headers, project)
    other = request("POST", "/api/v1/auth/register", json={"email": "agent-eval-outsider@example.com", "password": "correct-horse-battery-staple"}).json()
    assert request("GET", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=authorization(other)).status_code == 404
    request("PATCH", f"/api/v1/projects/{project['id']}/target-mode", headers=headers, json={"target_mode": "process"})
    response = request("POST", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=headers, json={"runtime": "openclaw", "results": [{"scenario_id": item, "passed": True} for item in initial["required_scenarios"]]})
    assert response.status_code == 409


def test_cost_or_duration_regression_blocks_a_functionally_successful_run():
    headers, project = create_ready_project("agent-cost-regression@example.com")
    initial = gate(headers, project)
    baseline = submit(headers, project, initial, cost=100, duration=1000)
    request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": baseline["id"]})
    submit(headers, project, gate(headers, project), cost=126, duration=1000)
    regressed = gate(headers, project)
    assert regressed["status"] == "regression"
    assert regressed["blockers"] == ["evaluation_cost_regression"]
