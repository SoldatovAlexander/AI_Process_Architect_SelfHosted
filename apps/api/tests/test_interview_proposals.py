from process_architect_api.deepseek import DeepSeekAnalystTurn, DeepSeekClient
from test_analyst_api import NAME_PATCH, create_proposal
from test_api import request
from test_interview_analysis import imported_interview, result_for


def analyzed_interview(monkeypatch):
    headers, session, document = imported_interview()
    reviewed = request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()

    async def fake_analysis(self, messages):
        return result_for(reviewed)

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", fake_analysis)
    analysis = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers).json()
    project = request("GET", f"/api/v1/projects/{session['project_id']}", headers=headers).json()
    return headers, project, session, reviewed, analysis


def test_confirmed_fact_creates_reviewable_proposal_with_evidence(monkeypatch):
    headers, project, _, reviewed, analysis = analyzed_interview(monkeypatch)
    captured = {}

    async def fake_proposal(self, messages):
        captured["messages"] = messages
        return DeepSeekAnalystTurn(message="Подготовлено изменение по подтверждённому факту.", summary="Добавлен источник заявки.", patch=NAME_PATCH)

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_proposal)
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/proposal", headers=headers, json={"base_revision_id": project["current_revision_id"], "selected_fact_indices": [0]})

    assert response.status_code == 201
    payload = response.json()
    assert payload["proposal"]["status"] == "pending"
    assert payload["proposal"]["draft_quality"]["evidence_coverage"] == 100
    assert payload["proposal"]["draft_quality"]["step_count"] >= 3
    assert payload["proposal"]["draft_quality"]["edge_count"] >= 1
    assert payload["proposal"]["source_message_id"] == payload["message"]["id"]
    assert payload["message"]["prompt_version"] == "interview-proposal-v1"
    assert payload["evidence"] == {"analysis_id": analysis["id"], "segments_sha256": analysis["segments_sha256"], "selected_fact_indices": [0], "segment_ids": [reviewed["segments"][0]["id"]]}
    prompt = captured["messages"][-1]["content"]
    assert "Заявка приходит с сайта." in prompt
    assert "Проверка бюджета может быть частично автоматизирована." not in prompt

    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert unchanged["current_revision_id"] == project["current_revision_id"]
    accepted = request("POST", f"/api/v1/analyst/proposals/{payload['proposal']['id']}/accept", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert accepted.status_code == 200
    changed = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert changed["current_revision_id"] == accepted.json()["accepted_revision_id"]
    assert changed["current_revision"]["process_ir"]["process"]["name"] == NAME_PATCH[0]["value"]


def test_rejects_invalid_fact_selection_and_stale_project_revision(monkeypatch):
    headers, project, session, _, analysis = analyzed_interview(monkeypatch)
    invalid = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/proposal", headers=headers, json={"base_revision_id": project["current_revision_id"], "selected_fact_indices": [1]})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "interview_fact_selection_invalid"

    proposal = create_proposal(headers, project, session)
    accepted = request("POST", f"/api/v1/analyst/proposals/{proposal['id']}/accept", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert accepted.status_code == 200
    stale = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/proposal", headers=headers, json={"base_revision_id": project["current_revision_id"], "selected_fact_indices": [0]})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"


def test_empty_model_patch_does_not_leave_partial_history(monkeypatch):
    headers, project, session, _, analysis = analyzed_interview(monkeypatch)

    async def empty_proposal(self, messages):
        return DeepSeekAnalystTurn(message="Факт уже отражён.", summary="", patch=[])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", empty_proposal)
    before = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/proposal", headers=headers, json={"base_revision_id": project["current_revision_id"], "selected_fact_indices": [0]})
    after = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_interview_proposal"
    assert after["messages"] == before["messages"]
    assert after["proposed_patches"] == before["proposed_patches"]


def test_changed_transcript_invalidates_analysis_for_proposals(monkeypatch):
    headers, project, _, reviewed, analysis = analyzed_interview(monkeypatch)
    segments = reviewed["segments"]
    segments[0]["text"] = "Заявка автоматически поступает с сайта."
    changed = request("PUT", f"/api/v1/analyst/interviews/{reviewed['id']}", headers=headers, json={"expected_segments_sha256": reviewed["segments_sha256"], "title": reviewed["title"], "language": reviewed["language"], "segments": segments})
    assert changed.status_code == 200
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/proposal", headers=headers, json={"base_revision_id": project["current_revision_id"], "selected_fact_indices": [0]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "interview_revision_conflict"


def test_builds_multi_step_draft_from_all_confirmed_facts(monkeypatch):
    headers, project, session, reviewed, analysis = analyzed_interview(monkeypatch)
    captured = {}

    async def process_draft(self, messages):
        captured["messages"] = messages
        return DeepSeekAnalystTurn(message="Подготовлен связный черновик процесса.", summary="Собрана схема по подтверждённым фактам.", patch=[{"op": "replace", "path": "/steps/1/title", "value": "Получить заявку с сайта"}])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", process_draft)
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/process-draft", headers=headers, json={"base_revision_id": project["current_revision_id"]})

    assert response.status_code == 201
    payload = response.json()
    assert payload["message"]["prompt_version"] == "interview-process-draft-v1"
    assert payload["proposal"]["status"] == "pending"
    assert payload["proposal"]["draft_quality"]["evidence_coverage"] == 100
    assert payload["proposal"]["draft_quality"]["step_count"] >= 2
    assert payload["proposal"]["draft_quality"]["edge_count"] >= 1
    assert payload["evidence"]["selected_fact_indices"] == [0]
    assert payload["evidence"]["segment_ids"] == [reviewed["segments"][0]["id"]]
    prompt = captured["messages"][-1]["content"]
    assert "Заявка приходит с сайта." in prompt
    assert "Проверка бюджета может быть частично автоматизирована." not in prompt
    assert "Что происходит после проверки бюджета?" in prompt
    restored = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    restored_proposal = next(item for item in restored["proposed_patches"] if item["id"] == payload["proposal"]["id"])
    assert restored_proposal["draft_quality"] == payload["proposal"]["draft_quality"]


def test_rejects_process_draft_without_graph_change(monkeypatch):
    headers, project, _, _, analysis = analyzed_interview(monkeypatch)

    async def description_only(self, messages):
        return DeepSeekAnalystTurn(message="Обновлено описание.", summary="Описание", patch=[{"op": "replace", "path": "/process/description", "value": "Заявка приходит с сайта."}])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", description_only)
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/process-draft", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_interview_proposal"
