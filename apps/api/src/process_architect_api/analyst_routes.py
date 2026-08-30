from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .database import get_db
from .config import Settings, get_settings
from .entitlement_dependencies import InterviewImportEntitlement
from .db_models import AnalystMessage, AnalystSession, InterviewAnalysis, InterviewDocument, InterviewProposalEvidence, InterviewProposalEvidenceSource, ProcessRevision, ProposedPatch
from .deepseek import DeepSeekConfigurationError, DeepSeekResponseError
from .models import (
    AnalystMessageCreateRequest,
    AnalystMessageResponse,
    AnalystSessionCreateRequest,
    AnalystSessionDetailResponse,
    AnalystSessionResponse,
    AnalystTurnResponse,
    InterviewAnalysisResponse,
    InterviewDocumentResponse,
    InterviewDraftQualityResponse,
    CrossInterviewConflictResolveRequest,
    CrossInterviewConflictResponse,
    CrossInterviewConflictScanResponse,
    InterviewEvidenceFactResponse,
    InterviewEvidenceSourceResponse,
    InterviewEvidenceSummaryResponse,
    InterviewImportRequest,
    InterviewProposalEvidenceResponse,
    InterviewProcessDraftRequest,
    InterviewProposalRequest,
    InterviewProposalResponse,
    MultiInterviewProposalResponse,
    InterviewTemplateMatchRequest,
    InterviewTemplateMatchResponse,
    InterviewReviewRequest,
    InterviewSegmentResponse,
    InterviewSourceResolveRequest,
    InterviewSourceResolveResponse,
    InterviewUpdateRequest,
    ProposedPatchCreateRequest,
    ProposedPatchResolveRequest,
    ProposedPatchResponse,
)
from .repositories.analyst import (
    list_project_sessions,
    list_session_messages,
    list_interview_segments,
    list_session_interviews,
    list_session_proposals,
    latest_interview_analysis,
)
from .services.analyst import (
    AnalystMessageNotFound,
    AnalystSessionClosed,
    AnalystSessionNotFound,
    ProposedPatchBaseMismatch,
    ProposedPatchNotFound,
    ProposedPatchResolved,
    accept_proposed_patch,
    add_user_message,
    close_analyst_session,
    create_analyst_session,
    create_proposed_patch,
    reject_proposed_patch,
    require_session_access,
)
from .services.projects import (
    InvalidProcessPatch,
    ProjectNotFound,
    RevisionConflict,
    RevisionNotFound,
    preview_process_patch,
    require_project_access,
)
from .services.analyst_runtime import AnalystGeneratedPatchError, run_analyst_turn
from .services.billing_usage import BillingUsageLimitExceeded
from .readiness import calculate_readiness
from .services.interview_analysis import InterviewNotReviewed, InvalidInterviewAnalysis, analyze_reviewed_interview
from .services.cross_interview_conflicts import CrossInterviewConflictNotFound, InvalidCrossInterviewConflict, current_cross_interview_conflicts, evidence_snapshot, resolve_cross_interview_conflict, scan_cross_interview_conflicts
from .services.interview_evidence import create_multi_interview_process_draft, summarize_interview_evidence
from .services.interview_proposals import InterviewAnalysisNotFound, InterviewFactSelectionInvalid, InterviewProposalInvalid, create_interview_process_draft, create_interview_proposal
from .services.interview_templates import match_interview_template
from .services.interview_sources import InterviewSourceInvalid, resolve_file, resolve_link, validate_source_url
from .services.interviews import InterviewDuplicate, InterviewNotFound, InterviewPurged, InterviewRevisionConflict, content_hash, create_interview_document, delete_interview_content, enforce_interview_retention, parse_interview, review_interview_document, segments_hash, update_interview_document
from .services.workspaces import WorkspaceAccessDenied


