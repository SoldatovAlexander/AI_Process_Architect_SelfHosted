from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from ..analyst.interview_proposal_prompts import MULTI_INTERVIEW_DRAFT_PROMPT_VERSION, multi_interview_process_draft_prompt
from ..config import Settings
from ..db_models import InterviewProposalEvidenceSource, User
from ..deepseek import DeepSeekClient, DeepSeekResponseError
from ..repositories.analyst import latest_interview_analysis, list_interview_segments, list_session_interviews
from .analyst import add_assistant_message, create_proposed_patch, require_session_access
from .interview_proposals import InterviewFactSelectionInvalid, InterviewProposalInvalid
from .llm_credentials import resolve_user_llm_connection
from .llm_usage import begin_llm_usage, finish_llm_usage
from .projects import RevisionConflict, preview_process_patch, require_project_access, require_project_revision


@dataclass(frozen=True)
class InterviewEvidenceSummary:
    session_id: str
    source_count: int
    confirmed_fact_count: int
    unique_fact_count: int
    duplicate_fact_count: int
    facts: list[dict]
    contradictions: list[dict]
    clarification_questions: list[dict]

    @property
    def can_build_draft(self) -> bool:
        return self.source_count >= 2 and self.unique_fact_count > 0 and not self.contradictions


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def summarize_interview_evidence(db: Session, *, user: User, session_id: str) -> InterviewEvidenceSummary:
    session = require_session_access(db, session_id, user.id)
    documents = list_session_interviews(db, session.id)
    grouped: dict[str, dict] = {}
    contradictions: list[dict] = []
    questions: dict[str, dict] = {}
    source_count = 0
    confirmed_count = 0
    for document in documents:
        analysis = latest_interview_analysis(db, document.id)
        if document.status != "reviewed" or analysis is None or analysis.segments_sha256 != document.segments_sha256:
            continue
        source_count += 1
        confirmed = analysis.result.get("confirmed_facts", [])
        confirmed_count += len(confirmed)
        for index, fact in enumerate(confirmed):
            key = _key(fact["statement"])
            group = grouped.setdefault(key, {"statement": fact["statement"], "occurrences": 0, "sources": []})
            group["occurrences"] += 1
            group["sources"].append({
                "analysis_id": analysis.id,
                "document_id": document.id,
                "document_title": document.title,
                "segments_sha256": analysis.segments_sha256,
                "selected_fact_indices": [index],
                "segment_ids": sorted(set(fact["segment_ids"])),
            })
        contradictions.extend(analysis.result.get("contradictions", []))
        for item in analysis.result.get("clarification_questions", []):
            key = _key(item["question"])
            existing = questions.get(key)
            if existing is None:
                questions[key] = {**item, "segment_ids": sorted(set(item["segment_ids"]))}
            else:
                existing["segment_ids"] = sorted(set(existing["segment_ids"]) | set(item["segment_ids"]))
                priorities = {"optional": 0, "important": 1, "blocking": 2}
                if priorities[item["priority"]] > priorities[existing["priority"]]:
                    existing["priority"] = item["priority"]
    facts = sorted(grouped.values(), key=lambda item: _key(item["statement"]))
    return InterviewEvidenceSummary(
        session_id=session.id,
        source_count=source_count,
        confirmed_fact_count=confirmed_count,
        unique_fact_count=len(facts),
        duplicate_fact_count=confirmed_count - len(facts),
        facts=facts,
        contradictions=contradictions,
        clarification_questions=sorted(questions.values(), key=lambda item: (-{"optional": 0, "important": 1, "blocking": 2}[item["priority"]], _key(item["question"]))),
    )


