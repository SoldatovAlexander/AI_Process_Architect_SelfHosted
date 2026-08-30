from process_architect_api.deepseek import DeepSeekClient
from process_architect_api.models import InterviewAnalysisResult
from test_api import request
from test_interview_analysis import imported_interview


def analyzed_lead_interview(monkeypatch):
    headers, _, document = imported_interview()
    reviewed = request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()
    segment_ids = [item["id"] for item in reviewed["segments"]]

    async def fake_analysis(self, messages):
        return InterviewAnalysisResult.model_validate({
            "confirmed_facts": [
                {"statement": "Лиды приходят с сайта, их надо квалифицировать и назначать менеджера в CRM.", "segment_ids": [segment_ids[0]]},
            ],
            "candidate_facts": [
                {"statement": "Возможно, нужен контроль SLA и автоматическая эскалация тикетов.", "reason": "Это ещё не подтверждено.", "segment_ids": [segment_ids[1]]},
            ],
        })

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", fake_analysis)
    analysis = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers).json()
    return headers, reviewed, analysis


def test_matches_template_and_rubric_using_confirmed_facts_only(monkeypatch):
    headers, reviewed, analysis = analyzed_lead_interview(monkeypatch)
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/template-match", headers=headers, json={"locale": "ru", "excluded_ids": []})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_id"] == analysis["id"]
    assert payload["segments_sha256"] == reviewed["segments_sha256"]
    assert payload["confirmed_fact_indices"] == [0]
    assert payload["suggestion"]["template"]["id"] == "lead-qualification"
    assert payload["suggestion"]["confidence"] >= 0.7
    assert payload["suggestion"]["matched_signals"]
    assert payload["proposed_rubric_entry_ids"] == payload["suggestion"]["template"]["rubric_entry_ids"]
    assert payload["suggestion"]["template"]["id"] != "catalog-support-sla-monitoring-escalation"


def test_exclusion_and_stale_analysis_are_enforced(monkeypatch):
    headers, reviewed, analysis = analyzed_lead_interview(monkeypatch)
    excluded = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/template-match", headers=headers, json={"locale": "en", "excluded_ids": ["lead-qualification"]})
    assert excluded.status_code == 200
    assert excluded.json()["suggestion"] is None or excluded.json()["suggestion"]["template"]["id"] != "lead-qualification"

    segments = reviewed["segments"]
    segments[0]["text"] = "Источник лидов пока неизвестен."
    changed = request("PUT", f"/api/v1/analyst/interviews/{reviewed['id']}", headers=headers, json={"expected_segments_sha256": reviewed["segments_sha256"], "title": reviewed["title"], "language": reviewed["language"], "segments": segments})
    assert changed.status_code == 200
    stale = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/template-match", headers=headers, json={"locale": "ru"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "interview_revision_conflict"


def test_does_not_match_candidates_when_no_facts_are_confirmed(monkeypatch):
    headers, _, document = imported_interview()
    reviewed = request("POST", f"/api/v1/analyst/interviews/{document['id']}/review", headers=headers, json={"expected_segments_sha256": document["segments_sha256"]}).json()

    async def candidate_only_analysis(self, messages):
        return InterviewAnalysisResult.model_validate({
            "candidate_facts": [{
                "statement": "Лиды надо квалифицировать и назначать менеджера в CRM.",
                "reason": "Это только предположение.",
                "segment_ids": [reviewed["segments"][0]["id"]],
            }],
        })

    monkeypatch.setattr(DeepSeekClient, "analyze_interview", candidate_only_analysis)
    analysis = request("POST", f"/api/v1/analyst/interviews/{document['id']}/analysis", headers=headers).json()
    response = request("POST", f"/api/v1/analyst/interview-analyses/{analysis['id']}/template-match", headers=headers, json={"locale": "ru"})

    assert response.status_code == 200
    assert response.json()["confirmed_fact_indices"] == []
    assert response.json()["suggestion"] is None
    assert response.json()["proposed_rubric_entry_ids"] == []