router = APIRouter(prefix="/api/v1", tags=["analyst"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def message_response(message: AnalystMessage) -> AnalystMessageResponse:
    return AnalystMessageResponse(
        id=message.id,
        session_id=message.session_id,
        revision_id=message.revision_id,
        role=message.role,
        content=message.content,
        locale=message.locale,
        provider=message.provider,
        model=message.model,
        prompt_version=message.prompt_version,
        created_by_user_id=message.created_by_user_id,
        created_at=message.created_at,
    )


def proposal_response(proposal: ProposedPatch, db: Session | None = None) -> ProposedPatchResponse:
    return ProposedPatchResponse(
        id=proposal.id,
        session_id=proposal.session_id,
        project_id=proposal.project_id,
        base_revision_id=proposal.base_revision_id,
        source_message_id=proposal.source_message_id,
        patch=proposal.patch,
        summary=proposal.summary,
        validation=proposal.validation_result,
        status=proposal.status,
        accepted_revision_id=proposal.accepted_revision_id,
        created_by_user_id=proposal.created_by_user_id,
        resolved_by_user_id=proposal.resolved_by_user_id,
        created_at=proposal.created_at,
        resolved_at=proposal.resolved_at,
        draft_quality=_proposal_quality(db, proposal) if db else None,
    )


def _proposal_quality(db: Session, proposal: ProposedPatch) -> InterviewDraftQualityResponse | None:
    evidence = db.get(InterviewProposalEvidence, proposal.id)
    evidence_sources = list(db.scalars(select(InterviewProposalEvidenceSource).where(InterviewProposalEvidenceSource.proposal_id == proposal.id)))
    revision = db.get(ProcessRevision, proposal.base_revision_id)
    if (evidence is None and not evidence_sources) or revision is None:
        return None
    analyses = [db.get(InterviewAnalysis, item.analysis_id) for item in evidence_sources] if evidence_sources else [db.get(InterviewAnalysis, evidence.analysis_id)]
    if any(item is None for item in analyses):
        return None
    try:
        process_ir, _, validation = preview_process_patch(revision.process_ir, proposal.patch)
    except InvalidProcessPatch:
        return None
    confirmed_count = sum(len(item.result.get("confirmed_facts", [])) for item in analyses if item is not None)
    selected_count = sum(len(item.selected_fact_indices) for item in evidence_sources) if evidence_sources else len(evidence.selected_fact_indices)
    readiness = calculate_readiness(process_ir)
    return InterviewDraftQualityResponse(
        selected_fact_count=selected_count,
        total_confirmed_fact_count=confirmed_count,
        evidence_coverage=round(selected_count / confirmed_count * 100) if confirmed_count else 0,
        step_count=len(process_ir.get("steps", [])),
        edge_count=len(process_ir.get("edges", [])),
        decision_count=sum(item.get("type") == "decision" for item in process_ir.get("steps", [])),
        open_question_count=len(process_ir.get("openQuestions", [])),
        validation_warning_codes=sorted({item["code"] for item in validation["issues"] if item["severity"] == "warning"}),
        readiness=readiness.overall,
        draft_ready=readiness.draft_ready,
    )


def evidence_source_response(db: Session, source: InterviewProposalEvidenceSource) -> InterviewEvidenceSourceResponse:
    analysis = db.get(InterviewAnalysis, source.analysis_id)
    document = db.get(InterviewDocument, analysis.document_id) if analysis else None
    return InterviewEvidenceSourceResponse(
        analysis_id=source.analysis_id,
        document_id=document.id if document else "",
        document_title=document.title if document else "",
        segments_sha256=source.segments_sha256,
        selected_fact_indices=source.selected_fact_indices,
        segment_ids=source.segment_ids,
    )


def cross_interview_conflict_response(conflict) -> CrossInterviewConflictResponse:
    return CrossInterviewConflictResponse(
        id=conflict.id,
        session_id=conflict.session_id,
        evidence_sha256=conflict.evidence_sha256,
        summary=conflict.summary,
        question=conflict.question,
        reason=conflict.reason,
        fact_references=conflict.fact_references,
        segment_ids=conflict.segment_ids,
        status=conflict.status,
        resolved_by_user_id=conflict.resolved_by_user_id,
        created_at=conflict.created_at,
        resolved_at=conflict.resolved_at,
    )


def session_response(session: AnalystSession) -> AnalystSessionResponse:
    return AnalystSessionResponse(
        id=session.id,
        project_id=session.project_id,
        started_from_revision_id=session.started_from_revision_id,
        mode=session.mode,
        locale=session.locale,
        status=session.status,
        created_by_user_id=session.created_by_user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def interview_response(db: Session, document: InterviewDocument) -> InterviewDocumentResponse:
    document = enforce_interview_retention(db, document)
    segments = list_interview_segments(db, document.id)
    analysis = latest_interview_analysis(db, document.id) if document.status != "purged" else None
    return InterviewDocumentResponse(
        id=document.id,
        session_id=document.session_id,
        title=document.title,
        source_format=document.source_format,
        source_url=document.source_url,
        language=document.language,
        content_sha256=document.content_sha256,
        segments_sha256=document.segments_sha256,
        status=document.status,
        data_residency=document.data_residency,
        retention_until=document.retention_until,
        purged_at=document.purged_at,
        purge_reason=document.purge_reason,
        segment_count=len(segments),
        segments=[InterviewSegmentResponse(id=item.id, ordinal=item.ordinal, speaker=item.speaker, text=item.text, start_ms=item.start_ms, end_ms=item.end_ms) for item in segments],
        created_at=document.created_at,
        reviewed_at=document.reviewed_at,
        latest_analysis=analysis_response(document, analysis) if analysis else None,
    )


def analysis_response(document: InterviewDocument, analysis: InterviewAnalysis) -> InterviewAnalysisResponse:
    return InterviewAnalysisResponse(
        id=analysis.id,
        document_id=analysis.document_id,
        segments_sha256=analysis.segments_sha256,
        result=analysis.result,
        stale=analysis.segments_sha256 != document.segments_sha256 or document.status != "reviewed",
        provider=analysis.provider,
        model=analysis.model,
        prompt_version=analysis.prompt_version,
        created_at=analysis.created_at,
    )


def session_detail_response(db: Session, session: AnalystSession) -> AnalystSessionDetailResponse:
    return AnalystSessionDetailResponse(
        **session_response(session).model_dump(),
        messages=[message_response(item) for item in list_session_messages(db, session.id)],
        proposed_patches=[proposal_response(item, db) for item in list_session_proposals(db, session.id)],
        interview_documents=[interview_response(db, item) for item in list_session_interviews(db, session.id)],
    )


def _translate_error(error: RuntimeError) -> HTTPException:
    if isinstance(error, ProjectNotFound):
        code, http_status = "project_not_found", 404
    elif isinstance(error, RevisionNotFound):
        code, http_status = "revision_not_found", 404
    elif isinstance(error, AnalystSessionNotFound):
        code, http_status = "analyst_session_not_found", 404
    elif isinstance(error, AnalystMessageNotFound):
        code, http_status = "analyst_message_not_found", 404
    elif isinstance(error, ProposedPatchNotFound):
        code, http_status = "proposed_patch_not_found", 404
    elif isinstance(error, WorkspaceAccessDenied):
        code, http_status = "project_access_denied", 403
    elif isinstance(error, RevisionConflict):
        return HTTPException(
            status_code=409,
            detail={
                "code": "revision_conflict",
                "message": str(error),
                "currentRevisionId": error.current_revision_id,
            },
        )
    elif isinstance(error, ProposedPatchBaseMismatch):
        code, http_status = "proposal_base_mismatch", 409
    elif isinstance(error, ProposedPatchResolved):
        code, http_status = "proposal_already_resolved", 409
    elif isinstance(error, AnalystSessionClosed):
        code, http_status = "analyst_session_closed", 409
    elif isinstance(error, InvalidProcessPatch):
        code, http_status = "invalid_process_change", 422
    else:
        code, http_status = "analyst_error", 500
    return HTTPException(status_code=http_status, detail={"code": code, "message": str(error)})


@router.post(
    "/projects/{project_id}/analyst/sessions",
    response_model=AnalystSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    project_id: str,
    request: AnalystSessionCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> AnalystSessionResponse:
    try:
        session = create_analyst_session(
            db,
            user=current_user,
            project_id=project_id,
            mode=request.mode,
            locale=request.locale,
        )
    except (ProjectNotFound, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return session_response(session)


@router.get(
    "/projects/{project_id}/analyst/sessions",
    response_model=list[AnalystSessionResponse],
)
def list_sessions(
    project_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[AnalystSessionResponse]:
    try:
        require_project_access(db, project_id, current_user.id)
    except (ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return [session_response(item) for item in list_project_sessions(db, project_id)]


@router.get(
    "/analyst/sessions/{session_id}",
    response_model=AnalystSessionDetailResponse,
)
def get_session(
    session_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> AnalystSessionDetailResponse:
    try:
        session = require_session_access(db, session_id, current_user.id)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return session_detail_response(db, session)


@router.post(
    "/analyst/sessions/{session_id}/interviews/preview",
    response_model=InterviewDocumentResponse,
)
def preview_interview(
    session_id: str,
    request: InterviewImportRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> InterviewDocumentResponse:
    try:
        session = require_session_access(db, session_id, current_user.id)
        segments = parse_interview(request.content, request.source_format)
        source_url = validate_source_url(request.source_format, request.source_url)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    except (InterviewSourceInvalid, ValueError) as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_interview_transcript", "message": str(error)}) from error
    return InterviewDocumentResponse(
        title=request.title,
        source_format=request.source_format,
        source_url=source_url,
        language=request.language or session.locale,
        content_sha256=content_hash(request.content),
        segments_sha256=segments_hash(segments),
        status="draft",
        segment_count=len(segments),
        segments=[InterviewSegmentResponse(ordinal=item.ordinal, speaker=item.speaker, text=item.text, start_ms=item.start_ms, end_ms=item.end_ms) for item in segments],
    )


@router.post("/analyst/sessions/{session_id}/interviews/resolve-source", response_model=InterviewSourceResolveResponse)
async def resolve_interview_source(session_id: str, request: InterviewSourceResolveRequest, current_user: CurrentUser, db: DbSession) -> InterviewSourceResolveResponse:
    try:
        require_session_access(db, session_id, current_user.id)
        if request.source_type in {"docx", "odt"}:
            title, content = resolve_file(source_type=request.source_type, content_base64=request.content_base64, filename=request.filename)
        else:
            title, content = await resolve_link(source_type=request.source_type, url=request.url)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    except (InterviewSourceInvalid, httpx.HTTPError, ValueError) as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_interview_source", "message": str(error)}) from error
    return InterviewSourceResolveResponse(title=title, source_format=request.source_type, content=content)


@router.post(
    "/analyst/sessions/{session_id}/interviews",
    response_model=InterviewDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_interview(
    session_id: str,
    request: InterviewImportRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
    _entitlement: InterviewImportEntitlement,
) -> InterviewDocumentResponse:
    try:
        document = create_interview_document(db, user=current_user, session_id=session_id, title=request.title, source_format=request.source_format, language=request.language, content=request.content, source_url=request.source_url, retention_days=settings.transcript_retention_days, data_residency=settings.transcript_data_residency)
    except (AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    except InterviewDuplicate as error:
        raise HTTPException(status_code=409, detail={"code": "interview_already_imported", "message": str(error)}) from error
    except (InterviewSourceInvalid, ValueError) as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_interview_transcript", "message": str(error)}) from error
    return interview_response(db, document)


def _interview_error(error: RuntimeError | ValueError) -> HTTPException:
    if isinstance(error, InterviewNotFound):
        return HTTPException(status_code=404, detail={"code": "interview_not_found", "message": str(error)})
    if isinstance(error, InterviewRevisionConflict):
        return HTTPException(status_code=409, detail={"code": "interview_revision_conflict", "message": str(error)})
    if isinstance(error, InterviewPurged):
        return HTTPException(status_code=410, detail={"code": "interview_content_deleted", "message": str(error)})
    if isinstance(error, (AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, WorkspaceAccessDenied)):
        return _translate_error(error)
    return HTTPException(status_code=422, detail={"code": "invalid_interview_transcript", "message": str(error)})


@router.put("/analyst/interviews/{document_id}", response_model=InterviewDocumentResponse)
def update_interview(document_id: str, request: InterviewUpdateRequest, current_user: CurrentUser, db: DbSession) -> InterviewDocumentResponse:
    try:
        document = update_interview_document(db, user=current_user, document_id=document_id, expected_hash=request.expected_segments_sha256, title=request.title, language=request.language, segments=request.segments)
    except (InterviewNotFound, InterviewPurged, InterviewRevisionConflict, AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, WorkspaceAccessDenied, ValueError) as error:
        raise _interview_error(error) from error
    return interview_response(db, document)


@router.post("/analyst/interviews/{document_id}/review", response_model=InterviewDocumentResponse)
def review_interview(document_id: str, request: InterviewReviewRequest, current_user: CurrentUser, db: DbSession) -> InterviewDocumentResponse:
    try:
        document = review_interview_document(db, user=current_user, document_id=document_id, expected_hash=request.expected_segments_sha256)
    except (InterviewNotFound, InterviewPurged, InterviewRevisionConflict, AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, WorkspaceAccessDenied, ValueError) as error:
        raise _interview_error(error) from error
    return interview_response(db, document)


@router.post("/analyst/interviews/{document_id}/analysis", response_model=InterviewAnalysisResponse)
async def analyze_interview(document_id: str, current_user: CurrentUser, db: DbSession, settings: AppSettings) -> InterviewAnalysisResponse:
    try:
        analysis = await analyze_reviewed_interview(db, user=current_user, document_id=document_id, settings=settings)
        document = db.get(InterviewDocument, document_id)
    except (InterviewNotFound, InterviewPurged, InterviewRevisionConflict, AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _interview_error(error) from error
    except InterviewNotReviewed as error:
        raise HTTPException(status_code=409, detail={"code": "interview_not_reviewed", "message": str(error)}) from error
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail={"code": "llm_not_configured", "message": str(error)}) from error
    except (InvalidInterviewAnalysis, httpx.HTTPError) as error:
        raise HTTPException(status_code=502, detail={"code": "invalid_interview_analysis", "message": str(error)}) from error
    return analysis_response(document, analysis)


@router.delete("/analyst/interviews/{document_id}/content", response_model=InterviewDocumentResponse)
def delete_interview(document_id: str, current_user: CurrentUser, db: DbSession) -> InterviewDocumentResponse:
    try:
        document = delete_interview_content(db, user=current_user, document_id=document_id)
    except (InterviewNotFound, AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _interview_error(error) from error
    return interview_response(db, document)


@router.post("/analyst/interview-analyses/{analysis_id}/proposal", response_model=InterviewProposalResponse, status_code=status.HTTP_201_CREATED)
async def propose_from_interview(analysis_id: str, request: InterviewProposalRequest, current_user: CurrentUser, db: DbSession, settings: AppSettings) -> InterviewProposalResponse:
    try:
        message, proposal, evidence = await create_interview_proposal(db, user=current_user, analysis_id=analysis_id, base_revision_id=request.base_revision_id, selected_indices=request.selected_fact_indices, settings=settings)
    except InterviewAnalysisNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "interview_analysis_not_found", "message": str(error)}) from error
    except InterviewFactSelectionInvalid as error:
        raise HTTPException(status_code=422, detail={"code": "interview_fact_selection_invalid", "message": str(error)}) from error
    except InterviewProposalInvalid as error:
        raise HTTPException(status_code=502, detail={"code": "invalid_interview_proposal", "message": str(error)}) from error
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail={"code": "llm_not_configured", "message": str(error)}) from error
    except (httpx.HTTPError, DeepSeekResponseError) as error:
        raise HTTPException(status_code=502, detail={"code": "llm_request_failed", "message": str(error)}) from error
    except InterviewRevisionConflict as error:
        raise _interview_error(error) from error
    except (AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, RevisionNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return InterviewProposalResponse(
        message=message_response(message),
        proposal=proposal_response(proposal, db),
        evidence=InterviewProposalEvidenceResponse(analysis_id=evidence.analysis_id, segments_sha256=evidence.segments_sha256, selected_fact_indices=evidence.selected_fact_indices, segment_ids=evidence.segment_ids),
    )


@router.post("/analyst/interview-analyses/{analysis_id}/template-match", response_model=InterviewTemplateMatchResponse)
def match_template_from_interview(analysis_id: str, request: InterviewTemplateMatchRequest, current_user: CurrentUser, db: DbSession) -> InterviewTemplateMatchResponse:
    try:
        analysis, confirmed_indices, suggestion = match_interview_template(db, user=current_user, analysis_id=analysis_id, locale=request.locale, excluded_ids=request.excluded_ids)
    except InterviewAnalysisNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "interview_analysis_not_found", "message": str(error)}) from error
    except InterviewRevisionConflict as error:
        raise _interview_error(error) from error
    proposed_rubric_entry_ids = suggestion["template"]["rubric_entry_ids"] if suggestion else []
    return InterviewTemplateMatchResponse(
        analysis_id=analysis.id,
        segments_sha256=analysis.segments_sha256,
        confirmed_fact_indices=confirmed_indices,
        suggestion=suggestion,
        proposed_rubric_entry_ids=proposed_rubric_entry_ids,
    )


@router.post("/analyst/interview-analyses/{analysis_id}/process-draft", response_model=InterviewProposalResponse, status_code=status.HTTP_201_CREATED)
async def draft_process_from_interview(analysis_id: str, request: InterviewProcessDraftRequest, current_user: CurrentUser, db: DbSession, settings: AppSettings) -> InterviewProposalResponse:
    try:
        message, proposal, evidence = await create_interview_process_draft(db, user=current_user, analysis_id=analysis_id, base_revision_id=request.base_revision_id, settings=settings)
    except InterviewAnalysisNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "interview_analysis_not_found", "message": str(error)}) from error
    except InterviewFactSelectionInvalid as error:
        raise HTTPException(status_code=422, detail={"code": "interview_fact_selection_invalid", "message": str(error)}) from error
    except InterviewProposalInvalid as error:
        raise HTTPException(status_code=502, detail={"code": "invalid_interview_proposal", "message": str(error)}) from error
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail={"code": "llm_not_configured", "message": str(error)}) from error
    except (httpx.HTTPError, DeepSeekResponseError) as error:
        raise HTTPException(status_code=502, detail={"code": "llm_request_failed", "message": str(error)}) from error
    except InterviewRevisionConflict as error:
        raise _interview_error(error) from error
    except (AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, RevisionNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return InterviewProposalResponse(message=message_response(message), proposal=proposal_response(proposal, db), evidence=InterviewProposalEvidenceResponse(analysis_id=evidence.analysis_id, segments_sha256=evidence.segments_sha256, selected_fact_indices=evidence.selected_fact_indices, segment_ids=evidence.segment_ids))


@router.get("/analyst/sessions/{session_id}/interview-evidence-summary", response_model=InterviewEvidenceSummaryResponse)
def interview_evidence_summary(session_id: str, current_user: CurrentUser, db: DbSession) -> InterviewEvidenceSummaryResponse:
    try:
        summary = summarize_interview_evidence(db, user=current_user, session_id=session_id)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    semantic = current_cross_interview_conflicts(db, user=current_user, session_id=session_id)
    return InterviewEvidenceSummaryResponse(
        session_id=summary.session_id,
        source_count=summary.source_count,
        confirmed_fact_count=summary.confirmed_fact_count,
        unique_fact_count=summary.unique_fact_count,
        duplicate_fact_count=summary.duplicate_fact_count,
        facts=[InterviewEvidenceFactResponse.model_validate(item) for item in summary.facts],
        contradictions=summary.contradictions,
        clarification_questions=summary.clarification_questions,
        semantic_conflicts_pending=semantic.pending_count,
        semantic_conflicts_confirmed=semantic.confirmed_count,
        semantic_scan_required=summary.source_count >= 2 and semantic.scan is None,
        can_build_draft=summary.can_build_draft and semantic.scan is not None and semantic.pending_count == 0 and semantic.confirmed_count == 0,
    )


@router.post("/analyst/sessions/{session_id}/cross-interview-conflicts/scan", response_model=CrossInterviewConflictScanResponse)
async def scan_interview_conflicts(session_id: str, current_user: CurrentUser, db: DbSession, settings: AppSettings) -> CrossInterviewConflictScanResponse:
    try:
        current = await scan_cross_interview_conflicts(db, user=current_user, session_id=session_id, settings=settings)
    except InvalidCrossInterviewConflict as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_cross_interview_conflicts", "message": str(error)}) from error
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail={"code": "llm_not_configured", "message": str(error)}) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail={"code": "llm_request_failed", "message": str(error)}) from error
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return CrossInterviewConflictScanResponse(session_id=session_id, evidence_sha256=current.evidence_sha256, source_count=current.scan.source_count, fact_count=current.scan.fact_count, conflicts=[cross_interview_conflict_response(item) for item in current.conflicts])


@router.get("/analyst/sessions/{session_id}/cross-interview-conflicts", response_model=CrossInterviewConflictScanResponse)
def list_interview_conflicts(session_id: str, current_user: CurrentUser, db: DbSession) -> CrossInterviewConflictScanResponse:
    try:
        summary = summarize_interview_evidence(db, user=current_user, session_id=session_id)
        current = current_cross_interview_conflicts(db, user=current_user, session_id=session_id)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    evidence_sha256, _, _ = evidence_snapshot(summary)
    return CrossInterviewConflictScanResponse(session_id=session_id, evidence_sha256=evidence_sha256, source_count=summary.source_count, fact_count=summary.confirmed_fact_count, conflicts=[cross_interview_conflict_response(item) for item in current.conflicts])


@router.post("/analyst/cross-interview-conflicts/{conflict_id}/resolve", response_model=CrossInterviewConflictResponse)
def resolve_interview_conflict(conflict_id: str, request: CrossInterviewConflictResolveRequest, current_user: CurrentUser, db: DbSession) -> CrossInterviewConflictResponse:
    try:
        conflict = resolve_cross_interview_conflict(db, user=current_user, conflict_id=conflict_id, action=request.action)
    except CrossInterviewConflictNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "cross_interview_conflict_not_found", "message": str(error)}) from error
    except InvalidCrossInterviewConflict as error:
        raise HTTPException(status_code=409, detail={"code": "cross_interview_conflict_stale", "message": str(error)}) from error
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return cross_interview_conflict_response(conflict)


@router.post("/analyst/sessions/{session_id}/interview-process-draft", response_model=MultiInterviewProposalResponse, status_code=status.HTTP_201_CREATED)
async def draft_process_from_interviews(session_id: str, request: InterviewProcessDraftRequest, current_user: CurrentUser, db: DbSession, settings: AppSettings) -> MultiInterviewProposalResponse:
    try:
        message, proposal, sources, _ = await create_multi_interview_process_draft(db, user=current_user, session_id=session_id, base_revision_id=request.base_revision_id, settings=settings)
    except InterviewFactSelectionInvalid as error:
        raise HTTPException(status_code=409 if "contradiction" in str(error).lower() else 422, detail={"code": "interview_evidence_not_ready", "message": str(error)}) from error
    except InterviewProposalInvalid as error:
        raise HTTPException(status_code=502, detail={"code": "invalid_interview_proposal", "message": str(error)}) from error
    except DeepSeekConfigurationError as error:
        raise HTTPException(status_code=503, detail={"code": "llm_not_configured", "message": str(error)}) from error
    except (httpx.HTTPError, DeepSeekResponseError) as error:
        raise HTTPException(status_code=502, detail={"code": "llm_request_failed", "message": str(error)}) from error
    except (AnalystSessionNotFound, AnalystSessionClosed, ProjectNotFound, RevisionNotFound, RevisionConflict, InvalidProcessPatch, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return MultiInterviewProposalResponse(message=message_response(message), proposal=proposal_response(proposal, db), evidence_sources=[evidence_source_response(db, item) for item in sources])


@router.post(
    "/analyst/sessions/{session_id}/messages",
    response_model=AnalystMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_message(
    session_id: str,
    request: AnalystMessageCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> AnalystMessageResponse:
    try:
        message = add_user_message(
            db,
            user=current_user,
            session_id=session_id,
            content=request.content,
        )
    except (
        AnalystSessionNotFound,
        AnalystSessionClosed,
        ProjectNotFound,
        InvalidProcessPatch,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return message_response(message)


@router.post(
    "/analyst/sessions/{session_id}/turns",
    response_model=AnalystTurnResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_turn(
    session_id: str,
    request: AnalystMessageCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> AnalystTurnResponse:
    try:
        result = await run_analyst_turn(
            db,
            user=current_user,
            session_id=session_id,
            content=request.content,
            settings=settings,
        )
    except DeepSeekConfigurationError as error:
        raise HTTPException(
            status_code=503,
            detail={"code": "llm_not_configured", "message": str(error)},
        ) from error
    except (DeepSeekResponseError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "llm_request_failed", "message": str(error)},
        ) from error
    except BillingUsageLimitExceeded as error:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "billing_usage_limit_reached",
                "metric": error.metric,
                "limit": error.limit,
                "used": error.used,
            },
        ) from error
    except AnalystGeneratedPatchError as error:
        raise HTTPException(
            status_code=502,
            detail={"code": "invalid_llm_patch", "message": str(error)},
        ) from error
    except (
        AnalystSessionNotFound,
        AnalystSessionClosed,
        ProjectNotFound,
        RevisionNotFound,
        InvalidProcessPatch,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return AnalystTurnResponse(
        user_message=message_response(result.user_message),
        assistant_message=message_response(result.assistant_message),
        proposed_patch=(
            proposal_response(result.proposed_patch, db)
            if result.proposed_patch is not None
            else None
        ),
    )


@router.post(
    "/analyst/sessions/{session_id}/proposals",
    response_model=ProposedPatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_proposal(
    session_id: str,
    request: ProposedPatchCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProposedPatchResponse:
    try:
        proposal = create_proposed_patch(
            db,
            user=current_user,
            session_id=session_id,
            base_revision_id=request.base_revision_id,
            patch=request.patch,
            summary=request.summary,
            source_message_id=request.source_message_id,
        )
    except (
        AnalystSessionNotFound,
        AnalystSessionClosed,
        AnalystMessageNotFound,
        ProjectNotFound,
        RevisionNotFound,
        RevisionConflict,
        InvalidProcessPatch,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return proposal_response(proposal, db)


@router.post(
    "/analyst/proposals/{proposal_id}/accept",
    response_model=ProposedPatchResponse,
)
def accept_proposal(
    proposal_id: str,
    request: ProposedPatchResolveRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ProposedPatchResponse:
    try:
        proposal, _ = accept_proposed_patch(
            db,
            user=current_user,
            proposal_id=proposal_id,
            base_revision_id=request.base_revision_id,
        )
    except (
        ProposedPatchNotFound,
        ProposedPatchResolved,
        ProposedPatchBaseMismatch,
        AnalystSessionNotFound,
        ProjectNotFound,
        RevisionConflict,
        InvalidProcessPatch,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return proposal_response(proposal, db)


@router.post(
    "/analyst/proposals/{proposal_id}/reject",
    response_model=ProposedPatchResponse,
)
def reject_proposal(
    proposal_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> ProposedPatchResponse:
    try:
        proposal = reject_proposed_patch(db, user=current_user, proposal_id=proposal_id)
    except (
        ProposedPatchNotFound,
        ProposedPatchResolved,
        AnalystSessionNotFound,
        ProjectNotFound,
        WorkspaceAccessDenied,
    ) as error:
        raise _translate_error(error) from error
    return proposal_response(proposal, db)


@router.post(
    "/analyst/sessions/{session_id}/close",
    response_model=AnalystSessionResponse,
)
def close_session(
    session_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> AnalystSessionResponse:
    try:
        session = close_analyst_session(db, user=current_user, session_id=session_id)
    except (AnalystSessionNotFound, ProjectNotFound, WorkspaceAccessDenied) as error:
        raise _translate_error(error) from error
    return session_response(session)
