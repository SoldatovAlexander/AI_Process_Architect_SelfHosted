from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..analyst.cross_interview_prompts import CROSS_INTERVIEW_CONFLICT_PROMPT_VERSION, cross_interview_conflict_prompt
from ..config import Settings
from ..db_models import CrossInterviewConflict, CrossInterviewConflictScan, User, utc_now
from ..deepseek import DeepSeekClient, DeepSeekResponseError
from ..models import CrossInterviewConflictAnalysis
from .analyst import require_session_access
from .interview_evidence import _key, summarize_interview_evidence
from .llm_credentials import resolve_user_llm_connection
from .llm_usage import begin_llm_usage, finish_llm_usage
from .projects import require_project_access


class InvalidCrossInterviewConflict(RuntimeError):
    pass


class CrossInterviewConflictNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class CurrentCrossInterviewConflicts:
    evidence_sha256: str
    scan: CrossInterviewConflictScan | None
    conflicts: list[CrossInterviewConflict]

    @property
    def pending_count(self) -> int:
        return sum(item.status == "pending" for item in self.conflicts)

    @property
    def confirmed_count(self) -> int:
        return sum(item.status == "confirmed" for item in self.conflicts)


def evidence_snapshot(summary) -> tuple[str, list[dict], dict[tuple[str, int], dict]]:
    facts: list[dict] = []
    lookup: dict[tuple[str, int], dict] = {}
    for fact in summary.facts:
        for source in fact["sources"]:
            index = source["selected_fact_indices"][0]
            item = {"analysis_id": source["analysis_id"], "fact_index": index, "statement": fact["statement"], "document_id": source["document_id"], "document_title": source["document_title"], "segment_ids": source["segment_ids"], "segments_sha256": source["segments_sha256"]}
            facts.append(item)
            lookup[(item["analysis_id"], item["fact_index"])] = item
    facts.sort(key=lambda item: (item["analysis_id"], item["fact_index"]))
    content = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(content).hexdigest(), facts, lookup


def current_cross_interview_conflicts(db: Session, *, user: User, session_id: str) -> CurrentCrossInterviewConflicts:
    summary = summarize_interview_evidence(db, user=user, session_id=session_id)
    evidence_sha256, _, _ = evidence_snapshot(summary)
    scan = db.scalar(select(CrossInterviewConflictScan).where(CrossInterviewConflictScan.session_id == session_id, CrossInterviewConflictScan.evidence_sha256 == evidence_sha256))
    conflicts = list(db.scalars(select(CrossInterviewConflict).where(CrossInterviewConflict.session_id == session_id, CrossInterviewConflict.evidence_sha256 == evidence_sha256).order_by(CrossInterviewConflict.created_at, CrossInterviewConflict.id)))
    return CurrentCrossInterviewConflicts(evidence_sha256, scan, conflicts)


def _validate_candidates(result: CrossInterviewConflictAnalysis, lookup: dict[tuple[str, int], dict]) -> list[tuple[dict, list[dict]]]:
    validated: list[tuple[dict, list[dict]]] = []
    fingerprints: set[str] = set()
    for conflict in result.conflicts:
        refs = [(item.analysis_id, item.fact_index) for item in conflict.fact_references]
        if len(refs) != len(set(refs)) or any(ref not in lookup for ref in refs) or len({item[0] for item in refs}) < 2:
            raise InvalidCrossInterviewConflict("A semantic conflict cites invalid or same-analysis facts.")
        cited = [lookup[ref] for ref in refs]
        if len({_key(item["statement"]) for item in cited}) < 2:
            raise InvalidCrossInterviewConflict("An exact repeated fact cannot be a semantic conflict.")
        canonical_refs = sorted({f"{analysis_id}:{index}" for analysis_id, index in refs})
        fingerprint = hashlib.sha256("|".join(canonical_refs).encode()).hexdigest()
        if fingerprint in fingerprints:
            raise InvalidCrossInterviewConflict("The model returned a duplicate semantic conflict.")
        fingerprints.add(fingerprint)
        validated.append(({**conflict.model_dump(mode="json"), "fact_references": [{"analysis_id": item.split(":", 1)[0], "fact_index": int(item.split(":", 1)[1])} for item in canonical_refs], "fingerprint": fingerprint}, cited))
    return validated


