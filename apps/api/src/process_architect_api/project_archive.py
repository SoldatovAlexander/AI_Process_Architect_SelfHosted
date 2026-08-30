from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_models import (
    AgentBaselineDecision,
    AgentEvaluationRun,
    AgentIncident,
    AgentRun,
    AgentRunEvent,
    AnalystMessage,
    AnalystSession,
    CrossInterviewConflict,
    CrossInterviewConflictScan,
    InterviewDocument,
    InterviewAnalysis,
    InterviewProposalEvidence,
    InterviewProposalEvidenceSource,
    InterviewSegment,
    N8nImportArtifact,
    ProcessRevision,
    Project,
    ProjectArchiveRestore,
    ProposedPatch,
    User,
)
from .process_ir import upgrade_process_ir
from .services.workspaces import require_membership
from .validation import validate_process_ir


ARCHIVE_FORMAT = "ai-process-architect-project"
ARCHIVE_VERSION = "1.10"
PRODUCT_VERSION = "0.1.0"
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
V1_DATA_FILES = (
    "project.json",
    "revisions.json",
    "analyst-sessions.json",
    "analyst-messages.json",
    "proposed-patches.json",
    "n8n-import-artifacts.json",
)
V1_1_DATA_FILES = (
    *V1_DATA_FILES,
    "agent-runs.json",
    "agent-run-events.json",
)
V1_2_DATA_FILES = (*V1_1_DATA_FILES, "agent-evaluation-runs.json", "agent-baseline-decisions.json")
V1_3_DATA_FILES = (*V1_2_DATA_FILES, "agent-incidents.json")
V1_4_DATA_FILES = (*V1_3_DATA_FILES, "interview-documents.json", "interview-segments.json")
V1_5_DATA_FILES = (*V1_4_DATA_FILES, "interview-analyses.json")
V1_6_DATA_FILES = (*V1_5_DATA_FILES, "interview-proposal-evidence.json")
V1_7_DATA_FILES = (*V1_6_DATA_FILES, "interview-proposal-evidence-sources.json")
DATA_FILES = (*V1_7_DATA_FILES, "cross-interview-conflict-scans.json", "cross-interview-conflicts.json")
SECRET_MARKERS = ("password", "passwd", "secret", "token", "api_key", "apikey", "authorization", "private_key")


class InvalidProjectArchive(ValueError):
    pass


class ProjectArchiveConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedArchive:
    archive_sha256: str
    manifest: dict[str, Any]
    documents: dict[str, Any]
    warnings: list[str]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _secret_paths(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if any(marker in str(key).casefold() for marker in SECRET_MARKERS) and child not in (None, "", {}, []):
                found.append(child_path)
            else:
                found.extend(_secret_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_secret_paths(child, f"{path}/{index}"))
    return found


def _zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def export_project_archive(db: Session, project: Project) -> bytes:
    revisions = list(db.scalars(select(ProcessRevision).where(ProcessRevision.project_id == project.id).order_by(ProcessRevision.version_number)))
    sessions = list(db.scalars(select(AnalystSession).where(AnalystSession.project_id == project.id).order_by(AnalystSession.created_at, AnalystSession.id)))
    session_ids = [item.id for item in sessions]
    messages = list(db.scalars(select(AnalystMessage).where(AnalystMessage.session_id.in_(session_ids)).order_by(AnalystMessage.created_at, AnalystMessage.id))) if session_ids else []
    interview_documents = list(db.scalars(select(InterviewDocument).where(InterviewDocument.session_id.in_(session_ids)).order_by(InterviewDocument.created_at, InterviewDocument.id))) if session_ids else []
    interview_ids = [item.id for item in interview_documents]
    interview_segments = list(db.scalars(select(InterviewSegment).where(InterviewSegment.document_id.in_(interview_ids)).order_by(InterviewSegment.document_id, InterviewSegment.ordinal))) if interview_ids else []
    interview_analyses = list(db.scalars(select(InterviewAnalysis).where(InterviewAnalysis.document_id.in_(interview_ids)).order_by(InterviewAnalysis.created_at, InterviewAnalysis.id))) if interview_ids else []
    proposals = list(db.scalars(select(ProposedPatch).where(ProposedPatch.project_id == project.id).order_by(ProposedPatch.created_at, ProposedPatch.id)))
    proposal_ids = [item.id for item in proposals]
    interview_proposal_evidence = list(db.scalars(select(InterviewProposalEvidence).where(InterviewProposalEvidence.proposal_id.in_(proposal_ids)).order_by(InterviewProposalEvidence.created_at, InterviewProposalEvidence.proposal_id))) if proposal_ids else []
    interview_proposal_evidence_sources = list(db.scalars(select(InterviewProposalEvidenceSource).where(InterviewProposalEvidenceSource.proposal_id.in_(proposal_ids)).order_by(InterviewProposalEvidenceSource.proposal_id, InterviewProposalEvidenceSource.analysis_id))) if proposal_ids else []
    cross_interview_conflict_scans = list(db.scalars(select(CrossInterviewConflictScan).where(CrossInterviewConflictScan.session_id.in_(session_ids)).order_by(CrossInterviewConflictScan.created_at, CrossInterviewConflictScan.id))) if session_ids else []
    cross_interview_conflicts = list(db.scalars(select(CrossInterviewConflict).where(CrossInterviewConflict.session_id.in_(session_ids)).order_by(CrossInterviewConflict.created_at, CrossInterviewConflict.id))) if session_ids else []
    artifacts = list(db.scalars(select(N8nImportArtifact).where(N8nImportArtifact.project_id == project.id).order_by(N8nImportArtifact.created_at, N8nImportArtifact.id)))
    runs = list(db.scalars(select(AgentRun).where(AgentRun.project_id == project.id).order_by(AgentRun.created_at, AgentRun.id)))
    run_ids = [item.id for item in runs]
    run_events = list(db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id.in_(run_ids)).order_by(AgentRunEvent.run_id, AgentRunEvent.sequence))) if run_ids else []
    evaluations = list(db.scalars(select(AgentEvaluationRun).where(AgentEvaluationRun.project_id == project.id).order_by(AgentEvaluationRun.created_at, AgentEvaluationRun.id)))
    evaluation_ids = [item.id for item in evaluations]
    baseline_decisions = list(db.scalars(select(AgentBaselineDecision).where(AgentBaselineDecision.project_id == project.id).order_by(AgentBaselineDecision.created_at, AgentBaselineDecision.id)))
    incidents = list(db.scalars(select(AgentIncident).where(AgentIncident.project_id == project.id).order_by(AgentIncident.created_at, AgentIncident.id)))

    documents: dict[str, Any] = {
        "project.json": {"id": project.id, "name": project.name, "description": project.description, "default_locale": project.default_locale, "status": project.status, "target_mode": project.target_mode, "current_revision_id": project.current_revision_id, "created_at": _datetime(project.created_at), "updated_at": _datetime(project.updated_at)},
        "revisions.json": [{"id": item.id, "version_number": item.version_number, "schema_version": item.schema_version, "process_ir": item.process_ir, "forward_patch": item.forward_patch, "inverse_patch": item.inverse_patch, "validation_result": item.validation_result, "parent_revision_id": item.parent_revision_id, "restored_from_revision_id": item.restored_from_revision_id, "source": item.source, "perspective": item.perspective, "created_at": _datetime(item.created_at)} for item in revisions],
        "analyst-sessions.json": [{"id": item.id, "started_from_revision_id": item.started_from_revision_id, "mode": item.mode, "locale": item.locale, "status": item.status, "created_at": _datetime(item.created_at), "updated_at": _datetime(item.updated_at)} for item in sessions],
        "analyst-messages.json": [{"id": item.id, "session_id": item.session_id, "revision_id": item.revision_id, "role": item.role, "content": item.content, "locale": item.locale, "provider": item.provider, "model": item.model, "prompt_version": item.prompt_version, "authorship": "user" if item.created_by_user_id else "assistant", "created_at": _datetime(item.created_at)} for item in messages],
        "interview-documents.json": [{"id": item.id, "session_id": item.session_id, "title": item.title, "source_format": item.source_format, "source_url": item.source_url, "language": item.language, "original_text": item.original_text, "content_sha256": item.content_sha256, "segments_sha256": item.segments_sha256, "status": item.status, "data_residency": item.data_residency, "retention_until": _datetime(item.retention_until), "purged_at": _datetime(item.purged_at), "purge_reason": item.purge_reason, "reviewed": item.reviewed_by_user_id is not None, "reviewed_at": _datetime(item.reviewed_at), "created_at": _datetime(item.created_at), "updated_at": _datetime(item.updated_at)} for item in interview_documents],
        "interview-segments.json": [{"id": item.id, "document_id": item.document_id, "ordinal": item.ordinal, "speaker": item.speaker, "text": item.text, "start_ms": item.start_ms, "end_ms": item.end_ms, "created_at": _datetime(item.created_at)} for item in interview_segments],
        "interview-analyses.json": [{"id": item.id, "document_id": item.document_id, "segments_sha256": item.segments_sha256, "result": item.result, "provider": item.provider, "model": item.model, "prompt_version": item.prompt_version, "created_at": _datetime(item.created_at)} for item in interview_analyses],
        "interview-proposal-evidence.json": [{"proposal_id": item.proposal_id, "analysis_id": item.analysis_id, "segments_sha256": item.segments_sha256, "selected_fact_indices": item.selected_fact_indices, "segment_ids": item.segment_ids, "created_at": _datetime(item.created_at)} for item in interview_proposal_evidence],
        "interview-proposal-evidence-sources.json": [{"id": item.id, "proposal_id": item.proposal_id, "analysis_id": item.analysis_id, "segments_sha256": item.segments_sha256, "selected_fact_indices": item.selected_fact_indices, "segment_ids": item.segment_ids, "created_at": _datetime(item.created_at)} for item in interview_proposal_evidence_sources],
        "cross-interview-conflict-scans.json": [{"id": item.id, "session_id": item.session_id, "evidence_sha256": item.evidence_sha256, "source_count": item.source_count, "fact_count": item.fact_count, "provider": item.provider, "model": item.model, "prompt_version": item.prompt_version, "created_at": _datetime(item.created_at)} for item in cross_interview_conflict_scans],
        "cross-interview-conflicts.json": [{"id": item.id, "session_id": item.session_id, "evidence_sha256": item.evidence_sha256, "fingerprint": item.fingerprint, "summary": item.summary, "question": item.question, "reason": item.reason, "fact_references": item.fact_references, "segment_ids": item.segment_ids, "status": item.status, "provider": item.provider, "model": item.model, "prompt_version": item.prompt_version, "resolved": item.resolved_by_user_id is not None, "created_at": _datetime(item.created_at), "resolved_at": _datetime(item.resolved_at)} for item in cross_interview_conflicts],
        "proposed-patches.json": [{"id": item.id, "session_id": item.session_id, "base_revision_id": item.base_revision_id, "source_message_id": item.source_message_id, "patch": item.patch, "summary": item.summary, "validation_result": item.validation_result, "status": item.status, "accepted_revision_id": item.accepted_revision_id, "created_at": _datetime(item.created_at), "resolved_at": _datetime(item.resolved_at)} for item in proposals],
        "n8n-import-artifacts.json": [{"id": item.id, "revision_id": item.revision_id, "source_minor": item.source_minor, "workflow_name": item.workflow_name, "source_sha256": item.source_sha256, "source_workflow": item.source_workflow, "diagnostics": item.diagnostics, "created_at": _datetime(item.created_at)} for item in artifacts],
        "agent-runs.json": [{"id": item.id, "revision_id": item.revision_id, "runtime": item.runtime, "status": item.status, "contract_version": item.contract_version, "idempotency_key": item.idempotency_key, "max_steps": item.max_steps, "max_tool_calls": item.max_tool_calls, "timeout_seconds": item.timeout_seconds, "max_cost_microunits": item.max_cost_microunits, "steps_used": item.steps_used, "tool_calls_used": item.tool_calls_used, "cost_microunits": item.cost_microunits, "started_at": _datetime(item.started_at), "ended_at": _datetime(item.ended_at), "created_at": _datetime(item.created_at), "updated_at": _datetime(item.updated_at)} for item in runs],
        "agent-run-events.json": [{"id": item.id, "run_id": item.run_id, "sequence": item.sequence, "event_type": item.event_type, "external_event_id": item.external_event_id, "actor_type": item.actor_type, "reason_code": item.reason_code, "metrics": item.metrics, "created_at": _datetime(item.created_at)} for item in run_events],
        "agent-evaluation-runs.json": [{"id": item.id, "revision_id": item.revision_id, "runtime": item.runtime, "suite_version": item.suite_version, "status": item.status, "model_fingerprint": item.model_fingerprint, "results": item.results, "passed_count": item.passed_count, "total_count": item.total_count, "cost_microunits": item.cost_microunits, "duration_ms": item.duration_ms, "created_at": _datetime(item.created_at)} for item in evaluations],
        "agent-baseline-decisions.json": [{"id": item.id, "evaluation_run_id": item.evaluation_run_id, "runtime": item.runtime, "action": item.action, "reason_code": item.reason_code, "created_at": _datetime(item.created_at)} for item in baseline_decisions],
        "agent-incidents.json": [{"id": item.id, "run_id": item.run_id, "status": item.status, "category": item.category, "reason_code": item.reason_code, "resolution_code": item.resolution_code, "replay_run_id": item.replay_run_id, "resolved_at": _datetime(item.resolved_at), "created_at": _datetime(item.created_at), "updated_at": _datetime(item.updated_at)} for item in incidents],
    }
    secret_paths = _secret_paths(documents)
    if secret_paths:
        raise InvalidProjectArchive("Archive contains secret-like values: " + ", ".join(secret_paths[:8]))
    files = {path: _json_bytes(document) for path, document in documents.items()}
    counts = {"revisions": len(revisions), "sessions": len(sessions), "messages": len(messages), "interviewDocuments": len(interview_documents), "interviewSegments": len(interview_segments), "interviewAnalyses": len(interview_analyses), "interviewProposalEvidence": len(interview_proposal_evidence), "interviewProposalEvidenceSources": len(interview_proposal_evidence_sources), "crossInterviewConflictScans": len(cross_interview_conflict_scans), "crossInterviewConflicts": len(cross_interview_conflicts), "proposals": len(proposals), "n8nArtifacts": len(artifacts), "agentRuns": len(runs), "agentRunEvents": len(run_events), "agentEvaluations": len(evaluations), "agentBaselineDecisions": len(baseline_decisions), "agentIncidents": len(incidents)}
    manifest = {
        "format": ARCHIVE_FORMAT,
        "formatVersion": ARCHIVE_VERSION,
        "productVersion": PRODUCT_VERSION,
        "sourceProjectId": project.id,
        "createdAt": _datetime(project.updated_at),
        "compatibility": {"minimumProductVersion": PRODUCT_VERSION, "processIrVersions": sorted({item.schema_version for item in revisions})},
        "counts": counts,
        "files": {path: {"sha256": _sha256(content), "bytes": len(content)} for path, content in sorted(files.items())},
        "secretsIncluded": False,
    }
    files["manifest.json"] = _json_bytes(manifest)
    return _zip(files)


