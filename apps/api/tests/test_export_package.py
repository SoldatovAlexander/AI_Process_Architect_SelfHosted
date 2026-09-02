import json
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from process_architect_api.exporters import (
    generate_export_package,
    generate_n8n_package,
    generate_resource_spec,
)
from process_architect_api.exporters.n8n import SUPPORTED_TARGETS
from process_architect_api.validation import validate_process_ir
from test_api import authorization, register, request


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in sorted((ROOT / "02_architecture" / "examples").glob("*.process-ir.json"))
]


def test_generates_resource_spec_for_every_system_in_all_pilots():
    for process_ir in FIXTURES:
        for system in process_ir["systems"]:
            spec = generate_resource_spec(process_ir, system["id"], "2.32")
            assert spec.startswith(f"# {system['name']} - Resource Specification")
            assert f"credential_{system['id']}" in spec
            assert "never place secret values" in spec


def test_export_package_is_deterministic_and_complete_for_all_targets():
    process_ir = FIXTURES[1]
    validation = validate_process_ir(process_ir)
    for target in SUPPORTED_TARGETS:
        first = generate_export_package(process_ir, validation, target)
        second = generate_export_package(process_ir, validation, target)
        assert first == second
        with ZipFile(BytesIO(first)) as archive:
            names = set(archive.namelist())
            expected_resources = {
                f"spec/resources/{system['id']}.md"
                for system in process_ir["systems"]
            }
            assert expected_resources <= names
            assert {
                "manifest.json",
                "process.bpmn",
                "spec/process-overview.md",
                f"workflow-n8n-{target}.json",
            } <= names
            manifest = json.loads(archive.read("manifest.json"))
            workflow = json.loads(archive.read(f"workflow-n8n-{target}.json"))
            ET.fromstring(archive.read("process.bpmn"))
            assert manifest["n8n"]["targetMinor"] == target
            assert manifest["files"] == sorted(names)
            assert workflow["meta"]["targetN8nMinor"] == target


def test_authenticated_package_endpoint_returns_zip():
    headers = authorization(register())
    response = request(
        "POST",
        "/api/v1/exports/package/2.32",
        headers=headers,
        json=FIXTURES[0],
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        assert "manifest.json" in archive.namelist()


def test_n8n_package_separates_general_and_process_specific_instructions():
    package = generate_n8n_package(FIXTURES[0], "2.32", "ru")

    with ZipFile(BytesIO(package)) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "N8N_BEGINNER_GUIDE.md",
            "PROCESS_SETUP.md",
            "workflow-n8n-2.32.json",
        }
        workflow = json.loads(archive.read("workflow-n8n-2.32.json"))
        index = archive.read("README.md").decode("utf-8")
        beginner_guide = archive.read("N8N_BEGINNER_GUIDE.md").decode("utf-8")
        process_guide = archive.read("PROCESS_SETUP.md").decode("utf-8")
        assert workflow["meta"]["targetN8nMinor"] == "2.32"
        assert "N8N_BEGINNER_GUIDE.md" in index
        assert "PROCESS_SETUP.md" in index
        assert "n8n с нуля" in beginner_guide
        assert "Import from File" in beginner_guide
        assert "n8nio/n8n:2.32.7" in beginner_guide
        assert FIXTURES[0]["process"]["name"] in process_guide
        assert "Настройка узлов" in process_guide
        assert "Import from File" not in process_guide


def test_n8n_package_can_omit_general_guide_without_losing_process_setup():
    package = generate_n8n_package(FIXTURES[0], "2.30", "en", False)

    with ZipFile(BytesIO(package)) as archive:
        assert set(archive.namelist()) == {
            "README.md",
            "PROCESS_SETUP.md",
            "workflow-n8n-2.30.json",
        }
        index = archive.read("README.md").decode("utf-8")
        assert "general guide is not included" in index
        assert "PROCESS_SETUP.md" in index


@pytest.mark.parametrize(
    ("target_minor", "tested_patch"),
    [("2.32", "2.32.7"), ("2.31", "2.31.7"), ("2.30", "2.30.8")],
)
def test_n8n_instructions_follow_selected_target(target_minor, tested_patch):
    package = generate_n8n_package(FIXTURES[0], target_minor, "en")

    with ZipFile(BytesIO(package)) as archive:
        beginner_guide = archive.read("N8N_BEGINNER_GUIDE.md").decode("utf-8")
        process_guide = archive.read("PROCESS_SETUP.md").decode("utf-8")
        workflow_name = f"workflow-n8n-{target_minor}.json"
        workflow = json.loads(archive.read(workflow_name))
        assert workflow_name in archive.namelist()
        assert f"targets **{target_minor}**" in beginner_guide
        assert f"n8nio/n8n:{tested_patch}" in beginner_guide
        assert f"- n8n: `{target_minor}`" in process_guide
        assert f"- Tested patch: `{tested_patch}`" in process_guide
        assert workflow["meta"]["targetN8nMinor"] == target_minor
        assert workflow["meta"]["testedPatch"] == tested_patch


def test_authenticated_n8n_package_endpoint_returns_zip():
    headers = authorization(register())
    response = request(
        "POST",
        "/api/v1/exports/n8n/2.31/package?locale=es&includeGeneralGuide=false",
        headers=headers,
        json=FIXTURES[0],
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "n8n-2.31.zip" in response.headers["content-disposition"]
    with ZipFile(BytesIO(response.content)) as archive:
        assert "N8N_BEGINNER_GUIDE.md" not in archive.namelist()
        assert "La guía general no está incluida" in archive.read("README.md").decode("utf-8")
        assert "Configurar" in archive.read("PROCESS_SETUP.md").decode("utf-8")
