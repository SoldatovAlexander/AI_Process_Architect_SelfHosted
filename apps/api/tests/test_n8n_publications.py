import json
from copy import deepcopy
from pathlib import Path

from test_api import authorization, request

from process_architect_api.services.n8n_publications import N8nPublicationError
from process_architect_api.services.runtime_connections import RuntimeVerification
from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import BillingUsageReservation
from process_architect_api.deployment_profiles import clear_deployment_profile_cache


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads((ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(encoding="utf-8"))


def setup_project_and_profile(monkeypatch):
    tokens = request("POST", "/api/v1/auth/register", json={"email": "publication-owner@example.com", "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    workspace_id = request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]
    project = request("POST", "/api/v1/projects", headers=headers, json={"workspace_id": workspace_id, "name": "Lead intake", "process_ir": deepcopy(LEAD)}).json()
    profile = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": "Production n8n", "kind": "n8n", "endpoint_url": "https://n8n.example.com", "secret_ref": "env:N8N_PUBLICATION_KEY", "n8n_minor": "2.32"}).json()

    async def verified(_profile):
        return RuntimeVerification("connection_verified", "2.32.7")

    monkeypatch.setattr("process_architect_api.runtime_connection_routes.verify_runtime_connection", verified)
    profile = request("POST", f"/api/v1/runtime-connections/{profile['id']}/verify", headers=headers).json()["profile"]
    return headers, project, profile


def test_previews_publishes_idempotently_and_deletes_remote_draft(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, project, profile = setup_project_and_profile(monkeypatch)
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    preview = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications/preview", headers=headers, json=body)
    assert preview.status_code == 200
    assert preview.json()["active"] is False
    assert preview.json()["target_minor"] == "2.32"
    assert preview.json()["node_count"] == len(LEAD["steps"])

    remote_calls = []

    async def publish(_profile, prepared):
        remote_calls.append(prepared.workflow_sha256)
        return "remote-workflow-42"

    async def delete(_profile, remote_id):
        assert remote_id == "remote-workflow-42"
        remote_calls.append("deleted")

    monkeypatch.setattr("process_architect_api.n8n_publication_routes.publish_inactive_workflow", publish)
    monkeypatch.setattr("process_architect_api.n8n_publication_routes.delete_inactive_workflow", delete)
    publish_body = {**body, "idempotency_key": "publish-request-001", "expected_workflow_sha256": preview.json()["workflow_sha256"]}
    published = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers, json=publish_body)
    assert published.status_code == 201
    assert published.json()["status"] == "published"
    assert published.json()["remote_workflow_id"] == "remote-workflow-42"

    repeated = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers, json=publish_body)
    same_content = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers, json={**publish_body, "idempotency_key": "publish-request-002"})
    assert repeated.json()["id"] == same_content.json()["id"] == published.json()["id"]
    assert len(remote_calls) == 1
    assert request("GET", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers).json()[0]["status"] == "published"

    deleted = request("DELETE", f"/api/v1/n8n-publications/{published.json()['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert remote_calls == [preview.json()["workflow_sha256"], "deleted"]
    with get_session_factory()() as db:
        reservations = db.query(BillingUsageReservation).all()
        assert len(reservations) == 1
        assert reservations[0].metric == "runtime_publish"
        assert reservations[0].status == "consumed"


def test_publication_requires_current_preview_and_verified_matching_profile(monkeypatch):
    headers, project, profile = setup_project_and_profile(monkeypatch)
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    stale = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers, json={**body, "idempotency_key": "publish-stale-001", "expected_workflow_sha256": "0" * 64})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "publication_preview_stale"

    request("POST", f"/api/v1/runtime-connections/{profile['id']}/disable", headers=headers)
    unverified = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications/preview", headers=headers, json=body)
    assert unverified.status_code == 409
    assert unverified.json()["detail"]["code"] == "n8n_profile_not_verified"


def test_failed_publication_with_remote_id_can_be_cleaned_up(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, project, profile = setup_project_and_profile(monkeypatch)
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    preview = request("POST", f"/api/v1/projects/{project['id']}/n8n-publications/preview", headers=headers, json=body).json()

    async def unsafe_publish(_profile, _prepared):
        raise N8nPublicationError("remote_workflow_not_inactive", remote_workflow_id="unsafe-remote-1")

    deleted_ids = []

    async def delete(_profile, remote_id):
        deleted_ids.append(remote_id)

    monkeypatch.setattr("process_architect_api.n8n_publication_routes.publish_inactive_workflow", unsafe_publish)
    monkeypatch.setattr("process_architect_api.n8n_publication_routes.delete_inactive_workflow", delete)
    failed = request(
        "POST",
        f"/api/v1/projects/{project['id']}/n8n-publications",
        headers=headers,
        json={**body, "idempotency_key": "unsafe-publication-001", "expected_workflow_sha256": preview["workflow_sha256"]},
    )
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "remote_workflow_not_inactive"

    publication = request("GET", f"/api/v1/projects/{project['id']}/n8n-publications", headers=headers).json()[0]
    assert publication["status"] == "failed"
    assert publication["remote_workflow_id"] == "unsafe-remote-1"

    deleted = request("DELETE", f"/api/v1/n8n-publications/{publication['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert deleted_ids == ["unsafe-remote-1"]
    with get_session_factory()() as db:
        reservation = db.query(BillingUsageReservation).one()
        assert reservation.metric == "runtime_publish"
        assert reservation.status == "released"
