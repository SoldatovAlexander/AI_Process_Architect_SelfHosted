import json
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from process_architect_api.n8n_importer import canonical_workflow, import_n8n_workflow
from process_architect_api.n8n_roundtrip import build_roundtrip_workflow
from test_api import authorization, request


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = json.loads((ROOT / "artifacts/n8n/lead-intake-2.32.json").read_text(encoding="utf-8"))


def _register(email: str) -> tuple[dict, dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    return headers, request("GET", "/api/v1/auth/me", headers=headers).json()


@pytest.mark.parametrize("minor", ["2.32", "2.31", "2.30"])
def test_import_creates_as_is_project_and_preserves_source(minor: str):
    headers, user = _register(f"n8n-import-{minor}@example.com")
    workflow = deepcopy(WORKFLOW)
    workflow["meta"]["targetN8nMinor"] = minor
    workflow["nodes"][3]["credentials"] = {"httpHeaderAuth": {"id": "cred-1", "name": "CRM production"}}
    workflow["nodes"].append({"id": "custom", "name": "Private connector", "type": "community.privateNode", "typeVersion": 1, "position": [0, 0], "parameters": {}})
    workflow["connections"]["Qualified lead handled"] = {"main": [[{"node": "Private connector", "type": "main", "index": 0}]]}

    response = request("POST", "/api/v1/n8n-imports", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"], "workflow": workflow, "source_minor": minor, "locale": "ru",
    })
    assert response.status_code == 201
    result = response.json()
    assert result["project"]["current_revision"]["source"] == "import"
    assert result["project"]["current_revision"]["process_ir"]["classification"]["status"] == "proposed"
    assert result["diagnostics"]["unknownNodes"] == [{"name": "Private connector", "type": "community.privateNode"}]
    assert result["diagnostics"]["credentialReferences"][0]["names"] == ["CRM production"]
    _, expected_hash = canonical_workflow(workflow)
    assert result["source_sha256"] == expected_hash

    artifact = request("GET", f"/api/v1/n8n-imports/{result['artifact_id']}", headers=headers)
    assert artifact.status_code == 200
    assert artifact.json()["source_workflow"] == workflow


def test_import_rejects_inline_secrets_and_invalid_workflow():
    headers, user = _register("n8n-import-invalid@example.com")
    workflow = deepcopy(WORKFLOW)
    workflow["nodes"][0]["parameters"]["apiToken"] = "secret-value"
    rejected = request("POST", "/api/v1/n8n-imports", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"], "workflow": workflow, "source_minor": "2.32", "locale": "ru",
    })
    assert rejected.status_code == 422
    assert "inline secrets" in rejected.json()["detail"]["message"]

    invalid = request("POST", "/api/v1/n8n-imports", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"], "workflow": {"name": "Empty", "nodes": [], "connections": {}}, "source_minor": "2.32", "locale": "ru",
    })
    assert invalid.status_code == 422


def test_import_completion_keeps_as_is_and_accepts_separate_to_be_revision():
    headers, user = _register("n8n-as-is-to-be@example.com")
    imported = request("POST", "/api/v1/n8n-imports", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"], "workflow": WORKFLOW, "source_minor": "2.32", "locale": "ru",
    }).json()
    project = imported["project"]
    as_is_revision_id = project["current_revision_id"]
    assert project["current_revision"]["perspective"] == "as_is"

    session_response = request(
        "POST",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
        json={"mode": "as_is_completion", "locale": "ru"},
    )
    assert session_response.status_code == 201
    session = session_response.json()
    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert detail["started_from_revision_id"] == as_is_revision_id
    assert detail["messages"][0]["prompt_version"] == "as-is-completion-v1"

    proposal = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/proposals",
        headers=headers,
        json={
            "base_revision_id": as_is_revision_id,
            "summary": "Уточнить бизнес-цель в целевой версии.",
            "patch": [{"op": "replace", "path": "/passport/goal", "value": "Квалифицировать входящие лиды за пять минут."}],
        },
    ).json()
    accepted = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": as_is_revision_id},
    )
    assert accepted.status_code == 200

    revisions = request("GET", f"/api/v1/projects/{project['id']}/revisions", headers=headers).json()
    assert [(item["version_number"], item["perspective"]) for item in revisions] == [(1, "as_is"), (2, "to_be")]
    assert revisions[1]["parent_revision_id"] == as_is_revision_id
    assert revisions[0]["process_ir"]["passport"]["goal"] != revisions[1]["process_ir"]["passport"]["goal"]

    invalid_session = request(
        "POST",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
        json={"mode": "as_is_completion", "locale": "ru"},
    )
    assert invalid_session.status_code == 422