async def scan_cross_interview_conflicts(db: Session, *, user: User, session_id: str, settings: Settings) -> CurrentCrossInterviewConflicts:
    session = require_session_access(db, session_id, user.id)
    summary = summarize_interview_evidence(db, user=user, session_id=session_id)
    if summary.source_count < 2:
        raise InvalidCrossInterviewConflict("At least two current reviewed interview analyses are required.")
    if summary.contradictions:
        raise InvalidCrossInterviewConflict("Resolve contradictions within each interview before cross-interview analysis.")
    evidence_sha256, facts, lookup = evidence_snapshot(summary)
    existing = current_cross_interview_conflicts(db, user=user, session_id=session_id)
    if existing.scan is not None:
        return existing
    prompt = cross_interview_conflict_prompt(language=session.locale, facts=facts)
    connection = resolve_user_llm_connection(db, user, settings)
    project = require_project_access(db, session.project_id, user.id)
    meter = begin_llm_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        operation="cross_interview_conflicts",
        idempotency_key=f"cross-interview:{session.id}:{evidence_sha256}",
    )
    async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
        client = DeepSeekClient(settings, http_client, connection)
        try:
            result = await client.analyze_cross_interview_conflicts(prompt)
            validated = _validate_candidates(result, lookup)
        except DeepSeekResponseError as error:
            raise InvalidCrossInterviewConflict(str(error)) from error
        finally:
            finish_llm_usage(db, meter=meter, provider=connection.provider, model=connection.model, observations=client.usage_observations, settings=settings)
    db.expire_all()
    refreshed_summary = summarize_interview_evidence(db, user=user, session_id=session_id)
    refreshed_hash, _, _ = evidence_snapshot(refreshed_summary)
    if refreshed_hash != evidence_sha256:
        raise InvalidCrossInterviewConflict("Interview evidence changed during semantic conflict analysis.")
    scan = CrossInterviewConflictScan(session_id=session_id, evidence_sha256=evidence_sha256, source_count=summary.source_count, fact_count=summary.confirmed_fact_count, provider=connection.provider, model=connection.model, prompt_version=CROSS_INTERVIEW_CONFLICT_PROMPT_VERSION, created_by_user_id=user.id)
    db.add(scan)
    for item, cited in validated:
        db.add(CrossInterviewConflict(session_id=session_id, evidence_sha256=evidence_sha256, fingerprint=item["fingerprint"], summary=item["summary"], question=item["question"], reason=item["reason"], fact_references=item["fact_references"], segment_ids=sorted({segment_id for source in cited for segment_id in source["segment_ids"]}), status="pending", provider=connection.provider, model=connection.model, prompt_version=CROSS_INTERVIEW_CONFLICT_PROMPT_VERSION, created_by_user_id=user.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return current_cross_interview_conflicts(db, user=user, session_id=session_id)


def resolve_cross_interview_conflict(db: Session, *, user: User, conflict_id: str, action: str) -> CrossInterviewConflict:
    conflict = db.scalar(select(CrossInterviewConflict).where(CrossInterviewConflict.id == conflict_id).with_for_update())
    if conflict is None:
        raise CrossInterviewConflictNotFound("Semantic conflict does not exist.")
    require_session_access(db, conflict.session_id, user.id)
    current = current_cross_interview_conflicts(db, user=user, session_id=conflict.session_id)
    if conflict.evidence_sha256 != current.evidence_sha256:
        raise InvalidCrossInterviewConflict("Interview evidence changed. Run semantic conflict analysis again.")
    if conflict.status != "pending":
        return conflict
    conflict.status = "confirmed" if action == "confirm" else "dismissed"
    conflict.resolved_by_user_id = user.id
    conflict.resolved_at = utc_now()
    db.commit(); db.refresh(conflict)
    return conflict
