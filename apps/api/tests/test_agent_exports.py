import json
import subprocess
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from process_architect_api.exporters import calculate_agent_readiness, generate_agent_package
from test_api import authorization, register, request


ROOT = Path(__file__).resolve().parents[3]
PROCESS = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def agent_process() -> dict:
    process_ir = deepcopy(PROCESS)
    task = next(step for step in process_ir["steps"] if step["type"] == "system_task")
    task["execution"] = {
        "performedBy": "ai",
        "autonomy": "supervised",
        "approvalRequired": True,
        "restrictions": ["Do not change process state directly"],
    }
    task["systemId"] = "system_website"
    return process_ir


def configured_agent_process() -> dict:
    process_ir = agent_process()
    task = next(step for step in process_ir["steps"] if step["execution"]["performedBy"] == "ai")
    task["agentConfig"] = {
        "knowledgeSources": ["CRM policy v3"],
        "allowedStateIds": [],
        "stopConditions": ["Required data is missing"],
        "auditEvents": ["tool_call", "human_review", "error"],
        "escalation": {"missingSource": "process owner", "conflictingSources": "compliance owner", "lowConfidence": "human reviewer", "riskyAction": "security owner"},
    }
    return process_ir


def test_agent_contract_follows_book_control_boundaries(tmp_path):
    process_ir = agent_process()
    for target in ("openclaw", "hermes", "langgraph", "crewai", "agno"):
        package = generate_agent_package(process_ir, target, "ru")
        assert package == generate_agent_package(process_ir, target, "ru")
        with ZipFile(BytesIO(package)) as archive:
            names = set(archive.namelist())
            assert {
                "agent-contract.json",
                "agent-readiness.json",
                "contracts/tool-permissions.json",
                "contracts/architecture-decision.json",
                "contracts/inter-agent-message.schema.json",
                "contracts/python-runtime.schema.json",
                "docs/agent-cards.md",
                "docs/architecture.md",
                "evals/scenarios.json",
                "harness/guard.py",
                "harness/tests/test_guard.py",
                "runtime_core/contract.py",
                "runtime_core/tests/test_contract.py",
            } <= names
            contract = json.loads(archive.read("agent-contract.json"))
            permissions = json.loads(archive.read("contracts/tool-permissions.json"))
            evals = json.loads(archive.read("evals/scenarios.json"))
            assert contract["methodology"] == "Processes for People and AI"
            assert contract["contractVersion"] == "1.1"
            assert contract["orchestration"]["stateOwner"] == "workflow_or_backend"
            assert contract["orchestration"]["agentMayChangeStateDirectly"] is False
            assert contract["architectureDecision"]["selectedTopology"] == "single_agent"
            assert contract["architectureDecision"]["activationPolicy"] == "explicit_human_approval"
            assert permissions["default"] == "deny"
            assert permissions["stateOwner"] == "workflow_or_backend"
            assert permissions["agentMayChangeStateDirectly"] is False
            assert permissions["permissions"]
            assert all(permission["agentMayCall"] for permission in permissions["permissions"])
            assert all(permission["allowedStates"] for permission in permissions["permissions"])
            assert {item["id"] for item in evals["scenarios"]} >= {
                "happy_path", "missing_required_data", "conflicting_sources", "approval_required"
            }
            if target == "openclaw":
                assert "openclaw/workspace/AGENTS.md" in names
                assert "openclaw/openclaw.config.fragment.json5" in names
            elif target == "hermes":
                assert "hermes/project/.hermes.md" in names
                assert "hermes/config.fragment.yaml" in names
            else:
                assert f"{target}/adapter/app.py" in names
                assert f"{target}/requirements.lock" in names
                assert f"{target}/runtime_core/contract.py" in names
                assert f"{target}/.env.example" in names
            extract_to = tmp_path / target
            archive.extractall(extract_to)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "harness/tests"],
            cwd=extract_to,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        runtime_completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "runtime_core/tests"],
            cwd=extract_to,
            capture_output=True,
            text=True,
            check=False,
        )
        assert runtime_completed.returncode == 0, runtime_completed.stderr
        if target in {"langgraph", "crewai", "agno"}:
            compiled = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", "adapter", "runtime_core"],
                cwd=extract_to / target,
                capture_output=True,
                text=True,
                check=False,
            )
            assert compiled.returncode == 0, compiled.stderr


