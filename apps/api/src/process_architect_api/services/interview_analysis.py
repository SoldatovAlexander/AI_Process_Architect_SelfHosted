from __future__ import annotations

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..analyst.interview_prompts import INTERVIEW_ANALYSIS_PROMPT_VERSION, interview_analysis_prompt
from ..config import Settings
from ..db_models import InterviewAnalysis, User
from ..deepseek import DeepSeekClient, DeepSeekResponseError
from ..models import InterviewAnalysisResult
from ..repositories.analyst import find_interview_analysis, list_interview_segments
from .interviews import InterviewRevisionConflict, _require_document
from .llm_credentials import resolve_user_llm_connection
from .llm_usage import begin_llm_usage, finish_llm_usage
from .analyst import require_session_access
from .projects import require_project_access


class InterviewNotReviewed(RuntimeError):
    pass


class InvalidInterviewAnalysis(RuntimeError):
    pass


def validate_evidence(result: InterviewAnalysisResult, segment_ids: set[str]) -> None:
    statements: set[str] = set()
    for collection in (result.confirmed_facts, result.candidate_facts):
        for item in collection:
            normalized = item.statement.casefold().strip()
            if normalized in statements:
                raise InvalidInterviewAnalysis("The same statement appears in more than one fact class.")
            statements.add(normalized)
    all_items = [*result.confirmed_facts, *result.candidate_facts, *result.contradictions, *result.clarification_questions]
    for item in all_items:
        if len(item.segment_ids) != len(set(item.segment_ids)) or not set(item.segment_ids).issubset(segment_ids):
            raise InvalidInterviewAnalysis("Interview analysis cites an unknown or repeated segment ID.")


async def analyze_reviewed_interview(db: Session, *, user: User, document_id: str, settings: Settings) -> InterviewAnalysis:
    document = _require_document(db, document_id, user)
    if document.status != "reviewed":
        raise InterviewNotReviewed("Review and confirm the transcript before analysis.")
    existing = find_interview_analysis(db, document.id, document.segments_sha256)
    if existing:
        return existing
    segments = list_interview_segments(db, document.id)
    segment_ids = {item.id for item in segments}
    prompt = interview_analysis_prompt(document, segments)
    connection = resolve_user_llm_connection(db, user, settings)
    analyst_session = require_session_access(db, document.session_id, user.id)
    project = require_project_access(db, analyst_session.project_id, user.id)
    meter = begin_llm_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        operation="interview_analysis",
        idempotency_key=f"interview-analysis:{document.id}:{document.segments_sha256}",
    )
    async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
        client = DeepSeekClient(settings, http_client, connection)
        try:
            result = await client.analyze_interview(prompt)
            validate_evidence(result, segment_ids)
        except DeepSeekResponseError as error:
            raise InvalidInterviewAnalysis(str(error)) from error
        finally:
            finish_llm_usage(db, meter=meter, provider=connection.provider, model=connection.model, observations=client.usage_observations, settings=settings)
    db.refresh(document)
    if document.status != "reviewed" or document.segments_sha256 != prompt_hash(document, segments):
        raise InterviewRevisionConflict("The transcript changed during analysis. Review it and run analysis again.")
    analysis = InterviewAnalysis(document_id=document.id, segments_sha256=document.segments_sha256, result=result.model_dump(mode="json"), provider=connection.provider, model=connection.model, prompt_version=INTERVIEW_ANALYSIS_PROMPT_VERSION, created_by_user_id=user.id)
    db.add(analysis)
    try:
        db.commit(); db.refresh(analysis); return analysis
    except IntegrityError:
        db.rollback()
        existing = find_interview_analysis(db, document.id, document.segments_sha256)
        if existing:
            return existing
        raise


def prompt_hash(document, segments) -> str:
    from .interviews import segments_hash
    return segments_hash(segments)
