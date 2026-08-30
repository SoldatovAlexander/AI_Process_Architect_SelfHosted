import pytest

from process_architect_api.deepseek import (
    DeepSeekAnalystTurn,
    DeepSeekClient,
    DeepSeekResponseError,
)
from process_architect_api.services.analyst_runtime import _readiness_fallback_turn
from test_api import request
from test_projects_api import create_project, register_user


NAME_PATCH = [
    {
        "op": "replace",
        "path": "/process/name",
        "value": "Analyst-qualified lead intake",
    }
]


def create_session() -> tuple[dict, dict, dict]:
    headers, project = create_project()
    response = request(
        "POST",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
        json={"mode": "refinement", "locale": "es-MX"},
    )
    assert response.status_code == 201
    return headers, project, response.json()


def create_proposal(headers: dict, project: dict, session: dict) -> dict:
    message = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/messages",
        headers=headers,
        json={"content": "Please make the process name more explicit."},
    )
    assert message.status_code == 201
    response = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/proposals",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "source_message_id": message.json()["id"],
            "summary": "Clarify the process name.",
            "patch": NAME_PATCH,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_persists_localized_session_and_message_context():
    headers, project, session = create_session()

    assert session["project_id"] == project["id"]
    assert session["started_from_revision_id"] == project["current_revision_id"]
    assert session["mode"] == "refinement"
    assert session["locale"] == "es-MX"

    message = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/messages",
        headers=headers,
        json={"content": "  Which CRM fields are still unknown?  "},
    )
    assert message.status_code == 201
    assert message.json()["content"] == "Which CRM fields are still unknown?"
    assert message.json()["revision_id"] == project["current_revision_id"]
    assert message.json()["locale"] == "es-MX"

    detail = request(
        "GET",
        f"/api/v1/analyst/sessions/{session['id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert [item["id"] for item in detail.json()["messages"]] == [message.json()["id"]]

    listed = request(
        "GET",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
    )
    assert [item["id"] for item in listed.json()] == [session["id"]]


def test_pending_proposal_does_not_mutate_project_until_accepted():
    headers, project, session = create_session()
    proposal = create_proposal(headers, project, session)

    assert proposal["status"] == "pending"
    assert proposal["validation"]["valid"] is True
    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert unchanged["current_revision_id"] == project["current_revision_id"]

    accepted = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["accepted_revision_id"] is not None

    changed = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert changed["current_revision_id"] == accepted.json()["accepted_revision_id"]
    assert changed["current_revision"]["source"] == "analyst"
    assert changed["current_revision"]["process_ir"]["process"]["name"] == NAME_PATCH[0]["value"]

    duplicate = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "proposal_already_resolved"


def test_stale_proposal_conflicts_without_overwriting_current_revision():
    headers, project, session = create_session()
    proposal = create_proposal(headers, project, session)
    direct_change = request(
        "POST",
        f"/api/v1/projects/{project['id']}/revisions",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "patch": [
                {
                    "op": "replace",
                    "path": "/process/description",
                    "value": "A newer direct user edit.",
                }
            ],
        },
    )
    assert direct_change.status_code == 201

    stale = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"

    current = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert current["current_revision_id"] == direct_change.json()["current_revision_id"]
    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert detail["proposed_patches"][0]["status"] == "pending"


def test_rejects_proposal_and_closing_session_blocks_new_content():
    headers, project, session = create_session()
    proposal = create_proposal(headers, project, session)

    rejected = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/reject",
        headers=headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert unchanged["current_revision_id"] == project["current_revision_id"]

    closed = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/close",
        headers=headers,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    blocked = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/messages",
        headers=headers,
        json={"content": "This message must not be stored."},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "analyst_session_closed"


