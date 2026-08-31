import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from process_architect_api.config import get_settings
from process_architect_api.database import get_engine, get_session_factory, init_database
from process_architect_api.deepseek import DeepSeekAnalystTurn, DeepSeekClient
from process_architect_api.models import InterviewAnalysisResult
from test_analyst_api import create_proposal, create_session
from test_api import authorization, request


def _documents(content: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _rebuild(content: bytes, replacements: dict[str, object]) -> bytes:
    files = _documents(content)
    manifest = json.loads(files["manifest.json"])
    for name, value in replacements.items():
        files[name] = (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode("utf-8")
        manifest["files"][name] = {
            "sha256": hashlib.sha256(files[name]).hexdigest(),
            "bytes": len(files[name]),
        }
    files["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _as_legacy_v1(content: bytes) -> bytes:
    files = _documents(content)
    for name in ("agent-runs.json", "agent-run-events.json", "agent-evaluation-runs.json", "agent-baseline-decisions.json", "agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        files.pop(name)
    manifest = json.loads(files["manifest.json"])
    manifest["formatVersion"] = "1.0"
    for name in ("agent-runs.json", "agent-run-events.json", "agent-evaluation-runs.json", "agent-baseline-decisions.json", "agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        manifest["files"].pop(name)
    for name in ("agentRuns", "agentRunEvents", "agentEvaluations", "agentBaselineDecisions", "agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"):
        manifest["counts"].pop(name)
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _as_legacy_v1_1(content: bytes) -> bytes:
    files = _documents(content)
    for name in ("agent-evaluation-runs.json", "agent-baseline-decisions.json", "agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        files.pop(name)
    manifest = json.loads(files["manifest.json"])
    manifest["formatVersion"] = "1.1"
    for name in ("agent-evaluation-runs.json", "agent-baseline-decisions.json", "agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        manifest["files"].pop(name)
    for name in ("agentEvaluations", "agentBaselineDecisions", "agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"):
        manifest["counts"].pop(name)
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _as_legacy_v1_2(content: bytes) -> bytes:
    files = _documents(content)
    for name in ("agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        files.pop(name)
    manifest = json.loads(files["manifest.json"])
    manifest["formatVersion"] = "1.2"
    for name in ("agent-incidents.json", "interview-documents.json", "interview-segments.json", "interview-analyses.json", "interview-proposal-evidence.json", "interview-proposal-evidence-sources.json", "cross-interview-conflict-scans.json", "cross-interview-conflicts.json"):
        manifest["files"].pop(name)
    for name in ("agentIncidents", "interviewDocuments", "interviewSegments", "interviewAnalyses", "interviewProposalEvidence", "interviewProposalEvidenceSources", "crossInterviewConflictScans", "crossInterviewConflicts"):
        manifest["counts"].pop(name)
    files["manifest.json"] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _reset_database(database_path) -> None:
    get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    database_path.unlink()
    get_settings.cache_clear()
    init_database()


def test_exports_validates_and_restores_complete_project_history(tmp_path, monkeypatch):
    headers, project, session = create_session()
    proposal = create_proposal(headers, project, session)
    accepted = request(
        "POST",
        f"/api/v1/analyst/proposals/{proposal['id']}/accept",
        headers=headers,
        json={"base_revision_id": project["current_revision_id"]},
    )
    assert accepted.status_code == 200
    request("PATCH", f"/api/v1/projects/{project['id']}/target-mode", headers=headers, json={"target_mode": "agent"})
    run = request("POST", f"/api/v1/projects/{project['id']}/agent-runs", headers=headers, json={"runtime": "openclaw", "idempotency_key": "archive-run-001"})
    assert run.status_code == 201
    request("POST", f"/api/v1/agent-runs/{run.json()['id']}/transitions", headers=headers, json={"action": "start"})
    request("POST", f"/api/v1/agent-runs/{run.json()['id']}/transitions", headers=headers, json={"action": "fail", "reason_code": "integration_failed"})
    gate = request("GET", f"/api/v1/projects/{project['id']}/agent-pilot-gate?runtime=openclaw", headers=headers).json()
    evaluation = request("POST", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=headers, json={"runtime": "openclaw", "results": [{"scenario_id": item, "passed": True} for item in gate["required_scenarios"]]})
    assert evaluation.status_code == 201
    baseline = request("POST", f"/api/v1/projects/{project['id']}/agent-baselines", headers=headers, json={"evaluation_run_id": evaluation.json()["id"]})
    assert baseline.status_code == 201
    source_url = "https://docs.google.com/document/d/archive-source/edit"
    transcript = request("POST", f"/api/v1/analyst/sessions/{session['id']}/interviews", headers=headers, json={"title": "Customer interview", "source_format": "google_docs", "source_url": source_url, "language": "en", "content": "Customer: Leads arrive from the website.\nAnalyst: Who reviews them?"})
    assert transcript.status_code == 201
    reviewed_transcript = request("POST", f"/api/v1/analyst/interviews/{transcript.json()['id']}/review", headers=headers, json={"expected_segments_sha256": transcript.json()["segments_sha256"]})
    assert reviewed_transcript.status_code == 200
    segment_id = reviewed_transcript.json()["segments"][0]["id"]
    async def fake_analysis(self, messages):
        return InterviewAnalysisResult.model_validate({"confirmed_facts": [{"statement": "Leads arrive from the website.", "segment_ids": [segment_id]}]})
    monkeypatch.setattr(DeepSeekClient, "analyze_interview", fake_analysis)
    analysis = request("POST", f"/api/v1/analyst/interviews/{transcript.json()['id']}/analysis", headers=headers)
    assert analysis.status_code == 200
    async def fake_interview_proposal(self, messages):
        return DeepSeekAnalystTurn(message="Prepared from confirmed interview evidence.", summary="Recorded the confirmed lead source.", patch=[{"op": "replace", "path": "/process/description", "value": "Leads arrive from the website."}])
    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_interview_proposal)
    interview_proposal = request("POST", f"/api/v1/analyst/interview-analyses/{analysis.json()['id']}/proposal", headers=headers, json={"base_revision_id": accepted.json()["accepted_revision_id"], "selected_fact_indices": [0]})
    assert interview_proposal.status_code == 201

    exported = request(
        "GET", f"/api/v1/project-archives/projects/{project['id']}", headers=headers
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"
    files = _documents(exported.content)
    assert set(files) == {
        "manifest.json",
        "project.json",
        "revisions.json",
        "analyst-sessions.json",
        "analyst-messages.json",
        "proposed-patches.json",
        "n8n-import-artifacts.json",
        "agent-runs.json",
        "agent-run-events.json",
        "agent-evaluation-runs.json",
        "agent-baseline-decisions.json",
        "agent-incidents.json",
        "interview-documents.json",
        "interview-segments.json",
            "interview-analyses.json",
            "interview-proposal-evidence.json",
            "interview-proposal-evidence-sources.json",
            "cross-interview-conflict-scans.json",
            "cross-interview-conflicts.json",
        }
    manifest = json.loads(files["manifest.json"])
    assert manifest["formatVersion"] == "1.10"
    assert manifest["secretsIncluded"] is False
    assert json.loads(files["interview-documents.json"])[0]["source_url"] == source_url
    assert manifest["counts"] == {
        "revisions": 2,
        "sessions": 1,
        "messages": 2,
        "interviewDocuments": 1,
        "interviewSegments": 2,
        "interviewAnalyses": 1,
            "interviewProposalEvidence": 1,
            "interviewProposalEvidenceSources": 0,
            "crossInterviewConflictScans": 0,
            "crossInterviewConflicts": 0,
        "proposals": 2,
        "n8nArtifacts": 0,
        "agentRuns": 1,
        "agentRunEvents": 3,
        "agentEvaluations": 1,
        "agentBaselineDecisions": 1,
        "agentIncidents": 1,
    }
    assert b"project-owner@example.com" not in exported.content
    assert b"correct-horse-battery-staple" not in exported.content

    checked = request(
        "POST",
        "/api/v1/project-archives/validate",
        headers=headers,
        content=exported.content,
        params={"unused": "ignored"},
    )
    assert checked.status_code == 200
    assert checked.json()["counts"] == manifest["counts"]
    legacy_checked = request("POST", "/api/v1/project-archives/validate", headers=headers, content=_as_legacy_v1(exported.content))
    assert legacy_checked.status_code == 200
    assert legacy_checked.json()["format_version"] == "1.0"
    legacy_v1_1_checked = request("POST", "/api/v1/project-archives/validate", headers=headers, content=_as_legacy_v1_1(exported.content))
    assert legacy_v1_1_checked.status_code == 200
    assert legacy_v1_1_checked.json()["format_version"] == "1.1"
    legacy_v1_2_checked = request("POST", "/api/v1/project-archives/validate", headers=headers, content=_as_legacy_v1_2(exported.content))
    assert legacy_v1_2_checked.status_code == 200
    assert legacy_v1_2_checked.json()["format_version"] == "1.2"

    database_path = tmp_path / "test.db"
    _reset_database(database_path)
    tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "restore-owner@example.com", "password": "correct-horse-battery-staple"},
    ).json()
    restore_headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=restore_headers).json()
    workspace_id = user["workspaces"][0]["workspace_id"]

    restored = request(
        "POST",
        "/api/v1/project-archives/restore",
        headers=restore_headers,
        params={"workspaceId": workspace_id},
        content=exported.content,
    )
    assert restored.status_code == 200
    assert restored.json()["already_restored"] is False
    assert restored.json()["project"]["id"] == project["id"]
    assert restored.json()["project"]["current_revision"]["version_number"] == 2

    revisions = request(
        "GET", f"/api/v1/projects/{project['id']}/revisions", headers=restore_headers
    ).json()
    restored_session = request(
        "GET", f"/api/v1/analyst/sessions/{session['id']}", headers=restore_headers
    ).json()
    assert [item["id"] for item in revisions] == [
        item["id"] for item in json.loads(files["revisions.json"])
    ]
    assert len(restored_session["messages"]) == 2
    assert restored_session["interview_documents"][0]["title"] == "Customer interview"
    assert restored_session["interview_documents"][0]["source_url"] == source_url
    assert restored_session["interview_documents"][0]["segment_count"] == 2
    assert restored_session["interview_documents"][0]["status"] == "reviewed"
    assert restored_session["interview_documents"][0]["reviewed_at"] is not None
    assert restored_session["interview_documents"][0]["latest_analysis"]["id"] == analysis.json()["id"]
    assert restored_session["interview_documents"][0]["latest_analysis"]["stale"] is False
    assert restored_session["interview_documents"][0]["latest_analysis"]["result"]["confirmed_facts"][0]["segment_ids"] == [segment_id]
    assert {item["status"] for item in restored_session["proposed_patches"]} == {"accepted", "pending"}
    evidence = json.loads(files["interview-proposal-evidence.json"])[0]
    assert evidence["proposal_id"] == interview_proposal.json()["proposal"]["id"]
    assert evidence["analysis_id"] == analysis.json()["id"]
    restored_runs = request("GET", f"/api/v1/projects/{project['id']}/agent-runs", headers=restore_headers).json()
    assert len(restored_runs) == 1
    assert restored_runs[0]["id"] == run.json()["id"]
    assert restored_runs[0]["events"][0]["event_type"] == "run_created"
    restored_incidents = request("GET", f"/api/v1/projects/{project['id']}/agent-incidents", headers=restore_headers).json()
    assert restored_incidents[0]["run_id"] == run.json()["id"]
    assert restored_incidents[0]["reason_code"] == "integration_failed"
    restored_evaluations = request("GET", f"/api/v1/projects/{project['id']}/agent-evaluations", headers=restore_headers).json()
    restored_gate = request("GET", f"/api/v1/projects/{project['id']}/agent-pilot-gate?runtime=openclaw", headers=restore_headers).json()
    assert restored_evaluations[0]["id"] == evaluation.json()["id"]
    assert restored_gate["baseline"]["evaluation_run_id"] == evaluation.json()["id"]

    duplicate = request(
        "POST",
        "/api/v1/project-archives/restore",
        headers=restore_headers,
        params={"workspaceId": workspace_id},
        content=exported.content,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["already_restored"] is True
    projects = request(
        "GET", "/api/v1/projects", headers=restore_headers, params={"workspace_id": workspace_id}
    ).json()
    assert len(projects) == 1

    other_tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "other-restore-owner@example.com", "password": "correct-horse-battery-staple"},
    ).json()
    other_headers = authorization(other_tokens)
    other_user = request("GET", "/api/v1/auth/me", headers=other_headers).json()
    private_validation = request(
        "POST", "/api/v1/project-archives/validate", headers=other_headers, content=exported.content
    )
    assert private_validation.json()["already_restored_project_id"] is None
    cross_workspace = request(
        "POST",
        "/api/v1/project-archives/restore",
        headers=other_headers,
        params={"workspaceId": other_user["workspaces"][0]["workspace_id"]},
        content=exported.content,
    )
    assert cross_workspace.status_code == 409


def test_rejects_corruption_and_secret_like_values_before_restore():
    headers, project, _ = create_session()
    content = request(
        "GET", f"/api/v1/project-archives/projects/{project['id']}", headers=headers
    ).content
    files = _documents(content)
    corrupted = files["project.json"].replace(b"Lead automation", b"Lost automation")
    broken_files = dict(files)
    broken_files["project.json"] = corrupted
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in broken_files.items():
            archive.writestr(name, value)
    rejected = request(
        "POST", "/api/v1/project-archives/validate", headers=headers, content=output.getvalue()
    )
    assert rejected.status_code == 422
    assert "Checksum" in rejected.json()["detail"]["message"]

    project_document = json.loads(files["project.json"])
    project_document["api_token"] = "must-not-be-restored"
    secret_archive = _rebuild(content, {"project.json": project_document})
    secret_rejected = request(
        "POST", "/api/v1/project-archives/validate", headers=headers, content=secret_archive
    )
    assert secret_rejected.status_code == 422
    assert "secret-like" in secret_rejected.json()["detail"]["message"]
