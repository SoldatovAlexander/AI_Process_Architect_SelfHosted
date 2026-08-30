from datetime import timedelta

from process_architect_api.database import get_session_factory
from process_architect_api.db_models import InterviewDocument, utc_now
from process_architect_api.services.interviews import content_hash, parse_interview
from test_analyst_api import create_session
from test_api import request
from test_projects_api import register_user


SRT = """1
00:00:01,200 --> 00:00:04,400
Заказчик: Заявка приходит с сайта.

2
00:00:05,000 --> 00:00:08,500
Аналитик: Кто проверяет бюджет?
"""


def test_parses_plain_speakers_and_subtitle_timestamps():
    plain = parse_interview("Заказчик: Заявка приходит с сайта.\nАналитик: Кто её проверяет?", "txt")
    assert [(item.speaker, item.text) for item in plain] == [
        ("Заказчик", "Заявка приходит с сайта."),
        ("Аналитик", "Кто её проверяет?"),
    ]

    subtitles = parse_interview(SRT, "srt")
    assert subtitles[0].speaker == "Заказчик"
    assert subtitles[0].start_ms == 1_200
    assert subtitles[1].end_ms == 8_500


def test_interview_preview_is_read_only_and_import_is_idempotent():
    headers, _, session = create_session()
    payload = {"title": "Интервью с заказчиком", "source_format": "srt", "language": "ru", "content": SRT}

    preview = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/preview", headers=headers, json=payload)
    assert preview.status_code == 200
    assert preview.json()["id"] is None
    assert preview.json()["segment_count"] == 2
    assert preview.json()["segments"][0]["speaker"] == "Заказчик"

    before = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert before["interview_documents"] == []

    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json=payload)
    assert imported.status_code == 201
    assert imported.json()["content_sha256"] == content_hash(SRT)

    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers).json()
    assert len(detail["interview_documents"]) == 1
    assert detail["messages"] == []

    duplicate = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "interview_already_imported"


def test_rejects_empty_subtitle_and_cross_workspace_access():
    headers, _, session = create_session()
    invalid = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews/preview", headers=headers, json={"title": "Bad", "source_format": "vtt", "content": "WEBVTT\n\nNOTE no cues"})
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_interview_transcript"


def test_edits_reviews_and_reopens_transcript_without_changing_source_hash():
    headers, _, session = create_session()
    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Interview", "source_format": "srt", "language": "ru", "content": SRT}).json()
    original_hash = imported["content_sha256"]
    original_segment_hash = imported["segments_sha256"]
    segments = imported["segments"]
    segments[0]["speaker"] = "Владелец процесса"
    segments[0]["text"] = "Заявка автоматически приходит с сайта."
    segments.append({"id": None, "speaker": "Заказчик", "text": "Проверку выполняет менеджер.", "start_ms": None, "end_ms": None})

    updated = request("PUT", f"/api/v1/analyst/interviews/{imported['id']}", headers=headers, json={"expected_segments_sha256": original_segment_hash, "title": "Проверенное интервью", "language": "ru", "segments": segments})
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["content_sha256"] == original_hash
    assert payload["segments_sha256"] != original_segment_hash
    assert payload["status"] == "draft"
    assert payload["segment_count"] == 3
    assert payload["segments"][0]["id"] == imported["segments"][0]["id"]

    stale = request("POST", f"/api/v1/analyst/interviews/{imported['id']}/review", headers=headers, json={"expected_segments_sha256": original_segment_hash})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "interview_revision_conflict"

    reviewed = request("POST", f"/api/v1/analyst/interviews/{imported['id']}/review", headers=headers, json={"expected_segments_sha256": payload["segments_sha256"]})
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "reviewed"
    assert reviewed.json()["reviewed_at"] is not None

    reopened = request("PUT", f"/api/v1/analyst/interviews/{imported['id']}", headers=headers, json={"expected_segments_sha256": payload["segments_sha256"], "title": "Проверенное интервью", "language": "ru", "segments": payload["segments"]})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "draft"
    assert reopened.json()["reviewed_at"] is None


def test_denies_transcript_update_from_another_workspace():
    headers, _, session = create_session()
    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Interview", "source_format": "txt", "content": "Customer: One step"}).json()
    other_headers, _ = register_user("transcript-other@example.com")
    denied = request("POST", f"/api/v1/analyst/interviews/{imported['id']}/review", headers=other_headers, json={"expected_segments_sha256": imported["segments_sha256"]})
    assert denied.status_code == 403


def test_deletes_transcript_content_but_preserves_audit_metadata():
    headers, _, session = create_session()
    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Interview", "source_format": "srt", "language": "ru", "content": SRT}).json()

    deleted = request("DELETE", f"/api/v1/analyst/interviews/{imported['id']}/content", headers=headers)

    assert deleted.status_code == 200
    payload = deleted.json()
    assert payload["status"] == "purged"
    assert payload["purge_reason"] == "manual"
    assert payload["purged_at"] is not None
    assert payload["content_sha256"] == imported["content_sha256"]
    assert payload["segments_sha256"] == imported["segments_sha256"]
    assert [item["text"] for item in payload["segments"]] == ["[deleted]", "[deleted]"]

    rejected = request("POST", f"/api/v1/analyst/interviews/{imported['id']}/review", headers=headers, json={"expected_segments_sha256": imported["segments_sha256"]})
    assert rejected.status_code == 410
    assert rejected.json()["detail"]["code"] == "interview_content_deleted"


def test_expired_transcript_is_purged_when_session_is_read():
    headers, _, session = create_session()
    imported = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Expired", "source_format": "txt", "content": "Customer: One step"}).json()
    with get_session_factory()() as db:
        document = db.get(InterviewDocument, imported["id"])
        document.retention_until = utc_now() - timedelta(seconds=1)
        db.commit()

    detail = request("GET", f"/api/v1/analyst/sessions/{session['id']}", headers=headers)

    assert detail.status_code == 200
    expired = detail.json()["interview_documents"][0]
    assert expired["status"] == "purged"
    assert expired["purge_reason"] == "retention"
    assert expired["segments"][0]["text"] == "[deleted]"
