from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..analyst.interview_proposal_prompts import INTERVIEW_DRAFT_PROMPT_VERSION, INTERVIEW_PROPOSAL_PROMPT_VERSION, interview_process_draft_prompt, interview_proposal_prompt
from ..config import Settings
from ..db_models import InterviewAnalysis, InterviewProposalEvidence, ProposedPatch, User
from ..deepseek import DeepSeekClient, DeepSeekResponseError
from ..repositories.analyst import list_interview_segments
from .analyst import add_assistant_message, create_proposed_patch
from .interviews import InterviewRevisionConflict, _require_document
from .llm_credentials import resolve_user_llm_connection
from .llm_usage import begin_llm_usage, finish_llm_usage
from .projects import RevisionConflict, preview_process_patch, require_project_access, require_project_revision


class InterviewAnalysisNotFound(RuntimeError):
    pass


class InterviewFactSelectionInvalid(RuntimeError):
    pass


class InterviewProposalInvalid(RuntimeError):
    pass


async def create_interview_proposal(db: Session, *, user: User, analysis_id: str, base_revision_id: str, selected_indices: list[int], settings: Settings):
    analysis = db.get(InterviewAnalysis, analysis_id)
    if analysis is None:
        raise InterviewAnalysisNotFound("Interview analysis does not exist.")
    document = _require_document(db, analysis.document_id, user)
    if document.status != "reviewed" or document.segments_sha256 != analysis.segments_sha256:
        raise InterviewRevisionConflict("The transcript or analysis changed. Review and analyze it again.")
    confirmed = analysis.result.get("confirmed_facts", [])
    if any(index >= len(confirmed) for index in selected_indices):
        raise InterviewFactSelectionInvalid("Selected fact does not belong to confirmed interview facts.")
    selected = [confirmed[index] for index in selected_indices]
    session = document.session_id
    from .analyst import require_session_access
    analyst_session = require_session_access(db, session, user.id)
    project = require_project_access(db, analyst_session.project_id, user.id)
    if project.current_revision_id != base_revision_id:
        raise RevisionConflict(project.current_revision_id or "")
    revision = require_project_revision(db, project, base_revision_id)
    segments = list_interview_segments(db, document.id)
    prompt = interview_proposal_prompt(document=document, analysis=analysis, selected_facts=selected, segments=segments, process_ir=revision.process_ir)
    return await _persist_generated_proposal(db, user=user, settings=settings, analysis=analysis, document=document, analyst_session=analyst_session, project=project, revision=revision, selected_indices=selected_indices, selected=selected, prompt=prompt, prompt_version=INTERVIEW_PROPOSAL_PROMPT_VERSION, require_process_graph=False)


async def create_interview_process_draft(db: Session, *, user: User, analysis_id: str, base_revision_id: str, settings: Settings):
    analysis = db.get(InterviewAnalysis, analysis_id)
    if analysis is None:
        raise InterviewAnalysisNotFound("Interview analysis does not exist.")
    document = _require_document(db, analysis.document_id, user)
    if document.status != "reviewed" or document.segments_sha256 != analysis.segments_sha256:
        raise InterviewRevisionConflict("The transcript or analysis changed. Review and analyze it again.")
    confirmed = analysis.result.get("confirmed_facts", [])
    if not confirmed:
        raise InterviewFactSelectionInvalid("The analysis has no confirmed facts for a process draft.")
    from .analyst import require_session_access
    analyst_session = require_session_access(db, document.session_id, user.id)
    project = require_project_access(db, analyst_session.project_id, user.id)
    if project.current_revision_id != base_revision_id:
        raise RevisionConflict(project.current_revision_id or "")
    revision = require_project_revision(db, project, base_revision_id)
    segments = list_interview_segments(db, document.id)
    prompt = interview_process_draft_prompt(document=document, analysis=analysis, confirmed_facts=confirmed, segments=segments, process_ir=revision.process_ir)
    return await _persist_generated_proposal(db, user=user, settings=settings, analysis=analysis, document=document, analyst_session=analyst_session, project=project, revision=revision, selected_indices=list(range(len(confirmed))), selected=confirmed, prompt=prompt, prompt_version=INTERVIEW_DRAFT_PROMPT_VERSION, require_process_graph=True)


async def _persist_generated_proposal(db: Session, *, user: User, settings: Settings, analysis: InterviewAnalysis, document, analyst_session, project, revision, selected_indices: list[int], selected: list[dict], prompt: list[dict[str, str]], prompt_version: str, require_process_graph: bool):
    connection = resolve_user_llm_connection(db, user, settings)
    selected_key = ",".join(str(index) for index in sorted(selected_indices))
    meter = begin_llm_usage(
        db,
        workspace_id=project.workspace_id,
        settings=settings,
        operation="interview_analysis",
        idempotency_key=f"interview-proposal:{analysis.id}:{revision.id}:{prompt_version}:{selected_key}",
    )
    async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
        client = DeepSeekClient(settings, http_client, connection)
        try:
            generated = await client.propose_process_patch(prompt)
        except DeepSeekResponseError as error:
            raise InterviewProposalInvalid(str(error)) from error
        finally:
            finish_llm_usage(db, meter=meter, provider=connection.provider, model=connection.model, observations=client.usage_observations, settings=settings)
    db.refresh(project); db.refresh(document)
    if project.current_revision_id != revision.id:
        raise RevisionConflict(project.current_revision_id or "")
    if document.status != "reviewed" or document.segments_sha256 != analysis.segments_sha256:
        raise InterviewRevisionConflict("The transcript changed while the proposal was prepared.")
    if not generated.patch:
        raise InterviewProposalInvalid("Selected facts did not produce a Process IR change.")
    if require_process_graph:
        preview, _, _ = preview_process_patch(revision.process_ir, generated.patch)
        graph_changed = preview.get("steps") != revision.process_ir.get("steps") or preview.get("edges") != revision.process_ir.get("edges")
        task_count = sum(item.get("type") in {"human_task", "system_task", "decision", "timer", "external_event"} for item in preview.get("steps", []))
        if not graph_changed or task_count < 1 or not preview.get("edges"):
            raise InterviewProposalInvalid("The model did not produce a multi-step process graph.")
    try:
        message = add_assistant_message(db, user=user, session_id=analyst_session.id, revision_id=revision.id, content=generated.message, provider=connection.provider, model=connection.model, prompt_version=prompt_version, commit=False)
        proposal = create_proposed_patch(db, user=user, session_id=analyst_session.id, base_revision_id=revision.id, patch=generated.patch, summary=generated.summary or generated.message, source_message_id=message.id, commit=False)
        segment_ids = sorted({segment_id for fact in selected for segment_id in fact["segment_ids"]})
        evidence = InterviewProposalEvidence(proposal_id=proposal.id, analysis_id=analysis.id, segments_sha256=analysis.segments_sha256, selected_fact_indices=selected_indices, segment_ids=segment_ids)
        db.add(evidence); db.commit(); db.refresh(message); db.refresh(proposal)
        return message, proposal, evidence
    except Exception:
        db.rollback()
        raise
