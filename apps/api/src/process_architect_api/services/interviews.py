from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import timedelta, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db_models import InterviewDocument, InterviewSegment, User, utc_now
from ..localization import normalize_locale
from ..repositories.analyst import list_interview_segments, lock_interview_document
from .analyst import AnalystSessionClosed, require_session_access
from .interview_sources import validate_source_url


TIMESTAMP = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})")
RANGE = re.compile(r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})")
SPEAKER = re.compile(r"^(?P<speaker>[^:\n]{1,80}):\s+(?P<text>.+)$")


class InterviewDuplicate(RuntimeError):
    pass


class InterviewNotFound(RuntimeError):
    pass


class InterviewRevisionConflict(RuntimeError):
    pass


class InterviewPurged(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedSegment:
    ordinal: int
    speaker: str | None
    text: str
    start_ms: int | None = None
    end_ms: int | None = None


def _milliseconds(value: str) -> int:
    match = TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise ValueError("Invalid transcript timestamp.")
    return (((int(match["h"]) * 60 + int(match["m"])) * 60 + int(match["s"])) * 1000 + int(match["ms"]))


def _speaker_text(value: str) -> tuple[str | None, str]:
    compact = " ".join(line.strip() for line in value.splitlines() if line.strip())
    match = SPEAKER.match(compact)
    if match:
        return match["speaker"].strip(), match["text"].strip()
    return None, compact


def _parse_subtitles(content: str, source_format: str) -> list[ParsedSegment]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if source_format == "vtt" and normalized.upper().startswith("WEBVTT"):
        normalized = normalized.split("\n", 1)[1] if "\n" in normalized else ""
    segments: list[ParsedSegment] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timestamp_index = next((index for index, line in enumerate(lines) if RANGE.search(line)), None)
        if timestamp_index is None:
            continue
        match = RANGE.search(lines[timestamp_index])
        text = "\n".join(lines[timestamp_index + 1 :])
        speaker, text = _speaker_text(text)
        if text:
            segments.append(ParsedSegment(len(segments) + 1, speaker, text, _milliseconds(match["start"]), _milliseconds(match["end"])))
    return segments


def _parse_plain(content: str) -> list[ParsedSegment]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n\s*\n", normalized)
    if len(blocks) == 1:
        blocks = [line for line in normalized.splitlines() if line.strip()]
    segments: list[ParsedSegment] = []
    for block in blocks:
        speaker, text = _speaker_text(block)
        if text:
            segments.append(ParsedSegment(len(segments) + 1, speaker, text))
    return segments


def parse_interview(content: str, source_format: str) -> list[ParsedSegment]:
    segments = _parse_subtitles(content, source_format) if source_format in {"srt", "vtt"} else _parse_plain(content)
    if not segments:
        raise ValueError("The transcript does not contain readable interview segments.")
    if len(segments) > 5_000:
        raise ValueError("The transcript contains more than 5,000 segments.")
    return segments


def content_hash(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def segments_hash(segments) -> str:
    payload = [{"ordinal": index, "speaker": item.speaker, "text": item.text, "start_ms": item.start_ms, "end_ms": item.end_ms} for index, item in enumerate(segments, 1)]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def purge_interview_document(db: Session, *, document: InterviewDocument, reason: str) -> InterviewDocument:
    if document.status == "purged":
        return document
    now = utc_now()
    db.execute(update(InterviewSegment).where(InterviewSegment.document_id == document.id).values(speaker=None, text="[deleted]", start_ms=None, end_ms=None))
    # Analysis rows may be referenced by immutable proposal evidence, so redact their payload in place.
    from ..db_models import InterviewAnalysis
    db.execute(update(InterviewAnalysis).where(InterviewAnalysis.document_id == document.id).values(result={"confirmed_facts": [], "candidate_facts": [], "contradictions": [], "clarification_questions": []}))
    document.original_text = ""
    document.status = "purged"
    document.reviewed_by_user_id = None
    document.reviewed_at = None
    document.purged_at = now
    document.purge_reason = reason
    document.updated_at = now
    db.commit()
    db.refresh(document)
    return document


def enforce_interview_retention(db: Session, document: InterviewDocument) -> InterviewDocument:
    retention_until = document.retention_until
    if retention_until is not None and retention_until.tzinfo is None:
        retention_until = retention_until.replace(tzinfo=timezone.utc)
    if document.status != "purged" and retention_until is not None and retention_until <= utc_now():
        return purge_interview_document(db, document=document, reason="retention")
    return document


def _require_document(db: Session, document_id: str, user: User, *, allow_purged: bool = False) -> InterviewDocument:
    document = lock_interview_document(db, document_id)
    if document is None:
        raise InterviewNotFound("Interview transcript does not exist.")
    require_session_access(db, document.session_id, user.id)
    enforce_interview_retention(db, document)
    if document.status == "purged" and not allow_purged:
        raise InterviewPurged("Interview transcript content has been deleted by its retention policy.")
    return document


def _validate_segment_times(start_ms: int | None, end_ms: int | None) -> None:
    if start_ms is not None and end_ms is not None and end_ms < start_ms:
        raise ValueError("Segment end time cannot be earlier than its start time.")


def create_interview_document(db: Session, *, user: User, session_id: str, title: str, source_format: str, language: str | None, content: str, source_url: str | None = None, retention_days: int = 0, data_residency: str = "local") -> InterviewDocument:
    session = require_session_access(db, session_id, user.id)
    if session.status != "active":
        raise AnalystSessionClosed("Analyst session is closed.")
    segments = parse_interview(content, source_format)
    source_url = validate_source_url(source_format, source_url)
    retention_until = utc_now() + timedelta(days=retention_days) if retention_days else None
    document = InterviewDocument(session_id=session.id, title=title.strip(), source_format=source_format, source_url=source_url, language=normalize_locale(language or session.locale), original_text=content.strip(), content_sha256=content_hash(content), segments_sha256=segments_hash(segments), status="draft", data_residency=data_residency.strip(), retention_until=retention_until, created_by_user_id=user.id)
    db.add(document)
    try:
        db.flush()
        for segment in segments:
            db.add(InterviewSegment(document_id=document.id, **segment.__dict__))
        session.updated_at = utc_now()
        db.commit()
        db.refresh(document)
        return document
    except IntegrityError as error:
        db.rollback()
        raise InterviewDuplicate("This transcript has already been imported into the interview.") from error


def update_interview_document(db: Session, *, user: User, document_id: str, expected_hash: str, title: str, language: str, segments) -> InterviewDocument:
    document = _require_document(db, document_id, user)
    if document.segments_sha256 != expected_hash:
        raise InterviewRevisionConflict("The transcript changed after it was opened. Reload it before saving.")
    existing = {item.id: item for item in list_interview_segments(db, document.id)}
    supplied_ids = [item.id for item in segments if item.id]
    if len(supplied_ids) != len(set(supplied_ids)) or any(item_id not in existing for item_id in supplied_ids):
        raise ValueError("Transcript contains an unknown or repeated segment ID.")
    for offset, segment in enumerate(existing.values(), 1):
        segment.ordinal = -offset
    db.flush()
    for ordinal, item in enumerate(segments, 1):
        _validate_segment_times(item.start_ms, item.end_ms)
        segment = existing.get(item.id) if item.id else InterviewSegment(document_id=document.id)
        segment.ordinal = ordinal
        segment.speaker = item.speaker
        segment.text = item.text.strip()
        segment.start_ms = item.start_ms
        segment.end_ms = item.end_ms
        db.add(segment)
    for segment_id, segment in existing.items():
        if segment_id not in supplied_ids:
            db.delete(segment)
    document.title = title.strip()
    document.language = normalize_locale(language)
    document.segments_sha256 = segments_hash(segments)
    document.status = "draft"
    document.reviewed_by_user_id = None
    document.reviewed_at = None
    document.updated_at = utc_now()
    db.commit()
    db.refresh(document)
    return document


def review_interview_document(db: Session, *, user: User, document_id: str, expected_hash: str) -> InterviewDocument:
    document = _require_document(db, document_id, user)
    if document.segments_sha256 != expected_hash:
        raise InterviewRevisionConflict("The transcript changed after it was opened. Reload it before review.")
    if not list_interview_segments(db, document.id):
        raise ValueError("An empty transcript cannot be reviewed.")
    document.status = "reviewed"
    document.reviewed_by_user_id = user.id
    document.reviewed_at = utc_now()
    document.updated_at = utc_now()
    db.commit()
    db.refresh(document)
    return document


def delete_interview_content(db: Session, *, user: User, document_id: str) -> InterviewDocument:
    document = _require_document(db, document_id, user, allow_purged=True)
    return purge_interview_document(db, document=document, reason="manual")
