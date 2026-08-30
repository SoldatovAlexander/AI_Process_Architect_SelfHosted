from copy import deepcopy

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import BillingUsageReservation
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from process_architect_api.services.agent_package_deliveries import AgentPackageDeliveryError
from process_architect_api.services.runtime_connections import RuntimeVerification
from test_agent_exports import configured_agent_process
from test_api import authorization, request


def setup_project_and_profile(monkeypatch, runtime="openclaw"):
    tokens = request("POST", "/api/v1/auth/register", json={"email": f"agent-delivery-{runtime}@example.com", "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    workspace_id = request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]
    process_ir = deepcopy(configured_agent_process())
    for question in process_ir["openQuestions"]:
        question["blocksAutomationReady"] = False
    project = request("POST", "/api/v1/projects", headers=headers, json={"workspace_id": workspace_id, "name": "Ready agent", "target_mode": "agent", "process_ir": process_ir}).json()
    profile = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": runtime.title(), "kind": runtime, "endpoint_url": f"https://{runtime}.example.com/architect", "secret_ref": f"env:{runtime.upper()}_DELIVERY_KEY"}).json()

    async def verified(_profile):
        return RuntimeVerification("connection_verified", "1.4.0")

    monkeypatch.setattr("process_architect_api.runtime_connection_routes.verify_runtime_connection", verified)
    profile = request("POST", f"/api/v1/runtime-connections/{profile['id']}/verify", headers=headers).json()["profile"]
    return headers, project, profile


def test_previews_stores_idempotently_and_deletes_agent_package(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, project, profile = setup_project_and_profile(monkeypatch)
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    preview = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries/preview", headers=headers, json=body)
    assert preview.status_code == 200
    assert preview.json()["runtime"] == "openclaw"
    assert preview.json()["ready"] is True
    assert preview.json()["active"] is False
    assert preview.json()["file_count"] > 10

    calls = []

    async def store(_profile, prepared, revision_id, idempotency_key):
        calls.append((prepared.package_sha256, revision_id, idempotency_key))
        return "remote-package-42"

    async def delete(_profile, remote_id):
        calls.append(("deleted", remote_id))

    monkeypatch.setattr("process_architect_api.agent_package_delivery_routes.store_inactive_agent_package", store)
    monkeypatch.setattr("process_architect_api.agent_package_delivery_routes.delete_stored_agent_package", delete)
    delivery_body = {**body, "idempotency_key": "delivery-request-001", "expected_package_sha256": preview.json()["package_sha256"]}
    stored = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers, json=delivery_body)
    assert stored.status_code == 201
    assert stored.json()["status"] == "stored"
    assert stored.json()["remote_package_id"] == "remote-package-42"

    repeated = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers, json=delivery_body)
    same_content = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers, json={**delivery_body, "idempotency_key": "delivery-request-002"})
    assert repeated.json()["id"] == same_content.json()["id"] == stored.json()["id"]
    assert len(calls) == 1

    deleted = request("DELETE", f"/api/v1/agent-package-deliveries/{stored.json()['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert calls[-1] == ("deleted", "remote-package-42")
    with get_session_factory()() as db:
        reservation = db.query(BillingUsageReservation).one()
        assert reservation.metric == "runtime_publish"
        assert reservation.status == "consumed"


def test_delivery_rejects_stale_preview_and_non_agent_project(monkeypatch):
    headers, project, profile = setup_project_and_profile(monkeypatch, "hermes")
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    stale = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers, json={**body, "idempotency_key": "stale-delivery-key", "expected_package_sha256": "0" * 64})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "agent_delivery_preview_stale"

    request("PATCH", f"/api/v1/projects/{project['id']}/target-mode", headers=headers, json={"target_mode": "process"})
    blocked = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries/preview", headers=headers, json=body)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "agent_mode_required"


def test_failed_delivery_with_remote_id_can_be_removed(monkeypatch):
    headers, project, profile = setup_project_and_profile(monkeypatch)
    body = {"profile_id": profile["id"], "revision_id": project["current_revision_id"]}
    preview = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries/preview", headers=headers, json=body).json()

    async def unsafe_store(*_args):
        raise AgentPackageDeliveryError("remote_agent_package_not_inactive", "unsafe-package-1")

    removed = []

    async def delete(_profile, remote_id):
        removed.append(remote_id)

    monkeypatch.setattr("process_architect_api.agent_package_delivery_routes.store_inactive_agent_package", unsafe_store)
    monkeypatch.setattr("process_architect_api.agent_package_delivery_routes.delete_stored_agent_package", delete)
    failed = request("POST", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers, json={**body, "idempotency_key": "unsafe-delivery-001", "expected_package_sha256": preview["package_sha256"]})
    assert failed.status_code == 502
    delivery = request("GET", f"/api/v1/projects/{project['id']}/agent-package-deliveries", headers=headers).json()[0]
    assert delivery["status"] == "failed"
    assert delivery["remote_package_id"] == "unsafe-package-1"
    assert request("DELETE", f"/api/v1/agent-package-deliveries/{delivery['id']}", headers=headers).status_code == 200
    assert removed == ["unsafe-package-1"]
