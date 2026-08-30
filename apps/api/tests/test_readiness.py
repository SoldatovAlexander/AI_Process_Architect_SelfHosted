import json
from copy import deepcopy
from pathlib import Path

from process_architect_api.readiness import calculate_readiness
from test_api import request
from test_projects_api import create_project, register_user


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def test_calculates_explainable_readiness_and_next_blocking_question():
    result = calculate_readiness(LEAD, "revision-lead")

    assert result.revision_id == "revision-lead"
    assert result.overall == 79
    assert result.automation_ready is False
    assert result.blocking_question_count == 2
    assert result.next_blocking_question.id == "question_crm_pipeline"
    assert result.categories["automation"].status == "blocked"
    assert result.categories["automation"].reason_codes == [
        "blocking_questions_open",
        "automation_parameters_missing",
    ]
    assert result.categories["systems"].reason_codes == ["unknown_integrations"]


def test_marks_complete_process_automation_ready():
    process_ir = deepcopy(LEAD)
    process_ir["openQuestions"] = []
    for step in process_ir["steps"]:
        step["missingFields"] = []
    for system in process_ir["systems"]:
        system["integrationStatus"] = "configured"
    existing_sources = {item["sourceStepId"] for item in process_ir["exceptions"]}
    for step in process_ir["steps"]:
        if step["type"] == "system_task" and step["id"] not in existing_sources:
            process_ir["exceptions"].append(
                {
                    "id": f"exception_{step['id']}",
                    "sourceStepId": step["id"],
                    "trigger": "Execution fails",
                    "handling": "Notify the process owner and queue a retry.",
                }
            )

    result = calculate_readiness(process_ir)

    assert result.automation_ready is True
    assert result.blocking_question_count == 0
    assert result.next_blocking_question is None
    assert result.categories["automation"].score == 100
    assert all(category.status != "blocked" for category in result.categories.values())


def test_process_owner_and_unlinked_decision_rules_block_draft_readiness():
    process_ir = deepcopy(LEAD)
    process_ir["passport"]["ownerActorId"] = None
    process_ir["businessRules"] = []
    for edge in process_ir["edges"]:
        edge["ruleIds"] = []

    result = calculate_readiness(process_ir)

    assert result.readiness_scope == "automation_draft"
    assert result.draft_ready is False
    assert result.categories["passport"].status == "blocked"
    assert "process_owner_missing" in result.categories["passport"].reason_codes
    assert result.categories["rules"].status == "blocked"


def test_structural_validation_errors_block_readiness_without_crashing():
    invalid = deepcopy(LEAD)
    invalid["steps"] = []
    invalid["edges"] = []

    result = calculate_readiness(invalid)

    assert result.automation_ready is False
    assert result.categories["structure"].status == "blocked"
    assert "validation_errors" in result.categories["structure"].reason_codes


def test_empty_seed_process_is_not_reported_as_automation_ready():
    process_ir = deepcopy(LEAD)
    process_ir["process"]["maturity"] = "draft"
    process_ir["actors"] = []
    process_ir["systems"] = []
    process_ir["dataObjects"] = []
    process_ir["steps"] = [
        deepcopy(next(step for step in LEAD["steps"] if step["type"] == "start")),
        deepcopy(next(step for step in LEAD["steps"] if step["type"] == "end")),
    ]
    for step in process_ir["steps"]:
        step["actorId"] = None
        step["systemId"] = None
        step["inputs"] = []
        step["outputs"] = []
    process_ir["edges"] = [
        {
            "id": "edge_seed",
            "from": process_ir["steps"][0]["id"],
            "to": process_ir["steps"][1]["id"],
            "condition": None,
        }
    ]
    process_ir["exceptions"] = []
    process_ir["openQuestions"] = []

    result = calculate_readiness(process_ir)

    assert result.overall == 4
    assert result.automation_ready is False
    assert result.categories["structure"].status == "blocked"
    assert "process_steps_missing" in result.categories["structure"].reason_codes
    assert result.categories["automation"].reason_codes == ["automation_steps_missing"]


def test_readiness_api_supports_current_and_historical_revision():
    headers, project = create_project()
    initial_id = project["current_revision_id"]
    changed = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": initial_id,
            "patch": [{"op": "remove", "path": "/openQuestions/1"}],
        },
    )
    assert changed.status_code == 201

    current = request(
        "GET",
        f"/api/v1/projects/{project['id']}/readiness",
        headers=headers,
    )
    historical = request(
        "GET",
        f"/api/v1/projects/{project['id']}/readiness",
        headers=headers,
        params={"revisionId": initial_id},
    )

    assert current.status_code == 200
    assert current.json()["blocking_question_count"] == 1
    assert current.json()["revision_id"] == changed.json()["current_revision_id"]
    assert historical.status_code == 200
    assert historical.json()["blocking_question_count"] == 2
    assert historical.json()["revision_id"] == initial_id


def test_readiness_api_denies_other_workspace():
    owner_headers, project = create_project()
    other_headers, _ = register_user("readiness-other@example.com")

    forbidden = request(
        "GET",
        f"/api/v1/projects/{project['id']}/readiness",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    allowed = request(
        "GET",
        f"/api/v1/projects/{project['id']}/readiness",
        headers=owner_headers,
    )
    assert allowed.status_code == 200