def test_denies_analyst_session_access_from_another_workspace():
    owner_headers, _, session = create_session()
    other_headers, _ = register_user("analyst-other@example.com")

    forbidden = request(
        "GET",
        f"/api/v1/analyst/sessions/{session['id']}",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    owner_view = request(
        "GET",
        f"/api/v1/analyst/sessions/{session['id']}",
        headers=owner_headers,
    )
    assert owner_view.status_code == 200


@pytest.mark.parametrize(
    ("locale", "language_instruction"),
    [
        ("ru", "in clear Russian"),
        ("en-GB", "in clear English"),
        ("es-MX", "in clear Spanish"),
    ],
)
def test_live_turn_contract_is_locale_aware_and_creates_pending_proposal(
    monkeypatch,
    locale,
    language_instruction,
):
    headers, project = create_project()
    session = request(
        "POST",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
        json={"mode": "refinement", "locale": locale},
    ).json()
    captured = {}

    async def fake_proposal(self, messages):
        captured["messages"] = messages
        return DeepSeekAnalystTurn(
            message="Localized assistant response",
            summary="Clarify process name",
            patch=NAME_PATCH,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_proposal)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Please clarify the process name."},
    )

    assert turn.status_code == 201
    payload = turn.json()
    assert language_instruction in captured["messages"][0]["content"]
    assert "Deterministic readiness context" in captured["messages"][0]["content"]
    assert "question_crm_pipeline" in captured["messages"][0]["content"]
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert payload["assistant_message"]["provider"] == "deepseek"
    assert payload["assistant_message"]["prompt_version"] == "analyst-patch-v13"
    assert "steps is a root array" in captured["messages"][0]["content"]
    assert "Process IR JSON Schema" in captured["messages"][0]["content"]
    assert "Treat the user as a business specialist" in captured["messages"][0]["content"]
    assert "Do not produce numbered technical checklists" in captured["messages"][0]["content"]
    assert "Every question must stand on its own" in captured["messages"][0]["content"]
    assert "openQuestions[].question" in captured["messages"][0]["content"]
    assert "introductory summary does not make an answered question new" in captured["messages"][0]["content"]
    assert payload["proposed_patch"]["status"] == "pending"
    assert payload["proposed_patch"]["source_message_id"] == payload["assistant_message"]["id"]
    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert unchanged["current_revision_id"] == project["current_revision_id"]


def test_live_turn_can_ask_question_without_creating_patch(monkeypatch):
    headers, project, session = create_session()

    async def fake_question(self, messages):
        return DeepSeekAnalystTurn(
            message="Which CRM should receive the lead?",
            summary="",
            patch=[],
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_question)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Help me improve CRM details."},
    )

    assert turn.status_code == 201
    assert turn.json()["proposed_patch"] is None
    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["proposed_patches"] == []


def test_live_turn_repairs_false_completion_without_patch(monkeypatch):
    headers, project, session = create_session()
    calls = []

    async def fake_completion_then_patch(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            return DeepSeekAnalystTurn(
                message="The process is complete and ready for export.",
                summary="",
                patch=[],
            )
        return DeepSeekAnalystTurn(
            message="I prepared the confirmed process change.",
            summary="Apply confirmed interview facts",
            patch=NAME_PATCH,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_completion_then_patch)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Use the business rules I just confirmed."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert "claims that the process or diagram is ready" in calls[1][-1]["content"]
    assert turn.json()["proposed_patch"]["patch"] == NAME_PATCH


def test_live_turn_does_not_show_false_completion_when_repair_is_empty(monkeypatch):
    headers, project, session = create_session()
    calls = []

    async def fake_stubborn_completion(self, messages):
        calls.append(messages)
        return DeepSeekAnalystTurn(
            message="The process is complete and ready for export.",
            summary="",
            patch=[],
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_stubborn_completion)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Use the business rules I just confirmed."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert turn.json()["proposed_patch"] is None
    assert "no se pudieron aplicar al diagrama" in turn.json()["assistant_message"]["content"]
    assert "ready for export" not in turn.json()["assistant_message"]["content"]


def test_live_turn_repairs_no_changes_required_without_patch(monkeypatch):
    headers, project, session = create_session()
    calls = []

    async def fake_no_changes_then_patch(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            return DeepSeekAnalystTurn(
                message="Правила уже добавлены в процесс. Дополнительных изменений не требуется.",
                summary="",
                patch=[],
            )
        return DeepSeekAnalystTurn(
            message="Подготовил изменение по последнему ответу.",
            summary="Записать подтверждённое правило",
            patch=NAME_PATCH,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_no_changes_then_patch)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Уточняющий вопрос клиенту отправляет программа автоматически."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert turn.json()["proposed_patch"]["patch"] == NAME_PATCH


def test_live_turn_uses_readiness_fallback_after_invalid_provider_output(monkeypatch):
    headers, project, session = create_session()

    async def fake_invalid_output(self, messages):
        raise DeepSeekResponseError("invalid output")

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_invalid_output)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Continue."},
    )

    assert turn.status_code == 201
    assert turn.json()["proposed_patch"] is None
    assert turn.json()["assistant_message"]["content"].startswith(
        "Pasemos a la automatización del CRM"
    )


