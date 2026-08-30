import json
import subprocess
import sys
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from process_architect_api.exporters import generate_n8n_package
from process_architect_api.exporters.n8n import GENERATOR_VERSION, PythonCodePolicyError, SUPPORTED_TARGETS, export_n8n, source_hash
from process_architect_api.exporters.n8n.python_code import generate_numeric_threshold_source, verify_python_fixtures
from process_architect_api.exporters.n8n.python_service import dependency_artifacts
from process_architect_api.exporters.n8n.typescript_node import typescript_node_type
from process_architect_api.n8n_roundtrip import build_roundtrip_workflow
from process_architect_api.validation import validate_process_ir
from test_api import authorization, register, request


ROOT = Path(__file__).resolve().parents[3]
PROCESS = json.loads((ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(encoding="utf-8"))
SOURCE = '''def transform(items):
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    result = []
    for item in items:
        data = item.get("json")
        if not isinstance(data, dict) or "amount" not in data:
            raise ValueError("amount is required")
        result.append({"json": {**data, "approved": data["amount"] <= 1000}})
    return result
'''


def process_with_python() -> dict:
    process_ir = deepcopy(PROCESS)
    step = next(item for item in process_ir["steps"] if item["type"] == "system_task")
    rule = {
        "id": "rule_amount_limit",
        "name": "Automatic approval limit",
        "description": "Amounts up to 1000 are approved automatically.",
        "type": "deterministic",
        "source": "Approved finance policy v1",
        "appliesToStepIds": [step["id"]],
    }
    process_ir["businessRules"].append(rule)
    step["automationHint"] = {"target": "n8n", "nodeType": "n8n-nodes-base.code"}
    step["customLogic"] = {
        "strategy": "python_code",
        "reasonStandardNodesInsufficient": "The confirmed rule must transform every item and preserve its fields.",
        "businessRuleIds": [rule["id"]],
        "runtimeProfile": "n8n_native_python",
        "source": SOURCE,
        "inputExample": [{"json": {"amount": 750, "lead": "A"}}],
        "outputExample": [{"json": {"amount": 750, "lead": "A", "approved": True}}],
        "errorExample": [{"json": {"lead": "A"}}],
        "expectedError": "ValueError",
        "errorCases": ["Missing amount raises ValueError", "Non-list input raises TypeError"],
        "prohibitions": ["network", "filesystem", "credentials", "dynamic_code"],
        "generatorVersion": GENERATOR_VERSION,
        "contentHash": source_hash(SOURCE),
        "approvalStatus": "approved",
    }
    step["customLogic"]["executionEvidence"] = verify_python_fixtures(step["customLogic"])
    return process_ir


def process_with_python_service() -> dict:
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["strategy"] = "python_service"
    step["customLogic"]["runtimeProfile"] = "external_python_service"
    step["automationHint"] = {"target": "n8n", "nodeType": "n8n-nodes-base.httpRequest"}
    return process_ir


def process_with_typescript_node() -> dict:
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    spec = {"kind": "numeric_threshold", "inputField": "amount", "outputField": "approved", "operator": "<=", "threshold": 1000}
    step["customLogic"].update({
        "strategy": "typescript_node", "runtimeProfile": "native_typescript_node",
        "fallbackReason": "python_runtime_unavailable", "operationSpec": spec,
    })
    step["customLogic"]["executionEvidence"] = verify_python_fixtures(step["customLogic"])
    from process_architect_api.exporters.n8n.python_code import operation_spec_hash
    step["customLogic"]["executionEvidence"]["operationSpecHash"] = operation_spec_hash(spec)
    step["automationHint"] = {"target": "n8n", "nodeType": "apa.numericThreshold"}
    return process_ir


def test_deterministic_generator_emits_reviewable_threshold_code():
    source = generate_numeric_threshold_source("amount", "approved", "<=", 1000)
    logic = next(item["customLogic"] for item in process_with_python()["steps"] if item.get("customLogic"))
    logic.update({"source": source, "contentHash": source_hash(source)})
    evidence = verify_python_fixtures(logic)
    assert evidence["status"] == "passed"
    assert evidence["contentHash"] == source_hash(source)
    assert evidence["checks"] == ["expected_output", "deterministic_repeat", "expected_error", "timeout"]


def test_fixture_runner_rejects_wrong_expected_output():
    step = next(item for item in process_with_python()["steps"] if item.get("customLogic"))
    step["customLogic"]["outputExample"] = [{"json": {"approved": False}}]
    with pytest.raises(PythonCodePolicyError, match="python_fixture_result_mismatch"):
        verify_python_fixtures(step["customLogic"])


def test_fixture_runner_stops_non_terminating_code():
    step = next(item for item in process_with_python()["steps"] if item.get("customLogic"))
    step["customLogic"]["source"] = "def transform(items):\n    while True:\n        pass\n"
    with pytest.raises(PythonCodePolicyError, match="python_execution_(timeout|failed)"):
        verify_python_fixtures(step["customLogic"])


def test_export_requires_execution_evidence_for_exact_hash():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"].pop("executionEvidence")
    with pytest.raises(PythonCodePolicyError, match="python_execution_required"):
        export_n8n(process_ir, "2.32")


def test_legacy_reviewed_artifact_remains_exportable():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["generatorVersion"] = "python-code/1.0"
    step["customLogic"].pop("executionEvidence")
    workflow = export_n8n(process_ir, "2.32")
    assert next(item for item in workflow["nodes"] if item["id"] == step["id"])["parameters"]["language"] == "pythonNative"


def test_approved_python_compiles_for_every_n8n_minor(tmp_path):
    process_ir = process_with_python()
    assert validate_process_ir(process_ir).valid
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    for target in SUPPORTED_TARGETS:
        workflow = export_n8n(process_ir, target)
        node = next(item for item in workflow["nodes"] if item["id"] == step["id"])
        assert node["type"] == "n8n-nodes-base.code"
        assert node["typeVersion"] == 2
        assert node["parameters"] == {
            "mode": "runOnceForAllItems",
            "language": "pythonNative",
            "pythonCode": SOURCE.rstrip() + "\n\nreturn transform(_items)\n",
        }

        package = generate_n8n_package(process_ir, target, "en")
        with ZipFile(BytesIO(package)) as archive:
            root = f"custom-code/{step['id']}"
            assert f"{root}/main.py" in archive.namelist()
            contract = json.loads(archive.read(f"{root}/contract.json"))
            assert contract["contentHash"] == source_hash(SOURCE)
            extract_to = tmp_path / target
            archive.extractall(extract_to)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=extract_to / root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr


def test_python_service_compiles_to_authenticated_http_node_and_package(tmp_path):
    process_ir = process_with_python_service()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    for target in SUPPORTED_TARGETS:
        workflow = export_n8n(process_ir, target)
        node = next(item for item in workflow["nodes"] if item["id"] == step["id"])
        assert node["type"] == "n8n-nodes-base.httpRequest"
        assert node["typeVersion"] == 4.2
        assert node["parameters"]["url"] == "={{ $env.APA_PYTHON_SERVICE_URL + '/execute' }}"
        assert node["parameters"]["body"] == "={{ JSON.stringify({ items: $input.all() }) }}"
        assert node["parameters"]["options"]["timeout"] == 30000
        assert node["credentials"] == {"httpHeaderAuth": {"name": "APA Python service token"}}
        assert (node["retryOnFail"], node["maxTries"], node["waitBetweenTries"]) == (True, 3, 1000)

        package = generate_n8n_package(process_ir, target, "en")
        with ZipFile(BytesIO(package)) as archive:
            root = f"python-services/{step['id']}"
            names = set(archive.namelist())
            assert {f"{root}/Dockerfile", f"{root}/compose.yaml", f"{root}/app/main.py", f"{root}/app/logic.py", f"{root}/contract.json", f"{root}/requirements.lock", f"{root}/dependency-manifest.json", f"{root}/sbom.cdx.json"} <= names
            assert b"replace-with-a-long-random-token" in archive.read(f"{root}/.env.example")
            assert b"fastapi==0.141.1" in archive.read(f"{root}/requirements.lock")
            assert json.loads(archive.read(f"{root}/contract.json"))["dependencyProfile"] == "core"
            assert b"sk-" not in package
            extract_to = tmp_path / f"service-{target}"
            archive.extractall(extract_to)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            cwd=extract_to / root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr


def test_python_service_rejects_native_runtime_profile():
    process_ir = process_with_python_service()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["runtimeProfile"] = "n8n_native_python"
    with pytest.raises(PythonCodePolicyError, match="python_runtime_unsupported"):
        export_n8n(process_ir, "2.32")


def test_dependency_profiles_are_pinned_and_emit_cyclonedx():
    requirements, manifest_text, sbom_text = dependency_artifacts("dates")
    manifest = json.loads(manifest_text)
    sbom = json.loads(sbom_text)
    assert "python-dateutil==2.9.0.post0\n" in requirements
    assert "six==1.17.0\n" in requirements
    assert not any(">=" in line or "~=" in line for line in requirements.splitlines())
    assert manifest["profile"] == "dates"
    assert manifest["allowedModules"] == ["dateutil"]
    assert sbom["bomFormat"] == "CycloneDX"
    assert {item["name"] for item in sbom["components"]} >= {"fastapi", "python-dateutil", "six"}


def test_unknown_dependency_profile_fails_closed():
    with pytest.raises(ValueError, match="unknown Python service dependency profile"):
        dependency_artifacts("anything-from-pypi")


def test_service_import_requires_matching_dependency_profile():
    process_ir = process_with_python_service()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    source = '''from dateutil.parser import isoparse

def transform(items):
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    result = []
    for item in items:
        data = item.get("json")
        if not isinstance(data, dict) or "date" not in data:
            raise ValueError("date is required")
        result.append({"json": {**data, "year": isoparse(data["date"]).year}})
    return result
'''
    logic = step["customLogic"]
    logic.update({
        "source": source, "contentHash": source_hash(source), "dependencyProfile": "dates",
        "inputExample": [{"json": {"date": "2026-08-13"}}],
        "outputExample": [{"json": {"date": "2026-08-13", "year": 2026}}],
        "errorExample": [{"json": {}}], "expectedError": "ValueError",
    })
    logic["executionEvidence"] = verify_python_fixtures(logic)
    assert export_n8n(process_ir, "2.32")["nodes"]
    logic["dependencyProfile"] = "core"
    with pytest.raises(PythonCodePolicyError, match="python_policy_violation"):
        export_n8n(process_ir, "2.32")


def test_dependency_profile_change_invalidates_execution_evidence():
    process_ir = process_with_python_service()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["dependencyProfile"] = "dates"
    with pytest.raises(PythonCodePolicyError, match="python_execution_required"):
        export_n8n(process_ir, "2.32")


def test_typescript_fallback_compiles_and_exports_private_node(tmp_path):
    process_ir = process_with_typescript_node()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    for target in SUPPORTED_TARGETS:
        workflow = export_n8n(process_ir, target)
        node = next(item for item in workflow["nodes"] if item["id"] == step["id"])
        assert node["type"] == typescript_node_type(step["id"])
        assert node["parameters"] == {
            "operationSpecVersion": "numeric_threshold/1.0", "inputField": "amount",
            "outputField": "approved", "operator": "<=", "threshold": 1000,
        }
        assert "credentials" not in node
        package = generate_n8n_package(process_ir, target, "en")
        with ZipFile(BytesIO(package)) as archive:
            root = f"typescript-nodes/{step['id']}"
            contract = json.loads(archive.read(f"{root}/contract.json"))
            package_json = json.loads(archive.read(f"{root}/package.json"))
            assert contract["fallbackReason"] == "python_runtime_unavailable"
            assert contract["operationSpecHash"].startswith("sha256:")
            assert package_json["private"] is True
            assert package_json["peerDependencies"]["n8n-workflow"] == ">=2.30.0 <2.33.0"
            assert package_json["devDependencies"]["n8n-workflow"] == f"{target}.0"
            extract_to = tmp_path / f"typescript-{target}"
            archive.extractall(extract_to)
        completed = subprocess.run(["npm", "test"], cwd=extract_to / root, capture_output=True, text=True, check=False)
        assert completed.returncode == 0, completed.stderr


def test_typescript_fallback_requires_confirmed_reason():
    process_ir = process_with_typescript_node()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"].pop("fallbackReason")
    with pytest.raises(PythonCodePolicyError, match="typescript_fallback_reason_required"):
        export_n8n(process_ir, "2.32")


def test_typescript_operation_change_invalidates_evidence():
    process_ir = process_with_typescript_node()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["operationSpec"]["threshold"] = 2000
    with pytest.raises(PythonCodePolicyError, match="python_execution_required"):
        export_n8n(process_ir, "2.32")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"approvalStatus": "draft"}, "python_code_not_approved"),
        ({"contentHash": "sha256:" + "0" * 64}, "python_content_hash_mismatch"),
        ({"source": "import os\n\ndef transform(items):\n    return items\n"}, "python_content_hash_mismatch"),
        ({"prohibitions": ["network"]}, "python_prohibitions_incomplete"),
    ],
)
def test_python_export_fails_closed(change, code):
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"].update(change)
    with pytest.raises(PythonCodePolicyError, match=code):
        export_n8n(process_ir, "2.32")


