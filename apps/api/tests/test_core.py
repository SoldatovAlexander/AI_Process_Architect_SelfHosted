import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from process_architect_api.analyst import extract_process_ir
from process_architect_api.exporters import (
    SUPPORTED_APP_TARGETS,
    generate_app_spec,
    generate_bpmn,
    generate_drawio,
    generate_spec,
)
from process_architect_api.exporters.n8n import SUPPORTED_TARGETS, export_n8n
from process_architect_api.process_ir import upgrade_process_ir
from process_architect_api.validation import validate_process_ir


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def test_baseline_extracts_lead_details():
    result = extract_process_ir(
        "Новая заявка становится лидом. При оценке 80 создаём сделку в Bitrix24 "
        "и уведомляем менеджера в Telegram."
    )
    assert result["analysis"]["scenarioId"] == "lead-intake"
    assert result["analysis"]["detectedThreshold"] == 80
    assert validate_process_ir(result["process_ir"]).valid is True


def test_baseline_rejects_unsupported_description():
    with pytest.raises(ValueError, match="not recognized"):
        extract_process_ir("Каждое утро сотрудник формирует отчёт о доступности серверов.")


def test_spec_contains_flow_and_open_questions():
    spec = generate_spec(LEAD, validate_process_ir(LEAD))
    assert spec.startswith("# Lead Intake - Implementation Spec")
    assert "## Flow" in spec
    assert "## Data" in spec
    assert "| email | string | yes | website_form |" in spec
    assert "Which CRM pipeline" in spec
    assert "## Process Passport" in spec
    assert "## States And Lifecycle" in spec
    assert "## Business Rules" in spec
    assert "## Human, System And AI Boundaries" in spec


def test_generates_target_specific_application_specifications():
    validation = validate_process_ir(LEAD)
    assert SUPPORTED_APP_TARGETS == (
        "cursor",
        "codex",
        "google_ai_studio",
        "bolt",
        "generic",
    )
    for target in SUPPORTED_APP_TARGETS:
        spec = generate_app_spec(LEAD, validation, target, "ru")
        assert "ТЗ на создание приложения" in spec
        assert "## Начальный промпт" in spec
        assert "## Функциональные требования" in spec
        assert "## Паспорт и границы процесса" in spec
        assert "## Бизнес-правила" in spec
        assert "## Границы человека, системы и ИИ" in spec
        assert "FR-01" in spec
        assert "`.env.example`" in spec
        assert "Работоспособный исходный код" in spec
    assert "`.cursor/rules`" in generate_app_spec(LEAD, validation, "cursor", "ru")
    assert "Build mode" in generate_app_spec(LEAD, validation, "google_ai_studio", "ru")
    assert "Preview" in generate_app_spec(LEAD, validation, "bolt", "ru")


def test_exports_each_supported_n8n_minor():
    assert SUPPORTED_TARGETS == ("2.32", "2.31", "2.30")
    for target in SUPPORTED_TARGETS:
        workflow = export_n8n(LEAD, target)
        assert workflow["id"] == "3f9bbea6-ddac-5136-ac52-9d0a606be4f3"
        assert workflow["meta"]["targetN8nMinor"] == target
        assert len(workflow["nodes"]) == len(LEAD["steps"])
        assert workflow["connections"]["Is lead qualified?"]["main"][1][0]["node"] == "Lead archived"


def test_n8n_export_assigns_unique_names_and_connections_to_duplicate_titles():
    process_ir = deepcopy(LEAD)
    process_ir["steps"][2]["title"] = process_ir["steps"][1]["title"]

    workflow = export_n8n(process_ir, "2.32")

    names = [node["name"] for node in workflow["nodes"]]
    assert len(names) == len(set(names))
    assert f"{process_ir['steps'][1]['title']} (2)" in names
    connection_targets = {
        connection["node"]
        for source in workflow["connections"].values()
        for output in source["main"]
        for connection in output
    }
    assert f"{process_ir['steps'][1]['title']} (2)" in connection_targets


def test_rejects_unsupported_n8n_minor():
    with pytest.raises(ValueError, match="Unsupported n8n target"):
        export_n8n(LEAD, "2.29")