def test_live_turn_repairs_repeated_question_after_user_answers(monkeypatch):
    headers, project, session = create_session()
    question = "How does the manager decide whether to repeat the work or escalate it?"
    first_message = f"I understand that the manager checks the reply. {question}"
    repeated_message = f"I recorded who checks the reply. One detail remains. {question}"
    calls = []

    async def fake_repeated_question(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            return DeepSeekAnalystTurn(message=first_message, summary="", patch=[])
        if len(calls) == 2:
            return DeepSeekAnalystTurn(message=repeated_message, summary="", patch=[])
        return DeepSeekAnalystTurn(
            message="I recorded the escalation rule.",
            summary="Record escalation decision",
            patch=NAME_PATCH,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_repeated_question)
    first_turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Help me clarify the decision."},
    )
    assert first_turn.status_code == 201

    second_turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "The manager asks the customer and assignee, then escalates if either requests it."},
    )

    assert second_turn.status_code == 201
    assert len(calls) == 3
    assert "repeats an analyst response already shown" in calls[2][-1]["content"]
    assert "The manager asks the customer and assignee" in calls[2][-1]["content"]
    assert second_turn.json()["assistant_message"]["content"] == "I recorded the escalation rule."
    assert second_turn.json()["proposed_patch"]["patch"] == NAME_PATCH


def test_live_turn_never_persists_question_when_correction_repeats(monkeypatch):
    headers, project, session = create_session()
    question = "How does the manager decide whether to repeat the work or escalate it?"
    calls = []

    async def fake_stubborn_question(self, messages):
        calls.append(messages)
        return DeepSeekAnalystTurn(message=question, summary="", patch=[])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_stubborn_question)
    first_turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Help me clarify the decision."},
    )
    assert first_turn.status_code == 201

    second_turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Escalate when either the customer or assignee requests it."},
    )

    assert second_turn.status_code == 201
    assert len(calls) == 3
    assert second_turn.json()["proposed_patch"] is None
    second_message = second_turn.json()["assistant_message"]["content"]
    assert second_message.startswith("Pasemos a la automatización del CRM")
    assert question not in second_turn.json()["assistant_message"]["content"]

    third_turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Continue."},
    )
    assert third_turn.status_code == 201
    third_message = third_turn.json()["assistant_message"]["content"]
    assert third_message.startswith("Las respuestas están recopiladas")
    assert third_message != second_message
    assert third_turn.json()["proposed_patch"] is not None
    assert third_turn.json()["proposed_patch"]["patch"][0]["path"] == "/process/description"


def test_readiness_fallback_proposes_diagram_ready_when_review_is_complete():
    turn = _readiness_fallback_turn(
        "ru",
        process_ir={"process": {"maturity": "draft"}},
        readiness_context={"blocking_question_count": 0, "categories": {}},
        conversation=[],
    )

    assert turn.message.startswith("Схема подтверждена")
    assert turn.patch == [
        {
            "op": "replace",
            "path": "/process/maturity",
            "value": "diagram_ready",
        }
    ]


def test_readiness_fallback_moves_confirmed_diagram_to_export():
    turn = _readiness_fallback_turn(
        "ru",
        process_ir={"process": {"maturity": "diagram_ready"}},
        readiness_context={"blocking_question_count": 0, "categories": {}},
        conversation=[],
    )

    assert turn.message == "Схема подтверждена и готова. Можно переходить к экспорту."
    assert turn.patch == []


def test_confirming_ready_diagram_does_not_call_provider(monkeypatch):
    headers, project, session = create_session()
    source_message = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/messages",
        headers=headers,
        json={"content": "Confirm the completed diagram."},
    ).json()
    proposal = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/proposals",
        headers=headers,
        json={
            "base_revision_id": project["current_revision_id"],
            "source_message_id": source_message["id"],
            "summary": "Confirm diagram readiness",
            "patch": [
                {
                    "op": "replace",
                    "path": "/process/maturity",
                    "value": "diagram_ready",
                }
            ],
        },
    ).json()
    accepted = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )
    assert accepted.status_code == 200

    async def fail_if_called(self, messages):
        raise AssertionError("Provider should not be called for a confirmed diagram")

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fail_if_called)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "El diagrama es correcto."},
    )

    assert turn.status_code == 201
    assert turn.json()["assistant_message"]["content"].startswith(
        "El diagrama está confirmado y listo"
    )
    assert turn.json()["proposed_patch"] is None


