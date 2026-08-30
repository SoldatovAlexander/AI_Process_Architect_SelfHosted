from process_architect_api.deepseek import DeepSeekClient
from process_architect_api.models import InterviewAnalysisResult
from test_analyst_api import create_session
from test_api import request


def imported_interview():
    headers, _, session = create_session()
    document = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Интервью", "source_format": "txt", "language": "ru", "content": "Заказчик: Заявка приходит с сайта.\nМенеджер: Я проверяю бюджет вручную.\nЗаказчик: Иногда бюджет проверяет система."}).json()
    return headers, session, document


def result_for(document):
    ids = [item["id"] for item in document["segments"]]
    return InterviewAnalysisResult.model_validate({
        "confirmed_facts": [{"statement": "Заявка приходит с сайта.", "segment_ids": [ids[0]]}],
        "candidate_facts": [{"statement": "Проверка бюджета может быть частично автоматизирована.", "reason": "Участники описывают разные варианты.", "segment_ids": [ids[1], ids[2]]}],
        "contradictions": [{"summary": "Бюджет проверяет менеджер или система.", "segment_ids": [ids[1], ids[2]], "question": "Кто обычно проверяет бюджет заявки?"}],
        "clarification_questions": [{"question": "Что происходит после проверки бюджета?", "reason": "Следующий шаг не указан.", "priority": "blocking", "segment_ids": [ids[1]]}],
    })


def test_analysis_requires_review_and_is_idempotent(monkeypatch):
    headers, _, document = imported_interview()
    blocked = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "interview_not_reviewed"
    reviewed = request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()
    calls = 0

    async def fake_analysis(self, messages):
        nonlocal calls
        calls += 1
        assert reviewed["segments"][0]["id"] in messages[-1]["content"]
        return result_for(reviewed)

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", fake_analysis)
    first = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers)
    second = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers)
    assert first.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert calls == 1
    assert first.json()["stale"] is False
    assert first.json()["result"]["contradictions"][0]["segment_ids"] == [reviewed["segments"][1]["id"], reviewed["segments"][2]["id"]]


def test_rejects_unknown_evidence_and_marks_old_analysis_stale(monkeypatch):
    headers, session, document = imported_interview()
    reviewed = request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()

    async def invalid_analysis(self, messages):
        return InterviewAnalysisResult.model_validate({"confirmed_facts": [{"statement": "Выдуманный факт", "segment_ids": ["unknown-segment"]}]})

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", invalid_analysis)
    invalid = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers)
    assert invalid.status_code == 502
    assert invalid.json()["detail"]["code"] == "invalid_interview_analysis"

    async def valid_analysis(self, messages):
        return result_for(reviewed)

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", valid_analysis)
    assert request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers).status_code == 200
    segments = reviewed["segments"]
    segments[0]["text"] = "Заявка автоматически приходит с сайта."
    changed = request("PUT", f"/api/v1/analyst/interviews/{document['id']}", headers=headers, json={"expected_segments_sha256": reviewed["segments_sha256"], "title": reviewed["title"], "language": "ru", "segments": segments})
    assert changed.status_code == 200
    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert detail["interview_documents"][0]["latest_analysis"]["stale"] is True