def test_generates_parseable_bpmn_with_diagram_information():
    bpmn = generate_bpmn(LEAD)
    root = ET.fromstring(bpmn)
    namespaces = {
        "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
        "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    }
    assert root.find("bpmn:process", namespaces) is not None
    assert len(root.findall(".//bpmn:sequenceFlow", namespaces)) == len(LEAD["edges"])
    assert root.find(".//bpmndi:BPMNDiagram", namespaces) is not None


def test_generates_editable_drawio_bpmn_diagram():
    drawio = generate_drawio(LEAD)
    root = ET.fromstring(drawio)

    assert root.tag == "mxfile"
    assert root.find("./diagram/mxGraphModel/root") is not None
    vertices = root.findall(".//mxCell[@vertex='1']")
    edges = root.findall(".//mxCell[@edge='1']")
    assert len(vertices) == len(LEAD["steps"])
    assert len(edges) == len(LEAD["edges"])
    assert any("rhombus" in cell.attrib["style"] for cell in vertices)
    boxes = []
    for cell in vertices:
        geometry = cell.find("mxGeometry")
        assert geometry is not None
        boxes.append(
            (
                float(geometry.attrib["x"]),
                float(geometry.attrib["y"]),
                float(geometry.attrib["width"]),
                float(geometry.attrib["height"]),
            )
        )
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            separated = (
                first[0] + first[2] <= second[0]
                or second[0] + second[2] <= first[0]
                or first[1] + first[3] <= second[1]
                or second[1] + second[3] <= first[1]
            )
            assert separated
    edge_labels = [cell.attrib["value"] for cell in edges]
    assert all("_" not in label for label in edge_labels)
    assert all("== True" not in label and "== False" not in label for label in edge_labels)
    assert any(edge.findall("./mxGeometry/Array/mxPoint") for edge in edges)


def test_schema_invalid_nested_values_return_issues_without_semantic_crash():
    malformed = deepcopy(LEAD)
    malformed["steps"][0]["outputs"] = [{"id": "data_lead"}]

    result = validate_process_ir(malformed)

    assert result.valid is False
    assert result.counts.errors >= 1
    assert all(issue.code == "schema_validation" for issue in result.issues)


def test_upgrades_legacy_ir_without_mutating_it_and_links_decision_rules():
    legacy = deepcopy(LEAD)
    legacy["schemaVersion"] = "0.1"
    legacy.pop("passport")
    legacy.pop("states")
    legacy.pop("stateTransitions")
    legacy.pop("businessRules")
    for step in legacy["steps"]:
        step.pop("execution")
    for edge in legacy["edges"]:
        edge.pop("ruleIds")

    upgraded = upgrade_process_ir(legacy)

    assert legacy["schemaVersion"] == "0.1"
    assert upgraded["schemaVersion"] == "0.2"
    assert upgraded["passport"]["ownerActorId"]
    assert all("execution" in step for step in upgraded["steps"])
    assert upgraded["businessRules"]
    assert all(edge["ruleIds"] for edge in upgraded["edges"] if edge["condition"])
    assert validate_process_ir(upgraded).valid


def test_execution_defaults_are_consistent_and_supervised_work_requires_approval():
    legacy = deepcopy(LEAD)
    legacy["schemaVersion"] = "0.1"
    legacy.pop("passport")
    legacy.pop("states")
    legacy.pop("stateTransitions")
    legacy.pop("businessRules")
    for step in legacy["steps"]:
        step.pop("execution")
    for edge in legacy["edges"]:
        edge.pop("ruleIds")

    upgraded = upgrade_process_ir(legacy)
    system_steps = [
        step
        for step in upgraded["steps"]
        if step["type"] == "system_task" and step["operation"]["kind"] != "ai_task"
    ]
    ai_step = next(step for step in upgraded["steps"] if step["operation"]["kind"] == "ai_task")
    automatic_decision = next(step for step in upgraded["steps"] if step["type"] == "decision")

    assert all(step["execution"]["autonomy"] == "autonomous" for step in system_steps)
    assert ai_step["execution"] == {
        "performedBy": "ai",
        "autonomy": "assist",
        "approvalRequired": True,
        "restrictions": [],
    }
    assert automatic_decision["execution"]["performedBy"] == "system"
    assert automatic_decision["execution"]["autonomy"] == "autonomous"

    inconsistent = deepcopy(upgraded)
    inconsistent["steps"][1]["execution"]["autonomy"] = "supervised"
    inconsistent["steps"][1]["execution"]["approvalRequired"] = False
    assert validate_process_ir(inconsistent).valid is False


def test_invalid_legacy_nested_values_are_reported_without_upgrade_crash():
    legacy = deepcopy(LEAD)
    legacy["schemaVersion"] = "0.1"
    legacy["edges"][0]["condition"] = "invalid"

    result = validate_process_ir(legacy)

    assert result.valid is False
    assert any(issue.code == "schema_validation" for issue in result.issues)
