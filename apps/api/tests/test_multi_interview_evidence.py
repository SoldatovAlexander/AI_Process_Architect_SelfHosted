import json
from io import BytesIO
from zipfile import ZipFile

from process_architect_api.deepseek import DeepSeekAnalystTurn, DeepSeekClient
from process_architect_api.models import CrossInterviewConflictAnalysis, InterviewAnalysisResult
from test_analyst_api import create_session
from test_api import request


def _review(headers, session_id, title, content):
    document = request("POST", f"/api/v1/analyst/sessions/{session_id}/interviews", headers=headers, json={"title": title, "source_format": "txt", "language": "ru", "content": content}).json()
    return request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()


def _analyze_documents(monkeypatch, headers, documents, results):
    by_segment = {document["segments"][0]["id"]: result for document, result in zip(documents, results, strict=True)}

    async def fake_analysis(self, messages):
        return next(result for segment_id, result in by_segment.items() if segment_id in messages[-1]["content"])

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", fake_analysis)
    return [request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers).json() for document in documents]


def test_combines_current_interviews_deduplicates_facts_and_preserves_sources(monkeypatch):
    headers, project, session = create_session()
    first = _review(headers, session["id"], "Продажи", "Заказчик: Заявка приходит с сайта.\nМенеджер: Менеджер проверяет заявку.")
    second = _review(headers, session["id"], "Операции", "Владелец: заявка приходит с сайта!\nОператор: После проверки создаётся карточка клиента.")
    first_result = InterviewAnalysisResult.model_validate({"confirmed_facts": [
        {"statement": "Заявка приходит с сайта.", "segment_ids": [first["segments"][0]["id"]]},
        {"statement": "Менеджер проверяет заявку.", "segment_ids": [first["segments"][1]["id"]]},
    ]})
    second_result = InterviewAnalysisResult.model_validate({"confirmed_facts": [
        {"statement": "заявка приходит с сайта!", "segment_ids": [second["segments"][0]["id"]]},
        {"statement": "После проверки создаётся карточка клиента.", "segment_ids": [second["segments"][1]["id"]]},
    ]})
    analyses = _analyze_documents(monkeypatch, headers, [first, second], [first_result, second_result])

    summary = request("GET", f"/api/v1/analyst/sessions/{session['id']}/interview-evidence-summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["source_count"] == 2
    assert summary.json()["confirmed_fact_count"] == 4
    assert summary.json()["unique_fact_count"] == 3
    assert summary.json()["duplicate_fact_count"] == 1
    assert summary.json()["semantic_scan_required"] is True
    assert summary.json()["can_build_draft"] is False
    duplicate = next(item for item in summary.json()["facts"] if item["occurrences"] == 2)
    assert {item["analysis_id"] for item in duplicate["sources"]} == {item["id"] for item in analyses}
    captured = {}

    async def no_conflicts(self, messages):
        return CrossInterviewConflictAnalysis()

    monkeypatch.setattr(DeepSeekClient, "analyze_cross_interview_conflicts", no_conflicts)
    scan = request("POST", f"/api/v1/analyst/sessions/{session['id']}/cross-interview-conflicts/scan", headers=headers)
    assert scan.status_code == 200
    assert scan.json()["conflicts"] == []

    async def fake_draft(self, messages):
        captured["prompt"] = messages[-1]["content"]
        return DeepSeekAnalystTurn(message="Подготовлен общий черновик.", summary="Объединены два интервью.", patch=[{"op": "replace", "path": "/steps/1/title", "value": "Получить и проверить заявку"}])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_draft)
    response = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interview-process-draft", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert response.status_code == 201
    payload = response.json()
    assert payload["message"]["prompt_version"] == "multi-interview-process-draft-v1"
    assert len(payload["evidence_sources"]) == 2
    assert {item["document_title"] for item in payload["evidence_sources"]} == {"Продажи", "Операции"}
    assert payload["proposal"]["draft_quality"]["evidence_coverage"] == 100
    assert captured["prompt"].count('"statement": "Заявка приходит с сайта."') == 1
    unchanged = request("GET", f"/api/v1/projects/{project['id']}", headers=headers).json()
    assert unchanged["current_revision_id"] == project["current_revision_id"]
    archive = request("GET", f"/api/v1/project-archives/projects/{project['id']}", headers=headers)
    with ZipFile(BytesIO(archive.content)) as bundle:
        sources = json.loads(bundle.read("interview-proposal-evidence-sources.json"))
    assert len(sources) == 2
    assert {item["analysis_id"] for item in sources} == {item["id"] for item in analyses}


def test_contradiction_blocks_combined_draft_before_llm(monkeypatch):
    headers, project, session = create_session()
    first = _review(headers, session["id"], "Первое", "Менеджер: Заявку проверяет менеджер.\nСистема: Иногда заявку проверяет система.")
    second = _review(headers, session["id"], "Второе", "Заказчик: После проверки отправляется ответ.")
    first_result = InterviewAnalysisResult.model_validate({
        "confirmed_facts": [{"statement": "Заявка поступает на проверку.", "segment_ids": [first["segments"][0]["id"]]}],
        "contradictions": [{"summary": "Проверяет менеджер или система.", "segment_ids": [item["id"] for item in first["segments"]], "question": "Кто проверяет заявку?"}],
    })
    second_result = InterviewAnalysisResult.model_validate({"confirmed_facts": [{"statement": "После проверки отправляется ответ.", "segment_ids": [second["segments"][0]["id"]]}]})
    _analyze_documents(monkeypatch, headers, [first, second], [first_result, second_result])
    summary = request("GET", f"/api/v1/analyst/sessions/{session['id']}/interview-evidence-summary", headers=headers).json()
    assert summary["can_build_draft"] is False
    assert summary["contradictions"][0]["question"] == "Кто проверяет заявку?"

    async def must_not_run(self, messages):
        raise AssertionError("LLM must not receive contradictory evidence")

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", must_not_run)
    response = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interview-process-draft", headers=headers, json={"base_revision_id": project["current_revision_id"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "interview_evidence_not_ready"