def test_agent_contract_compiles_visual_editor_configuration():
    process_ir = configured_agent_process()
    with ZipFile(BytesIO(generate_agent_package(process_ir, "openclaw"))) as archive:
        contract = json.loads(archive.read("agent-contract.json"))
    agent = contract["agents"][0]
    assert agent["knowledgeSources"] == ["CRM policy v3"]
    assert agent["stopConditions"] == ["Required data is missing"]
    assert agent["escalation"]["conflictingSources"] == "compliance owner"
    assert contract["observability"]["events"] == ["agent_started", "error", "human_review", "tool_call"]


def test_agent_config_rejects_unknown_process_state():
    process_ir = configured_agent_process()
    task = next(step for step in process_ir["steps"] if step["execution"]["performedBy"] == "ai")
    task["agentConfig"]["allowedStateIds"] = ["state_unknown"]
    from process_architect_api.validation import validate_process_ir
    validation = validate_process_ir(process_ir)
    assert not validation.valid
    assert "unknown_agent_allowed_state" in {item.code for item in validation.issues}


def test_multi_agent_candidate_remains_single_agent_until_reviewed():
    process_ir = agent_process()
    second = next(step for step in process_ir["steps"] if step.get("systemId") == "system_crm")
    second["execution"] = {
        "performedBy": "ai",
        "autonomy": "supervised",
        "approvalRequired": True,
        "restrictions": ["Do not change process state directly"],
    }
    with ZipFile(BytesIO(generate_agent_package(process_ir, "openclaw"))) as archive:
        contract = json.loads(archive.read("agent-contract.json"))
    decision = contract["architectureDecision"]
    assert decision["recommendedTopology"] == "multi_agent"
    assert decision["selectedTopology"] == "single_agent"
    assert decision["status"] == "review_required"
    assert decision["activationPolicy"] == "explicit_human_approval"


def test_agent_readiness_blocks_process_without_explicit_ai_role():
    process_ir = deepcopy(PROCESS)
    for step in process_ir["steps"]:
        if step["execution"]["performedBy"] == "ai":
            step["execution"]["performedBy"] = "human"
            step["execution"]["autonomy"] = "manual"
    readiness = calculate_agent_readiness(process_ir)
    assert readiness["agentReady"] is False
    assert "agent_role_not_defined" in readiness["blockers"]


def test_community_keeps_agent_mode_but_blocks_agent_package_export():
    tokens = register()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    created = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Agent process",
            "process_ir": agent_process(),
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["target_mode"] == "process"

    changed = request(
        "PATCH",
        f"/api/v1/projects/{project['id']}/target-mode",
        headers=headers,
        json={"target_mode": "agent"},
    )
    assert changed.status_code == 200
    assert changed.json()["target_mode"] == "agent"
    readiness = request(
        "GET", f"/api/v1/projects/{project['id']}/agent-readiness", headers=headers
    )
    assert readiness.status_code == 200
    assert readiness.json()["scope"] == "agent_deployment"

    exported = request(
        "POST",
        "/api/v1/exports/agent/openclaw/package?locale=ru",
        headers=headers,
        json=agent_process(),
    )
    assert exported.status_code == 403
    assert exported.json()["detail"]["entitlementId"] == "export.agent"

    python_export = request(
        "POST",
        "/api/v1/exports/agent/agno/package?locale=ru",
        headers=headers,
        json=agent_process(),
    )
    assert python_export.status_code == 403
    assert python_export.json()["detail"]["entitlementId"] == "export.agent"


def test_project_can_be_created_directly_in_agent_mode():
    tokens = register()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()

    created = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Agent template project",
            "process_ir": agent_process(),
            "target_mode": "agent",
        },
    )

    assert created.status_code == 201
    assert created.json()["target_mode"] == "agent"