def test_readiness_fallback_closes_stale_system_question_before_diagram_ready():
    turn = _readiness_fallback_turn(
        "ru",
        process_ir={
            "process": {"maturity": "draft"},
            "steps": [
                {
                    "id": "step_analyze",
                    "type": "system_task",
                    "description": "Система анализирует текст ответа клиента",
                    "missingFields": [],
                    "automationHint": {"target": "crm", "nodeType": "system_task"},
                }
            ],
            "openQuestions": [
                {
                    "id": "question_analysis",
                    "blocksAutomationReady": True,
                    "target": {"entity": "step", "id": "step_analyze"},
                }
            ],
        },
        readiness_context={"blocking_question_count": 1, "categories": {}},
        conversation=[],
    )

    assert "устаревший вопрос" in turn.message
    assert turn.patch == [
        {"op": "remove", "path": "/openQuestions/0"},
        {
            "op": "replace",
            "path": "/process/maturity",
            "value": "diagram_ready",
        },
    ]


def test_live_turn_keeps_chat_usable_when_repaired_patch_is_still_invalid(monkeypatch):
    headers, project, session = create_session()

    async def fake_invalid_patch(self, messages):
        return DeepSeekAnalystTurn(
            message="I updated the process.",
            summary="Add a process step",
            patch=[
                {
                    "op": "add",
                    "path": "/process/steps/-",
                    "value": {"id": "step_invalid"},
                }
            ],
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_invalid_patch)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Add one more process step."},
    )

    assert turn.status_code == 201
    assert turn.json()["proposed_patch"] is None
    assert "no se pudieron aplicar al diagrama" in turn.json()["assistant_message"]["content"]
    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["proposed_patches"] == []


def test_live_turn_repairs_invalid_patch_once(monkeypatch):
    headers, project, session = create_session()
    calls = []

    async def fake_repair(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            return DeepSeekAnalystTurn(
                message="I updated the process.",
                summary="Invalid first attempt",
                patch=[
                    {
                        "op": "add",
                        "path": "/process/steps/-",
                        "value": {"id": "step_invalid"},
                    }
                ],
            )
        return DeepSeekAnalystTurn(
            message="I corrected the process name.",
            summary="Correct process name",
            patch=NAME_PATCH,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_repair)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Correct the process name."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert "Validation error" in calls[1][-1]["content"]
    assert turn.json()["proposed_patch"]["patch"] == NAME_PATCH


def test_live_turn_repairs_new_employee_that_is_not_assigned_to_work(monkeypatch):
    headers, project, session = create_session()
    calls = []
    employee = {
        "id": "actor_finance_employee",
        "name": "Finance employee",
        "type": "human",
        "responsibilities": ["Approve finance replies"],
    }

    async def fake_employee_repair(self, messages):
        calls.append(messages)
        patch = [{"op": "add", "path": "/actors/-", "value": employee}]
        if len(calls) == 2:
            patch.append({
                "op": "replace",
                "path": "/passport/ownerActorId",
                "value": employee["id"],
            })
        return DeepSeekAnalystTurn(
            message="I added the finance employee.",
            summary="Assign finance employee",
            patch=patch,
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_employee_repair)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "A finance employee approves every finance reply."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert "must be assigned to relevant work" in calls[1][-1]["content"]
    assert any(
        operation["path"] == "/passport/ownerActorId"
        for operation in turn.json()["proposed_patch"]["patch"]
    )


def test_live_turn_explains_when_repaired_patch_is_a_noop(monkeypatch):
    headers, project, session = create_session()
    calls = []
    current_name = project["current_revision"]["process_ir"]["process"]["name"]

    async def fake_noop_repair(self, messages):
        calls.append(messages)
        if len(calls) == 1:
            return DeepSeekAnalystTurn(
                message="I updated the employee.",
                summary="Invalid employee change",
                patch=[{"op": "replace", "path": "/actors/99/name", "value": "Finance employee"}],
            )
        return DeepSeekAnalystTurn(
            message="The change is already present.",
            summary="No change",
            patch=[{"op": "replace", "path": "/process/name", "value": current_name}],
        )

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_noop_repair)
    turn = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Keep the employee who is already assigned."},
    )

    assert turn.status_code == 201
    assert len(calls) == 2
    assert turn.json()["proposed_patch"] is None
    assert "ya está reflejado" in turn.json()["assistant_message"]["content"]
