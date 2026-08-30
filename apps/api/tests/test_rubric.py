from sqlalchemy import delete

from process_architect_api.database import get_session_factory, init_database
from process_architect_api.db_models import RubricEntryTranslation
from test_projects_api import create_project
from test_api import request


def test_rubric_is_versioned_and_localized():
    headers, _ = create_project()

    russian = request("GET", "/api/v1/rubric?locale=ru", headers=headers)
    english = request("GET", "/api/v1/rubric?locale=en", headers=headers)

    assert russian.status_code == 200
    assert russian.json()["version"] == "core-1.0"
    assert len(russian.json()["dimensions"]) == 9
    assert russian.json()["dimensions"][0]["name"] == "Уровень процесса"
    assert english.json()["dimensions"][0]["name"] == "Process level"
    process = next(
        entry
        for entry in russian.json()["dimensions"][0]["entries"]
        if entry["code"] == "process"
    )
    assert process["parent_id"] == "core-1.0:process_level:process_map"


def test_database_initialization_repairs_missing_rubric_translations():
    with get_session_factory()() as db:
        db.execute(delete(RubricEntryTranslation))
        db.commit()

    init_database()

    headers, _ = create_project()
    response = request("GET", "/api/v1/rubric?locale=ru", headers=headers)
    assert response.status_code == 200
    assert all(dimension["entries"] for dimension in response.json()["dimensions"])


def test_confirmed_classification_creates_an_undoable_revision():
    headers, project = create_project()
    entry_ids = [
        "core-1.0:process_level:process",
        "core-1.0:business_role:core",
        "core-1.0:domain:sales_crm",
        "core-1.0:automation_mode:workflow",
    ]

    classified = request(
        "POST",
        f"/api/v1/projects/{project['id']}/classification",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "rubric_version": "core-1.0",
            "entry_ids": entry_ids,
        },
    )

    assert classified.status_code == 201
    changed = classified.json()
    assert changed["current_revision"]["version_number"] == 2
    classification = changed["current_revision"]["process_ir"]["classification"]
    assert classification["status"] == "confirmed"
    assert classification["entryIds"] == entry_ids
    assert classification["classifiedByUserId"]

    undone = request(
        "POST",
        f"/api/v1/projects/{project['id']}/undo",
        headers=headers,
        json={"base_revision_id": changed["current_revision_id"]},
    )
    assert undone.status_code == 201
    assert "classification" not in undone.json()["current_revision"]["process_ir"]


def test_classification_rejects_unknown_and_duplicate_dimensions():
    headers, project = create_project()
    unknown = request(
        "POST",
        f"/api/v1/projects/{project['id']}/classification",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "rubric_version": "core-1.0",
            "entry_ids": ["core-1.0:risk:unknown"],
        },
    )
    duplicate = request(
        "POST",
        f"/api/v1/projects/{project['id']}/classification",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "rubric_version": "core-1.0",
            "entry_ids": ["core-1.0:risk:low", "core-1.0:risk:high"],
        },
    )

    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "invalid_rubric_selection"
    assert duplicate.status_code == 422
    assert duplicate.json()["detail"]["code"] == "invalid_rubric_selection"