@pytest.mark.parametrize("minor", ["2.32", "2.31", "2.30"])
def test_as_is_round_trip_returns_exact_source_for_all_supported_minors(minor: str):
    workflow = deepcopy(WORKFLOW)
    workflow["meta"]["targetN8nMinor"] = minor
    workflow["customTopLevelField"] = {"preserve": True}
    process_ir, _, _, _ = import_n8n_workflow(workflow, "ru", minor)

    exported, report = build_roundtrip_workflow(
        process_ir,
        source_workflow=workflow,
        source_minor=minor,
        target_minor=minor,
        locale="ru",
        perspective="as_is",
    )

    assert exported == workflow
    assert report["exactSource"] is True
    assert report["sourceSha256"] == report["exportSha256"]


def test_round_trip_package_preserves_source_graph_and_reports_to_be_changes():
    headers, user = _register("n8n-round-trip-package@example.com")
    workflow = deepcopy(WORKFLOW)
    workflow["nodes"][2]["customNodeField"] = {"must": "survive"}
    imported = request("POST", "/api/v1/n8n-imports", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"], "workflow": workflow, "source_minor": "2.32", "locale": "ru",
    }).json()

    exact_response = request(
        "POST",
        f"/api/v1/n8n-imports/projects/{imported['project']['id']}/round-trip/2.32/package",
        headers=headers,
        json={"revision_id": imported["project"]["current_revision_id"], "locale": "ru", "include_general_guide": False},
    )
    assert exact_response.status_code == 200
    with ZipFile(BytesIO(exact_response.content)) as archive:
        exact_workflow = json.loads(archive.read("workflow-n8n-2.32.json"))
        exact_report = json.loads(archive.read("ROUND_TRIP_REPORT.json"))
        assert exact_workflow == workflow
        assert exact_report["mode"] == "exact_source"

    converted_response = request(
        "POST",
        f"/api/v1/n8n-imports/projects/{imported['project']['id']}/round-trip/2.30/package",
        headers=headers,
        json={"revision_id": imported["project"]["current_revision_id"], "locale": "ru", "include_general_guide": False},
    )
    assert converted_response.status_code == 200
    with ZipFile(BytesIO(converted_response.content)) as archive:
        converted = json.loads(archive.read("workflow-n8n-2.30.json"))
        report = json.loads(archive.read("ROUND_TRIP_REPORT.json"))
        assert converted["nodes"] == workflow["nodes"]
        assert converted["connections"] == workflow["connections"]
        assert converted["meta"]["targetN8nMinor"] == "2.30"
        assert converted["active"] is False
        assert report["mode"] == "source_minor_conversion"


def test_to_be_round_trip_preserves_opaque_source_node_fields():
    workflow = deepcopy(WORKFLOW)
    workflow["nodes"][2]["customNodeField"] = {"must": "survive"}
    process_ir, _, _, _ = import_n8n_workflow(workflow, "ru", "2.32")
    process_ir["process"]["name"] = "Lead Intake TO-BE"
    process_ir["steps"][2]["description"] = "Уточнённое назначение шага."

    exported, report = build_roundtrip_workflow(
        process_ir,
        source_workflow=workflow,
        source_minor="2.32",
        target_minor="2.31",
        locale="ru",
        perspective="to_be",
    )

    preserved_node = next(node for node in exported["nodes"] if node["id"] == workflow["nodes"][2]["id"])
    assert preserved_node["customNodeField"] == {"must": "survive"}
    assert preserved_node["position"] == workflow["nodes"][2]["position"]
    assert preserved_node["notes"] == "Уточнённое назначение шага."
    assert report["mode"] == "source_preserving_rebuild"
    assert report["preservedSourceNodes"] == len(workflow["nodes"])