def test_python_policy_rejects_forbidden_capabilities_with_current_hash():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    source = "import os\n\ndef transform(items):\n    os.system('echo unsafe')\n    return items\n"
    step["customLogic"]["source"] = source
    step["customLogic"]["contentHash"] = source_hash(source)
    with pytest.raises(PythonCodePolicyError, match="python_policy_violation"):
        export_n8n(process_ir, "2.32")


def test_python_policy_rejects_top_level_execution():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    source = "value = sum(range(10))\n\ndef transform(items):\n    return items\n"
    step["customLogic"]["source"] = source
    step["customLogic"]["contentHash"] = source_hash(source)
    with pytest.raises(PythonCodePolicyError, match="python_policy_violation"):
        export_n8n(process_ir, "2.32")


def test_api_returns_typed_error_for_unapproved_code():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    step["customLogic"]["approvalStatus"] = "draft"
    response = request("POST", "/api/v1/exports/n8n/2.32/package", headers=authorization(register()), json=process_ir)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "python_code_not_approved"


def test_validation_endpoint_normalizes_hash_without_saving():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    draft = {**step["customLogic"], "contentHash": "sha256:" + "0" * 64, "approvalStatus": "draft"}
    response = request(
        "POST",
        "/api/v1/exports/n8n/python-code/validate",
        headers=authorization(register()),
        json={"process_ir": process_ir, "step_id": step["id"], "target_minor": "2.32", "custom_logic": draft},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is True
    assert result["artifact"]["contentHash"] == source_hash(SOURCE)
    assert result["artifact"]["approvalStatus"] == "draft"
    assert set(result["checks"].values()) == {"passed"}


def test_validation_endpoint_returns_policy_details():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    draft = {**step["customLogic"], "source": "import os\n\ndef transform(items):\n    return items\n"}
    response = request(
        "POST",
        "/api/v1/exports/n8n/python-code/validate",
        headers=authorization(register()),
        json={"process_ir": process_ir, "step_id": step["id"], "target_minor": "2.32", "custom_logic": draft},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["valid"] is False
    assert result["checks"]["syntax"] == "passed"
    assert result["checks"]["policy"] == "failed"
    assert result["errors"][0]["code"] == "python_policy_violation"


def test_generation_endpoint_uses_only_sourced_step_rule():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    rule_id = step["customLogic"]["businessRuleIds"][0]
    response = request(
        "POST",
        "/api/v1/exports/n8n/python-code/generate",
        headers=authorization(register()),
        json={
            "process_ir": process_ir, "step_id": step["id"], "business_rule_id": rule_id,
            "reason": "Confirmed threshold needs a reusable transformation.", "input_field": "amount",
            "output_field": "approved", "operator": "<=", "threshold": 1000,
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["template"] == "numeric_threshold/1.0"
    assert result["artifact"]["approvalStatus"] == "draft"
    assert result["artifact"]["businessRuleIds"] == [rule_id]
    assert "value <= 1000.0" in result["artifact"]["source"]


def test_roundtrip_to_be_uses_reviewed_python_parameters():
    process_ir = process_with_python()
    step = next(item for item in process_ir["steps"] if item.get("customLogic"))
    source_ir = deepcopy(process_ir)
    source_ir["steps"] = [{**item, "customLogic": None} if item["id"] == step["id"] else item for item in source_ir["steps"]]
    source_ir["steps"] = [
        {**item, "automationHint": {"target": "n8n", "nodeType": "n8n-nodes-base.noOp"}}
        if item["id"] == step["id"] else item
        for item in source_ir["steps"]
    ]
    source_workflow = export_n8n(source_ir, "2.32")

    workflow, _ = build_roundtrip_workflow(
        process_ir,
        source_workflow=source_workflow,
        source_minor="2.32",
        target_minor="2.32",
        locale="en",
        perspective="to_be",
    )

    node = next(item for item in workflow["nodes"] if item["id"] == step["id"])
    assert node["type"] == "n8n-nodes-base.code"
    assert node["parameters"]["language"] == "pythonNative"
    assert node["parameters"]["pythonCode"].endswith("return transform(_items)\n")