async def create_multi_interview_process_draft(db: Session, *, user: User, session_id: str, base_revision_id: str, settings: Settings):
    summary = summarize_interview_evidence(db, user=user, session_id=session_id)
    if summary.source_count < 2:
        raise InterviewFactSelectionInvalid("At least two current reviewed interview analyses are required.")
    if summary.contradictions:
        raise InterviewFactSelectionInvalid("Resolve interview contradictions before building a combined draft.")
    from .cross_interview_conflicts import current_cross_interview_conflicts
    semantic = current_cross_interview_conflicts(db, user=user, session_id=session_id)
    if semantic.scan is None:
        raise InterviewFactSelectionInvalid("Run semantic conflict analysis before building a combined draft.")
    if semantic.pending_count:
        raise InterviewFactSelectionInvalid("Review semantic conflict candidates before building a combined draft.")
    if semantic.confirmed_count:
        raise InterviewFactSelectionInvalid("Resolve confirmed cross-interview conflicts before building a combined draft.")
    if not summary.facts:
        raise InterviewFactSelectionInvalid("The interviews have no confirmed facts for a process draft.")
    session = require_session_access(db, session_id, user.id)
    project = require_project_access(db, session.project_id, user.id)
    if project.current_revision_id != base_revision_id:
        raise RevisionConflict(project.current_revision_id or "")
    revision = require_project_revision(db, project, base_revision_id)
    source_rows = [source for fact in summary.facts for source in fact["sources"]]
    evidence = []
    for source in source_rows:
        document_segments = list_interview_segments(db, source["document_id"])
        selected_ids = set(source["segment_ids"])
        evidence.extend({"document_id": source["document_id"], "document_title": source["document_title"], "analysis_id": source["analysis_id"], "id": segment.id, "speaker": segment.speaker, "text": segment.text} for segment in document_segments if segment.id in selected_ids)
    prompt = multi_interview_process_draft_prompt(language=session.locale, facts=[{"statement": item["statement"], "occurrences": item["occurrences"]} for item in summary.facts], evidence=evidence, questions=summary.clarification_questions, process_ir=revision.process_ir)
    connection = resolve_user_llm_connection(db, user, settings)
    meter = begin_llm_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        operation="interview_analysis",
        idempotency_key=f"multi-interview-draft:{session.id}:{revision.id}:{semantic.evidence_sha256}",
    )
    async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
        client = DeepSeekClient(settings, http_client, connection)
        try:
            generated = await client.propose_process_patch(prompt)
        except DeepSeekResponseError as error:
            raise InterviewProposalInvalid(str(error)) from error
        finally:
            finish_llm_usage(db, meter=meter, provider=connection.provider, model=connection.model, observations=client.usage_observations, settings=settings)
    db.refresh(project)
    if project.current_revision_id != revision.id:
        raise RevisionConflict(project.current_revision_id or "")
    db.expire_all()
    refreshed = summarize_interview_evidence(db, user=user, session_id=session_id)
    if refreshed != summary:
        raise InterviewFactSelectionInvalid("Interview evidence changed while the proposal was prepared.")
    if not generated.patch:
        raise InterviewProposalInvalid("Confirmed facts did not produce a Process IR change.")
    preview, _, _ = preview_process_patch(revision.process_ir, generated.patch)
    graph_changed = preview.get("steps") != revision.process_ir.get("steps") or preview.get("edges") != revision.process_ir.get("edges")
    task_count = sum(item.get("type") in {"human_task", "system_task", "decision", "timer", "external_event"} for item in preview.get("steps", []))
    if not graph_changed or task_count < 1 or not preview.get("edges"):
        raise InterviewProposalInvalid("The model did not produce a multi-step process graph.")
    try:
        message = add_assistant_message(db, user=user, session_id=session.id, revision_id=revision.id, content=generated.message, provider=connection.provider, model=connection.model, prompt_version=MULTI_INTERVIEW_DRAFT_PROMPT_VERSION, commit=False)
        proposal = create_proposed_patch(db, user=user, session_id=session.id, base_revision_id=revision.id, patch=generated.patch, summary=generated.summary or generated.message, source_message_id=message.id, commit=False)
        merged_sources: dict[str, dict] = {}
        for source in source_rows:
            existing = merged_sources.setdefault(source["analysis_id"], {**source, "selected_fact_indices": [], "segment_ids": []})
            existing["selected_fact_indices"] = sorted(set(existing["selected_fact_indices"]) | set(source["selected_fact_indices"]))
            existing["segment_ids"] = sorted(set(existing["segment_ids"]) | set(source["segment_ids"]))
        records = [InterviewProposalEvidenceSource(proposal_id=proposal.id, analysis_id=source["analysis_id"], segments_sha256=source["segments_sha256"], selected_fact_indices=source["selected_fact_indices"], segment_ids=source["segment_ids"]) for source in merged_sources.values()]
        db.add_all(records); db.commit(); db.refresh(message); db.refresh(proposal)
        return message, proposal, records, summary
    except Exception:
        db.rollback()
        raise
