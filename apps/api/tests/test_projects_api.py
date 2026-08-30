import json
from copy import deepcopy
from pathlib import Path

from test_api import authorization, request


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def register_user(email: str = "project-owner@example.com") -> tuple[dict, dict]:
    tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    ).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    return headers, user


def create_project() -> tuple[dict, dict]:
    headers, user = register_user()
    response = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Lead automation",
            "process_ir": deepcopy(LEAD),
        },
    )
    assert response.status_code == 201
    return headers, response.json()


def test_creates_lists_reads_and_archives_project():
    headers, project = create_project()

    assert project["current_revision"]["version_number"] == 1
    assert project["current_revision"]["source"] == "initial"
    assert project["default_locale"] == "ru"

    listed = request(
        "GET",
        "/api/v1/projects",
        headers=headers,
        params={"workspace_id": project["workspace_id"]},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [project["id"]]

    fetched = request("GET", f"/api/v1/projects/{project['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["current_revision_id"] == project["current_revision_id"]

    archived = request(
        "POST",
        f"/api/v1/projects/{project['id']}/archive",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"


def test_applies_patch_and_rejects_stale_base_revision():
    headers, project = create_project()
    initial_revision_id = project["current_revision_id"]
    changed = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "patch": [{"op": "replace", "path": "/process/name", "value": "Qualified Lead Intake"}],
        },
    )

    assert changed.status_code == 201
    changed_project = changed.json()
    assert changed_project["current_revision"]["version_number"] == 2
    assert changed_project["current_revision"]["process_ir"]["process"]["name"] == "Qualified Lead Intake"
    assert changed_project["current_revision"]["inverse_patch"]

    conflict = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "patch": [{"op": "replace", "path": "/process/name", "value": "Stale edit"}],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {
        "code": "revision_conflict",
        "message": "The project has changed since the supplied base revision.",
        "currentRevisionId": changed_project["current_revision_id"],
    }


def test_edits_process_passport_and_step_execution_as_revisions():
    headers, project = create_project()
    process_ir = project["current_revision"]["process_ir"]
    step_index = next(index for index, step in enumerate(process_ir["steps"]) if step["type"] == "system_task")
    next_step = deepcopy(process_ir["steps"][step_index])
    next_step["title"] = "Create qualified lead safely"
    next_step["execution"] = {
        "performedBy": "ai",
        "autonomy": "assist",
        "approvalRequired": True,
        "restrictions": ["Do not create a lead without contact details"],
    }
    next_passport = deepcopy(process_ir["passport"])
    next_passport["goal"] = "Create complete and reviewable qualified leads."

    changed = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "patch": [
                {"op": "replace", "path": "/passport", "value": next_passport},
                {"op": "replace", "path": f"/steps/{step_index}", "value": next_step},
            ],
        },
    )

    assert changed.status_code == 201
    revision = changed.json()["current_revision"]
    assert revision["version_number"] == 2
    assert revision["process_ir"]["passport"]["goal"] == next_passport["goal"]
    assert revision["process_ir"]["steps"][step_index]["execution"]["performedBy"] == "ai"


def test_undo_creates_new_revision_without_rewriting_history():
    headers, project = create_project()
    original_name = project["current_revision"]["process_ir"]["process"]["name"]
    changed = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "patch": [{"op": "replace", "path": "/process/name", "value": "Temporary name"}],
        },
    ).json()

    undone = request(
        "POST",
        f"/api/v1/projects/{project['id']}/undo",
        headers=headers,
        json={"base_revision_id": changed["current_revision_id"]},
    )
    assert undone.status_code == 201
    undo_revision = undone.json()["current_revision"]
    assert undo_revision["version_number"] == 3
    assert undo_revision["source"] == "undo"
    assert undo_revision["process_ir"]["process"]["name"] == original_name

    history = request(
        "GET",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
    ).json()
    assert [revision["version_number"] for revision in history] == [1, 2, 3]
    assert history[1]["process_ir"]["process"]["name"] == "Temporary name"


def test_initial_revision_cannot_be_undone():
    headers, project = create_project()

    response = request(
        "POST",
        f"/api/v1/projects/{project['id']}/undo",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "revision_not_undoable"


def test_restores_selected_revision_and_exposes_diff():
    headers, project = create_project()
    initial_revision_id = project["current_revision_id"]
    second = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": initial_revision_id,
            "patch": [{"op": "replace", "path": "/process/name", "value": "Second version"}],
        },
    ).json()
    third = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": second["current_revision_id"],
            "patch": [{"op": "replace", "path": "/process/name", "value": "Third version"}],
        },
    ).json()

    diff = request(
        "GET",
        f"/api/v1/projects/{project['id']}/revisions/diff",
        headers=headers,
        params={"fromRevisionId": initial_revision_id, "toRevisionId": third["current_revision_id"]},
    )
    assert diff.status_code == 200
    assert diff.json()["patch"]

    restored = request(
        "POST",
        f"/api/v1/projects/{project['id']}/restore",
        headers=headers,
        json={
            "base_revision_id": third["current_revision_id"],
            "target_revision_id": initial_revision_id,
        },
    )
    assert restored.status_code == 201
    restore_revision = restored.json()["current_revision"]
    assert restore_revision["version_number"] == 4
    assert restore_revision["source"] == "restore"
    assert restore_revision["restored_from_revision_id"] == initial_revision_id
    assert restore_revision["process_ir"] == LEAD


def test_rejects_invalid_result_and_denies_cross_workspace_access():
    owner_headers, project = create_project()
    invalid = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=owner_headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "patch": [{"op": "remove", "path": "/steps"}],
        },
    )
    assert invalid.status_code == 422

    other_headers, _ = register_user("other-project-user@example.com")
    forbidden = request("GET", f"/api/v1/projects/{project['id']}", headers=other_headers)
    assert forbidden.status_code == 403

    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=owner_headers)
    assert unchanged.json()["current_revision_id"] == project["current_revision_id"]
