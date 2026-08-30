import json
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from mvp_scenarios import MVP_SCENARIOS
from process_architect_api.validation import validate_process_ir
from test_api import authorization, register, request


EXPORT_TARGETS = (
    "spec",
    "bpmn_drawio",
    "n8n_2_32",
    "n8n_2_31",
    "n8n_2_30",
    "agent_openclaw",
    "agent_hermes",
)


@pytest.mark.parametrize("export_target", EXPORT_TARGETS)
@pytest.mark.parametrize("scenario", MVP_SCENARIOS, ids=lambda item: item.id)
def test_mvp_scenario_export_matrix(scenario, export_target):
    process_ir = scenario.load_process_ir()
    validation = validate_process_ir(process_ir)
    assert validation.valid, validation.model_dump()
    headers = authorization(register())

    if export_target == "spec":
        response = request(
            "POST", "/api/v1/exports/app-spec/codex?locale=ru", headers=headers, json=process_ir
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert "app-spec-codex.md" in response.headers["content-disposition"]
        content = response.text
        assert process_ir["process"]["name"] in content
        assert "## Начальный промпт" in content
        assert "## Функциональные требования" in content
        assert "## Критерии приёмки" in content
        return

    if export_target == "bpmn_drawio":
        response = request("POST", "/api/v1/exports/drawio", headers=headers, json=process_ir)
        assert response.status_code == 200
        assert "application/vnd.jgraph.mxfile" in response.headers["content-type"]
        assert "-bpmn.drawio" in response.headers["content-disposition"]
        root = ET.fromstring(response.content)
        assert root.tag == "mxfile"
        assert len(root.findall(".//mxCell[@vertex='1']")) == len(process_ir["steps"])
        assert len(root.findall(".//mxCell[@edge='1']")) == len(process_ir["edges"])
        if any(step["type"] == "decision" for step in process_ir["steps"]):
            assert any(
                "rhombus" in cell.attrib.get("style", "")
                for cell in root.findall(".//mxCell[@vertex='1']")
            )
        return

    if export_target.startswith("n8n_"):
        target = export_target.removeprefix("n8n_").replace("_", ".")
        response = request(
            "POST",
            f"/api/v1/exports/n8n/{target}/package?locale=ru&includeGeneralGuide=true",
            headers=headers,
            json=process_ir,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert f"n8n-{target}.zip" in response.headers["content-disposition"]
        with ZipFile(BytesIO(response.content)) as archive:
            workflow_name = f"workflow-n8n-{target}.json"
            assert {"README.md", "N8N_BEGINNER_GUIDE.md", "PROCESS_SETUP.md", workflow_name} == set(archive.namelist())
            workflow = json.loads(archive.read(workflow_name))
            assert workflow["meta"]["targetN8nMinor"] == target
            assert len(workflow["nodes"]) == len(process_ir["steps"])
            assert process_ir["process"]["name"] in archive.read("PROCESS_SETUP.md").decode("utf-8")
        return

    runtime = export_target.removeprefix("agent_")
    response = request(
        "POST",
        f"/api/v1/exports/agent/{runtime}/package?locale=ru",
        headers=headers,
        json=process_ir,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert f"agent-{runtime}.zip" in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        contract = json.loads(archive.read("agent-contract.json"))
        readiness = json.loads(archive.read("agent-readiness.json"))
        assert contract["process"]["id"] == process_ir["process"]["id"]
        assert contract["orchestration"]["stateOwner"] == "workflow_or_backend"
        assert "blockers" in readiness
        assert "evals/scenarios.json" in names
        assert "contracts/tool-permissions.json" in names
        assert any(name.startswith(f"{runtime}/") for name in names)
