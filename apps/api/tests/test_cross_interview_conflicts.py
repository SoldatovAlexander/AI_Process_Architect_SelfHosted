import json
from io import BytesIO
from zipfile import ZipFile

from process_architect_api.deepseek import DeepSeekClient
from process_architect_api.models import CrossInterviewConflictAnalysis, InterviewAnalysisResult
from test_api import request
from test_multi_interview_evidence import _analyze_documents, _review
from test_analyst_api import create_session


def prepared_session(monkeypatch):
    headers, project, session = create_session()
    first = _review(headers, session["id"], "Владелец", "Владелец: Заявку всегда проверяет менеджер.")
    second = _review(headers, session["id"], "Исполнитель", "Исполнитель: Заявку всегда проверяет система.")
    results = [
        InterviewAnalysisResult.model_validate({"confirmed_facts": [{"statement": "Заявку всегда проверяет менеджер.", "segment_ids": [first["segments"][0]["id"]]}]}),
        InterviewAnalysisResult.model_validate({"confirmed_facts": [{"statement": "Заявку всегда проверяет система.", "segment_ids": [second["segments"][0]["id"]]}]}),
    ]
    analyses = _analyze_documents(monkeypatch, headers, [first, second], results)
    return headers, project, session, first, second, analyses


def test_semantic_conflict_requires_human_resolution_and_confirmed_conflict_blocks_draft(monkeypatch):
    headers, project, session, first, second, analyses = prepared_session(monkeypatch)

    async def conflict(self, messages):
        assert "Заявку всегда проверяет менеджер." in messages[-1]["content"]
        return CrossInterviewConflictAnalysis.model_validate({"conflicts": [{
            "summary": "Заявку проверяет менеджер или система.",
            "question": "Кто обычно проверяет заявку?",
            "reason": "Два участника называют разных постоянных исполнителей.",
            "fact_references": [{"analysis_id": analyses[0]["id"], "fact_index": 0}, {"analysis_id": analyses[1]["id"], "fact_index": 0}],
        }]})

    monkeypatch.setattr(DeepSeekClient, "analyze_cross_interview_conflicts", conflict)
    scan = request("POST", f"/api/v1/analyst/sessions/{session['id']}/cross-interview-conflicts/scan", headers=headers)
    assert scan.status_code == 200
    candidate = scan.json()["conflicts"][0]
    assert candidate["status"] == "pending"
    assert set(candidate["segment_ids"]) == {first["segments"][0]["id"], second["segments"][0]["id"]}
    summary = request("GET", f"/api/v1/analyst/sessions/{session['id']}/interview-evidence-summary", headers=headers).json()
    assert summary["semantic_conflicts_pending"] == 1
    assert summary["can_build_draft"] is False
    blocked = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interview-process-draft", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert blocked.status_code == 422

    confirmed = request("POST", f"/api/v1/analyst/cross-interview-conflicts/{candidate['id']}/resolve", headers=headers, json={"action": "confirm"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    summary = request("GET", f"/api/v1/analyst/sessions/{session['id']}/interview-evidence-summary", headers=headers).json()
    assert summary["semantic_conflicts_pending"] == 0
    assert summary["semantic_conflicts_confirmed"] == 1
    assert summary["can_build_draft"] is False
    archive = request("GET", f"/api/v1/project-archives/projects/{project['id']}", headers=headers)
    assert archive.status_code == 200
    with ZipFile(BytesIO(archive.content)) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        scans = json.loads(bundle.read("cross-interview-conflict-scans.json"))
        conflicts = json.loads(bundle.read("cross-interview-conflicts.json"))
    assert manifest["formatVersion"] == "1.10"
    assert manifest["counts"]["crossInterviewConflictScans"] == 1
    assert manifest["counts"]["crossInterviewConflicts"] == 1
    assert len(scans) == 1
    assert conflicts[0]["status"] == "confirmed"
    assert conflicts[0]["resolved"] is True
    validated = request("POST", "/api/v1/project-archives/validate", headers=headers, content=archive.content)
    assert validated.status_code == 200


def test_dismissed_candidate_allows_combined_draft_gate(monkeypatch):
    headers, _, session, _, _, analyses = prepared_session(monkeypatch)

    async def conflict(self, messages):
        return CrossInterviewConflictAnalysis.model_validate({"conflicts": [{"summary": "Разные исполнители.", "question": "Это разные варианты?", "reason": "Формулировки различаются.", "fact_references": [{"analysis_id": item["id"], "fact_index": 0} for item in analyses]}]})

    monkeypatch.setattr(DeepSeekClient, "analyze_cross_interview_conflicts", conflict)
    candidate = request("POST", f"/api/v1/analyst/sessions/{session['id']}/cross-interview-conflicts/scan", headers=headers).json()["conflicts"][0]
    dismissed = request("POST", f"/api/v1/analyst/cross-interview-conflicts/{candidate['id']}/resolve", headers=headers, json={"action": "dismiss"})
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    summary = request("GET", f"/api/v1/analyst/sessions/{session['id']}/interview-evidence-summary", headers=headers).json()
    assert summary["can_build_draft"] is True


def test_rejects_model_reference_outside_current_fact_set(monkeypatch):
    headers, _, session, _, _, analyses = prepared_session(monkeypatch)

    async def invalid(self, messages):
        return CrossInterviewConflictAnalysis.model_validate({"conflicts": [{"summary": "Ошибка", "question": "Что верно?", "reason": "Неверная ссылка", "fact_references": [{"analysis_id": analyses[0]["id"], "fact_index": 0}, {"analysis_id": "unknown", "fact_index": 0}]}]})

    monkeypatch.setattr(DeepSeekClient, "analyze_cross_interview_conflicts", invalid)
    response = request("POST", f"/api/v1/analyst/sessions/{session['id']}/cross-interview-conflicts/scan", headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_cross_interview_conflicts"