def validate_project_archive(content: bytes) -> ValidatedArchive:
    if not content or len(content) > MAX_ARCHIVE_BYTES:
        raise InvalidProjectArchive("Archive is empty or exceeds the 25 MB limit.")
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            if "manifest.json" not in names:
                raise InvalidProjectArchive("Archive does not contain a manifest.")
            manifest = json.loads(archive.read("manifest.json"))
            version = manifest.get("formatVersion")
            selected_files = V1_DATA_FILES if version == "1.0" else V1_1_DATA_FILES if version == "1.1" else V1_2_DATA_FILES if version == "1.2" else V1_3_DATA_FILES if version == "1.3" else V1_4_DATA_FILES if version == "1.4" else V1_5_DATA_FILES if version == "1.5" else V1_6_DATA_FILES if version == "1.6" else V1_7_DATA_FILES if version == "1.7" else DATA_FILES
            expected = {"manifest.json", *selected_files}
            if set(names) != expected or len(names) != len(expected):
                raise InvalidProjectArchive("Archive must contain exactly the documented project files.")
            if sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_BYTES:
                raise InvalidProjectArchive("Uncompressed archive contents exceed the 25 MB limit.")
            raw = {name: archive.read(name) for name in names}
    except (BadZipFile, KeyError, RuntimeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidProjectArchive("Archive is not a readable project ZIP.") from error
    try:
        manifest = json.loads(raw["manifest.json"])
        selected_files = V1_DATA_FILES if manifest.get("formatVersion") == "1.0" else V1_1_DATA_FILES if manifest.get("formatVersion") == "1.1" else V1_2_DATA_FILES if manifest.get("formatVersion") == "1.2" else V1_3_DATA_FILES if manifest.get("formatVersion") == "1.3" else V1_4_DATA_FILES if manifest.get("formatVersion") == "1.4" else V1_5_DATA_FILES if manifest.get("formatVersion") == "1.5" else V1_6_DATA_FILES if manifest.get("formatVersion") == "1.6" else V1_7_DATA_FILES if manifest.get("formatVersion") == "1.7" else DATA_FILES
        documents = {path: json.loads(raw[path]) for path in selected_files}
        documents.setdefault("agent-runs.json", [])
        documents.setdefault("agent-run-events.json", [])
        documents.setdefault("agent-evaluation-runs.json", [])
        documents.setdefault("agent-baseline-decisions.json", [])
        documents.setdefault("agent-incidents.json", [])
        documents.setdefault("interview-documents.json", [])
        documents.setdefault("interview-segments.json", [])
        documents.setdefault("interview-analyses.json", [])
        documents.setdefault("interview-proposal-evidence.json", [])
        documents.setdefault("interview-proposal-evidence-sources.json", [])
        documents.setdefault("cross-interview-conflict-scans.json", [])
        documents.setdefault("cross-interview-conflicts.json", [])
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidProjectArchive("Archive contains invalid JSON.") from error
    if manifest.get("format") != ARCHIVE_FORMAT or manifest.get("formatVersion") not in {"1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", ARCHIVE_VERSION}:
        raise InvalidProjectArchive("Unsupported project archive format or version.")
    if manifest.get("secretsIncluded") is not False:
        raise InvalidProjectArchive("Archive does not declare secretsIncluded=false.")
    selected_files = V1_DATA_FILES if manifest.get("formatVersion") == "1.0" else V1_1_DATA_FILES if manifest.get("formatVersion") == "1.1" else V1_2_DATA_FILES if manifest.get("formatVersion") == "1.2" else V1_3_DATA_FILES if manifest.get("formatVersion") == "1.3" else V1_4_DATA_FILES if manifest.get("formatVersion") == "1.4" else V1_5_DATA_FILES if manifest.get("formatVersion") == "1.5" else V1_6_DATA_FILES if manifest.get("formatVersion") == "1.6" else V1_7_DATA_FILES if manifest.get("formatVersion") == "1.7" else DATA_FILES
    for path in selected_files:
        expected = manifest.get("files", {}).get(path, {})
        if expected.get("sha256") != _sha256(raw[path]) or expected.get("bytes") != len(raw[path]):
            raise InvalidProjectArchive(f"Checksum or size mismatch for {path}.")
    if _secret_paths(documents):
        raise InvalidProjectArchive("Archive contains secret-like values and cannot be restored.")
    _validate_links(manifest, documents)
    return ValidatedArchive(_sha256(content), manifest, documents, ["External credentials must be configured on the destination server."])


def _validate_links(manifest: dict[str, Any], documents: dict[str, Any]) -> None:
    project = documents["project.json"]
    revisions = documents["revisions.json"]
    sessions = documents["analyst-sessions.json"]
    messages = documents["analyst-messages.json"]
    interview_documents = documents["interview-documents.json"]
    interview_segments = documents["interview-segments.json"]
    interview_analyses = documents["interview-analyses.json"]
    interview_proposal_evidence = documents["interview-proposal-evidence.json"]
    interview_proposal_evidence_sources = documents["interview-proposal-evidence-sources.json"]
    cross_interview_conflict_scans = documents["cross-interview-conflict-scans.json"]
    cross_interview_conflicts = documents["cross-interview-conflicts.json"]
    proposals = documents["proposed-patches.json"]
    artifacts = documents["n8n-import-artifacts.json"]
    runs = documents["agent-runs.json"]
    run_events = documents["agent-run-events.json"]
    evaluations = documents["agent-evaluation-runs.json"]
    baseline_decisions = documents["agent-baseline-decisions.json"]
    incidents = documents["agent-incidents.json"]
    if not isinstance(project, dict) or not all(isinstance(items, list) for items in (revisions, sessions, messages, interview_documents, interview_segments, interview_analyses, interview_proposal_evidence, interview_proposal_evidence_sources, cross_interview_conflict_scans, cross_interview_conflicts, proposals, artifacts, runs, run_events, evaluations, baseline_decisions, incidents)):
        raise InvalidProjectArchive("Project archive document shapes are invalid.")
    revision_ids = {item.get("id") for item in revisions}
    session_ids = {item.get("id") for item in sessions}
    message_ids = {item.get("id") for item in messages}
    if len(revision_ids) != len(revisions) or project.get("current_revision_id") not in revision_ids:
        raise InvalidProjectArchive("Revision IDs or current revision are invalid.")
    if sorted(item.get("version_number") for item in revisions) != list(range(1, len(revisions) + 1)):
        raise InvalidProjectArchive("Revision version numbers must be contiguous from 1.")
    for item in revisions:
        if item.get("parent_revision_id") not in revision_ids | {None} or item.get("restored_from_revision_id") not in revision_ids | {None}:
            raise InvalidProjectArchive("Revision history contains an unknown link.")
        try:
            validation = validate_process_ir(upgrade_process_ir(item.get("process_ir")))
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise InvalidProjectArchive(
                f"Revision {item.get('id')} contains malformed Process IR."
            ) from error
        if not validation.valid:
            raise InvalidProjectArchive(f"Revision {item.get('id')} contains invalid Process IR.")
    if any(item.get("started_from_revision_id") not in revision_ids for item in sessions):
        raise InvalidProjectArchive("Analyst session references an unknown revision.")
    if any(item.get("session_id") not in session_ids or item.get("revision_id") not in revision_ids for item in messages):
        raise InvalidProjectArchive("Analyst message contains an unknown link.")
    interview_ids = {item.get("id") for item in interview_documents}
    if len(interview_ids) != len(interview_documents) or any(item.get("session_id") not in session_ids for item in interview_documents):
        raise InvalidProjectArchive("Interview document contains an unknown session link.")
    if any(item.get("document_id") not in interview_ids for item in interview_segments):
        raise InvalidProjectArchive("Interview segment contains an unknown document link.")
    analysis_ids = {item.get("id") for item in interview_analyses}
    if len(analysis_ids) != len(interview_analyses) or any(item.get("document_id") not in interview_ids for item in interview_analyses):
        raise InvalidProjectArchive("Interview analysis contains an unknown document link.")
    segments_by_document: dict[str, set[str]] = {}
    for segment in interview_segments:
        segments_by_document.setdefault(segment.get("document_id"), set()).add(segment.get("id"))
    for analysis in interview_analyses:
        allowed = segments_by_document.get(analysis.get("document_id"), set())
        result = analysis.get("result", {})
        collections = (result.get("confirmed_facts", []), result.get("candidate_facts", []), result.get("contradictions", []), result.get("clarification_questions", []))
        cited = [segment_id for collection in collections for item in collection for segment_id in item.get("segment_ids", [])]
        if any(segment_id not in allowed for segment_id in cited):
            raise InvalidProjectArchive("Interview analysis cites a segment outside its document.")
    analysis_by_id = {item.get("id"): item for item in interview_analyses}
    proposal_ids = {item.get("id") for item in proposals}
    evidence_proposal_ids = [item.get("proposal_id") for item in interview_proposal_evidence]
    if len(evidence_proposal_ids) != len(set(evidence_proposal_ids)):
        raise InvalidProjectArchive("Interview proposal evidence contains duplicate proposal links.")
    for evidence in interview_proposal_evidence:
        analysis = analysis_by_id.get(evidence.get("analysis_id"))
        if evidence.get("proposal_id") not in proposal_ids or analysis is None:
            raise InvalidProjectArchive("Interview proposal evidence contains an unknown link.")
        confirmed = analysis.get("result", {}).get("confirmed_facts", [])
        indices = evidence.get("selected_fact_indices", [])
        if not indices or len(indices) != len(set(indices)) or any(not isinstance(index, int) or index < 0 or index >= len(confirmed) for index in indices):
            raise InvalidProjectArchive("Interview proposal evidence selects invalid facts.")
        expected_segments = sorted({segment_id for index in indices for segment_id in confirmed[index].get("segment_ids", [])})
        if evidence.get("segments_sha256") != analysis.get("segments_sha256") or sorted(evidence.get("segment_ids", [])) != expected_segments:
            raise InvalidProjectArchive("Interview proposal evidence does not match selected facts.")
    source_ids = [item.get("id") for item in interview_proposal_evidence_sources]
    source_links = [(item.get("proposal_id"), item.get("analysis_id")) for item in interview_proposal_evidence_sources]
    if len(source_ids) != len(set(source_ids)) or len(source_links) != len(set(source_links)):
        raise InvalidProjectArchive("Interview proposal evidence sources contain duplicate IDs or links.")
    for evidence in interview_proposal_evidence_sources:
        analysis = analysis_by_id.get(evidence.get("analysis_id"))
        if evidence.get("proposal_id") not in proposal_ids or analysis is None:
            raise InvalidProjectArchive("Interview proposal evidence source contains an unknown link.")
        confirmed = analysis.get("result", {}).get("confirmed_facts", [])
        indices = evidence.get("selected_fact_indices", [])
        if not indices or len(indices) != len(set(indices)) or any(not isinstance(index, int) or index < 0 or index >= len(confirmed) for index in indices):
            raise InvalidProjectArchive("Interview proposal evidence source selects invalid facts.")
        expected_segments = sorted({segment_id for index in indices for segment_id in confirmed[index].get("segment_ids", [])})
        if evidence.get("segments_sha256") != analysis.get("segments_sha256") or sorted(evidence.get("segment_ids", [])) != expected_segments:
            raise InvalidProjectArchive("Interview proposal evidence source does not match selected facts.")
    analyses_by_session: dict[str, list[dict]] = {}
    document_by_id = {item.get("id"): item for item in interview_documents}
    for analysis in interview_analyses:
        document = document_by_id.get(analysis.get("document_id"))
        if document and document.get("status") == "reviewed" and document.get("segments_sha256") == analysis.get("segments_sha256"):
            analyses_by_session.setdefault(document.get("session_id"), []).append(analysis)
    def semantic_snapshot(session_id: str) -> tuple[str, dict[tuple[str, int], dict]]:
        facts = []
        lookup = {}
        for analysis in analyses_by_session.get(session_id, []):
            document = document_by_id[analysis["document_id"]]
            for index, fact in enumerate(analysis.get("result", {}).get("confirmed_facts", [])):
                item = {"analysis_id": analysis["id"], "fact_index": index, "statement": fact["statement"], "document_id": document["id"], "document_title": document["title"], "segment_ids": fact["segment_ids"], "segments_sha256": analysis["segments_sha256"]}
                facts.append(item); lookup[(analysis["id"], index)] = item
        facts.sort(key=lambda item: (item["analysis_id"], item["fact_index"]))
        digest = _sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
        return digest, lookup
    scan_ids = [item.get("id") for item in cross_interview_conflict_scans]
    scan_links = [(item.get("session_id"), item.get("evidence_sha256")) for item in cross_interview_conflict_scans]
    if len(scan_ids) != len(set(scan_ids)) or len(scan_links) != len(set(scan_links)):
        raise InvalidProjectArchive("Cross-interview conflict scans contain duplicate IDs or evidence links.")
    scans_by_link = {}
    for scan in cross_interview_conflict_scans:
        if scan.get("session_id") not in session_ids:
            raise InvalidProjectArchive("Cross-interview conflict scan references an unknown session.")
        expected_hash, lookup = semantic_snapshot(scan["session_id"])
        if scan.get("evidence_sha256") != expected_hash or scan.get("source_count") != len(analyses_by_session.get(scan["session_id"], [])) or scan.get("fact_count") != len(lookup):
            raise InvalidProjectArchive("Cross-interview conflict scan does not match current evidence.")
        scans_by_link[(scan["session_id"], scan["evidence_sha256"])] = scan
    conflict_ids = [item.get("id") for item in cross_interview_conflicts]
    conflict_links = [(item.get("session_id"), item.get("evidence_sha256"), item.get("fingerprint")) for item in cross_interview_conflicts]
    if len(conflict_ids) != len(set(conflict_ids)) or len(conflict_links) != len(set(conflict_links)):
        raise InvalidProjectArchive("Cross-interview conflicts contain duplicate IDs or fingerprints.")
    for conflict in cross_interview_conflicts:
        link = (conflict.get("session_id"), conflict.get("evidence_sha256"))
        if link not in scans_by_link or conflict.get("status") not in {"pending", "confirmed", "dismissed"}:
            raise InvalidProjectArchive("Cross-interview conflict has no matching scan or invalid status.")
        _, lookup = semantic_snapshot(conflict["session_id"])
        refs = [(item.get("analysis_id"), item.get("fact_index")) for item in conflict.get("fact_references", [])]
        if len(refs) < 2 or len(refs) != len(set(refs)) or len({item[0] for item in refs}) < 2 or any(ref not in lookup for ref in refs):
            raise InvalidProjectArchive("Cross-interview conflict cites invalid facts.")
        fingerprint = _sha256("|".join(sorted(f"{analysis_id}:{index}" for analysis_id, index in refs)).encode())
        expected_segments = sorted({segment_id for ref in refs for segment_id in lookup[ref]["segment_ids"]})
        resolved = conflict.get("status") != "pending"
        if conflict.get("fingerprint") != fingerprint or sorted(conflict.get("segment_ids", [])) != expected_segments or bool(conflict.get("resolved")) != resolved or bool(conflict.get("resolved_at")) != resolved:
            raise InvalidProjectArchive("Cross-interview conflict provenance or resolution is invalid.")
    for item in proposals:
        if item.get("session_id") not in session_ids or item.get("base_revision_id") not in revision_ids or item.get("source_message_id") not in message_ids | {None} or item.get("accepted_revision_id") not in revision_ids | {None}:
            raise InvalidProjectArchive("Proposed patch contains an unknown link.")
    if any(item.get("revision_id") not in revision_ids for item in artifacts):
        raise InvalidProjectArchive("n8n artifact references an unknown revision.")
    run_ids = {item.get("id") for item in runs}
    if len(run_ids) != len(runs) or any(item.get("revision_id") not in revision_ids for item in runs):
        raise InvalidProjectArchive("Agent run IDs or revision links are invalid.")
    if any(item.get("run_id") not in run_ids for item in run_events):
        raise InvalidProjectArchive("Agent run event references an unknown run.")
    for run_id in run_ids:
        sequences = sorted(item.get("sequence") for item in run_events if item.get("run_id") == run_id)
        if sequences != list(range(1, len(sequences) + 1)):
            raise InvalidProjectArchive("Agent run event sequences must be contiguous from 1.")
    evaluation_ids = {item.get("id") for item in evaluations}
    if len(evaluation_ids) != len(evaluations) or any(item.get("revision_id") not in revision_ids for item in evaluations):
        raise InvalidProjectArchive("Agent evaluation IDs or revision links are invalid.")
    if any(item.get("evaluation_run_id") not in evaluation_ids for item in baseline_decisions):
        raise InvalidProjectArchive("Agent baseline decision references an unknown evaluation.")
    incident_ids = {item.get("id") for item in incidents}
    if len(incident_ids) != len(incidents) or any(item.get("run_id") not in run_ids or item.get("replay_run_id") not in run_ids | {None} for item in incidents):
        raise InvalidProjectArchive("Agent incident contains an unknown run link.")
    actual_counts = {"revisions": len(revisions), "sessions": len(sessions), "messages": len(messages), "interviewDocuments": len(interview_documents), "interviewSegments": len(interview_segments), "interviewAnalyses": len(interview_analyses), "interviewProposalEvidence": len(interview_proposal_evidence), "interviewProposalEvidenceSources": len(interview_proposal_evidence_sources), "crossInterviewConflictScans": len(cross_interview_conflict_scans), "crossInterviewConflicts": len(cross_interview_conflicts), "proposals": len(proposals), "n8nArtifacts": len(artifacts), "agentRuns": len(runs), "agentRunEvents": len(run_events), "agentEvaluations": len(evaluations), "agentBaselineDecisions": len(baseline_decisions), "agentIncidents": len(incidents)}
    version = manifest.get("formatVersion")
    excluded = {"agentRuns", "agentRunEvents", "agentEvaluations", "agentBaselineDecisions", "agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.0" else {"agentEvaluations", "agentBaselineDecisions", "agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.1" else {"agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.2" else {"interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.3" else {"interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.4" else {"interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.5" else {"interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.6" else {"crossInterviewConflictScans", "crossInterviewConflicts"} if version == "1.7" else set()
    expected_counts = {key: value for key, value in actual_counts.items() if key not in excluded}
    if manifest.get("counts") != expected_counts:
        raise InvalidProjectArchive("Manifest counts do not match archive contents.")


def restore_project_archive(db: Session, *, validated: ValidatedArchive, workspace_id: str, user: User) -> tuple[Project, bool]:
    require_membership(db, workspace_id, user.id)
    existing_restore = db.scalar(select(ProjectArchiveRestore).where(ProjectArchiveRestore.archive_sha256 == validated.archive_sha256))
    if existing_restore:
        project = db.get(Project, existing_restore.restored_project_id)
        if project is not None and project.workspace_id == workspace_id:
            return project, True
        raise ProjectArchiveConflict("This archive was already restored into another workspace.")
    data = validated.documents
    project_data = data["project.json"]
    id_checks = (
        (Project, [project_data["id"]]),
        (ProcessRevision, [item["id"] for item in data["revisions.json"]]),
        (AnalystSession, [item["id"] for item in data["analyst-sessions.json"]]),
        (AnalystMessage, [item["id"] for item in data["analyst-messages.json"]]),
        (InterviewDocument, [item["id"] for item in data["interview-documents.json"]]),
        (InterviewSegment, [item["id"] for item in data["interview-segments.json"]]),
        (InterviewAnalysis, [item["id"] for item in data["interview-analyses.json"]]),
        (InterviewProposalEvidenceSource, [item["id"] for item in data["interview-proposal-evidence-sources.json"]]),
        (CrossInterviewConflictScan, [item["id"] for item in data["cross-interview-conflict-scans.json"]]),
        (CrossInterviewConflict, [item["id"] for item in data["cross-interview-conflicts.json"]]),
        (ProposedPatch, [item["id"] for item in data["proposed-patches.json"]]),
        (N8nImportArtifact, [item["id"] for item in data["n8n-import-artifacts.json"]]),
        (AgentRun, [item["id"] for item in data["agent-runs.json"]]),
        (AgentRunEvent, [item["id"] for item in data["agent-run-events.json"]]),
        (AgentEvaluationRun, [item["id"] for item in data["agent-evaluation-runs.json"]]),
        (AgentBaselineDecision, [item["id"] for item in data["agent-baseline-decisions.json"]]),
        (AgentIncident, [item["id"] for item in data["agent-incidents.json"]]),
    )
    for model, identifiers in id_checks:
        if identifiers and db.scalar(select(model.id).where(model.id.in_(identifiers)).limit(1)):
            raise ProjectArchiveConflict("An object with a source archive ID already exists.")
    project = Project(
        id=project_data["id"], workspace_id=workspace_id, name=project_data["name"], description=project_data.get("description", ""), default_locale=project_data["default_locale"], status=project_data["status"], target_mode=project_data["target_mode"], current_revision_id=None, created_by_user_id=user.id, created_at=_parse_datetime(project_data["created_at"]), updated_at=_parse_datetime(project_data["updated_at"]),
    )
    try:
        db.add(project)
        db.flush()
        for item in data["revisions.json"]:
            db.add(ProcessRevision(id=item["id"], project_id=project.id, version_number=item["version_number"], schema_version=item["schema_version"], process_ir=item["process_ir"], forward_patch=item["forward_patch"], inverse_patch=item["inverse_patch"], validation_result=item["validation_result"], parent_revision_id=item["parent_revision_id"], restored_from_revision_id=item["restored_from_revision_id"], source=item["source"], perspective=item["perspective"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        db.flush()
        project.current_revision_id = project_data["current_revision_id"]
        for item in data["analyst-sessions.json"]:
            db.add(AnalystSession(id=item["id"], project_id=project.id, started_from_revision_id=item["started_from_revision_id"], mode=item["mode"], locale=item["locale"], status=item["status"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"]), updated_at=_parse_datetime(item["updated_at"])))
        db.flush()
        for item in data["analyst-messages.json"]:
            db.add(AnalystMessage(id=item["id"], session_id=item["session_id"], revision_id=item["revision_id"], role=item["role"], content=item["content"], locale=item["locale"], provider=item["provider"], model=item["model"], prompt_version=item["prompt_version"], created_by_user_id=user.id if item["authorship"] == "user" else None, created_at=_parse_datetime(item["created_at"])))
        db.flush()
        for item in data["interview-documents.json"]:
            db.add(InterviewDocument(id=item["id"], session_id=item["session_id"], title=item["title"], source_format=item["source_format"], source_url=item.get("source_url"), language=item["language"], original_text=item["original_text"], content_sha256=item["content_sha256"], segments_sha256=item["segments_sha256"], status=item["status"], data_residency=item.get("data_residency", "local"), retention_until=_parse_datetime(item.get("retention_until")), purged_at=_parse_datetime(item.get("purged_at")), purge_reason=item.get("purge_reason"), reviewed_by_user_id=user.id if item.get("reviewed") else None, reviewed_at=_parse_datetime(item.get("reviewed_at")), created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"]), updated_at=_parse_datetime(item["updated_at"])))
        db.flush()
        for item in data["interview-segments.json"]:
            db.add(InterviewSegment(id=item["id"], document_id=item["document_id"], ordinal=item["ordinal"], speaker=item["speaker"], text=item["text"], start_ms=item["start_ms"], end_ms=item["end_ms"], created_at=_parse_datetime(item["created_at"])))
        db.flush()
        for item in data["interview-analyses.json"]:
            db.add(InterviewAnalysis(id=item["id"], document_id=item["document_id"], segments_sha256=item["segments_sha256"], result=item["result"], provider=item["provider"], model=item["model"], prompt_version=item["prompt_version"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        db.flush()
        for item in data["proposed-patches.json"]:
            db.add(ProposedPatch(id=item["id"], session_id=item["session_id"], project_id=project.id, base_revision_id=item["base_revision_id"], source_message_id=item["source_message_id"], patch=item["patch"], summary=item["summary"], validation_result=item["validation_result"], status=item["status"], accepted_revision_id=item["accepted_revision_id"], created_by_user_id=user.id, resolved_by_user_id=user.id if item["resolved_at"] else None, created_at=_parse_datetime(item["created_at"]), resolved_at=_parse_datetime(item["resolved_at"])))
        db.flush()
        for item in data["interview-proposal-evidence.json"]:
            db.add(InterviewProposalEvidence(proposal_id=item["proposal_id"], analysis_id=item["analysis_id"], segments_sha256=item["segments_sha256"], selected_fact_indices=item["selected_fact_indices"], segment_ids=item["segment_ids"], created_at=_parse_datetime(item["created_at"])))
        for item in data["interview-proposal-evidence-sources.json"]:
            db.add(InterviewProposalEvidenceSource(id=item["id"], proposal_id=item["proposal_id"], analysis_id=item["analysis_id"], segments_sha256=item["segments_sha256"], selected_fact_indices=item["selected_fact_indices"], segment_ids=item["segment_ids"], created_at=_parse_datetime(item["created_at"])))
        for item in data["cross-interview-conflict-scans.json"]:
            db.add(CrossInterviewConflictScan(id=item["id"], session_id=item["session_id"], evidence_sha256=item["evidence_sha256"], source_count=item["source_count"], fact_count=item["fact_count"], provider=item["provider"], model=item["model"], prompt_version=item["prompt_version"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        for item in data["cross-interview-conflicts.json"]:
            db.add(CrossInterviewConflict(id=item["id"], session_id=item["session_id"], evidence_sha256=item["evidence_sha256"], fingerprint=item["fingerprint"], summary=item["summary"], question=item["question"], reason=item["reason"], fact_references=item["fact_references"], segment_ids=item["segment_ids"], status=item["status"], provider=item["provider"], model=item["model"], prompt_version=item["prompt_version"], created_by_user_id=user.id, resolved_by_user_id=user.id if item["resolved"] else None, created_at=_parse_datetime(item["created_at"]), resolved_at=_parse_datetime(item["resolved_at"])))
        for item in data["n8n-import-artifacts.json"]:
            db.add(N8nImportArtifact(id=item["id"], project_id=project.id, revision_id=item["revision_id"], source_minor=item["source_minor"], workflow_name=item["workflow_name"], source_sha256=item["source_sha256"], source_workflow=item["source_workflow"], diagnostics=item["diagnostics"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        for item in data["agent-runs.json"]:
            db.add(AgentRun(id=item["id"], project_id=project.id, revision_id=item["revision_id"], runtime=item["runtime"], status=item["status"], contract_version=item["contract_version"], idempotency_key=item["idempotency_key"], max_steps=item["max_steps"], max_tool_calls=item["max_tool_calls"], timeout_seconds=item["timeout_seconds"], max_cost_microunits=item["max_cost_microunits"], steps_used=item["steps_used"], tool_calls_used=item["tool_calls_used"], cost_microunits=item["cost_microunits"], created_by_user_id=user.id, started_at=_parse_datetime(item["started_at"]), ended_at=_parse_datetime(item["ended_at"]), created_at=_parse_datetime(item["created_at"]), updated_at=_parse_datetime(item["updated_at"])))
        db.flush()
        for item in data["agent-run-events.json"]:
            db.add(AgentRunEvent(id=item["id"], run_id=item["run_id"], sequence=item["sequence"], event_type=item["event_type"], external_event_id=item.get("external_event_id"), actor_type=item["actor_type"], reason_code=item["reason_code"], metrics=item["metrics"], created_by_user_id=user.id if item["actor_type"] == "user" else None, created_at=_parse_datetime(item["created_at"])))
        for item in data["agent-evaluation-runs.json"]:
            db.add(AgentEvaluationRun(id=item["id"], project_id=project.id, revision_id=item["revision_id"], runtime=item["runtime"], suite_version=item["suite_version"], status=item["status"], model_fingerprint=item["model_fingerprint"], results=item["results"], passed_count=item["passed_count"], total_count=item["total_count"], cost_microunits=item["cost_microunits"], duration_ms=item["duration_ms"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        db.flush()
        for item in data["agent-baseline-decisions.json"]:
            db.add(AgentBaselineDecision(id=item["id"], project_id=project.id, evaluation_run_id=item["evaluation_run_id"], runtime=item["runtime"], action=item["action"], reason_code=item["reason_code"], created_by_user_id=user.id, created_at=_parse_datetime(item["created_at"])))
        for item in data["agent-incidents.json"]:
            db.add(AgentIncident(id=item["id"], project_id=project.id, run_id=item["run_id"], status=item["status"], category=item["category"], reason_code=item["reason_code"], resolution_code=item["resolution_code"], replay_run_id=item["replay_run_id"], resolved_by_user_id=user.id if item["resolved_at"] else None, resolved_at=_parse_datetime(item["resolved_at"]), created_at=_parse_datetime(item["created_at"]), updated_at=_parse_datetime(item["updated_at"])))
        db.add(ProjectArchiveRestore(archive_sha256=validated.archive_sha256, source_project_id=project_data["id"], restored_project_id=project.id, restored_by_user_id=user.id))
        db.commit()
        db.refresh(project)
        return project, False
    except Exception:
        db.rollback()
        raise
