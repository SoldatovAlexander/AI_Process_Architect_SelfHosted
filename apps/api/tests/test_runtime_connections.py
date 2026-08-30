from test_api import authorization, request

from process_architect_api.config import get_settings
from process_architect_api.services.runtime_connections import RuntimeVerification, RuntimeVerificationError


def register(email: str) -> dict:
    response = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"})
    assert response.status_code == 201
    return response.json()


def workspace(headers: dict) -> str:
    return request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]


def test_runtime_profiles_are_workspace_scoped_and_secret_reference_only():
    headers = authorization(register("runtime-owner@example.com"))
    workspace_id = workspace(headers)
    payload = {"name": "Development n8n", "kind": "n8n", "endpoint_url": "http://localhost:5678/", "secret_ref": "env:N8N_DEVELOPMENT_API_KEY", "n8n_minor": "2.32"}
    created = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json=payload)
    assert created.status_code == 201
    assert created.json()["endpoint_url"] == "http://localhost:5678"
    assert created.json()["status"] == "draft"
    assert request("GET", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers).json() == [created.json()]

    duplicate = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json=payload)
    assert duplicate.status_code == 409
    foreign_headers = authorization(register("runtime-foreign@example.com"))
    assert request("GET", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=foreign_headers).status_code == 404


def test_runtime_profile_rejects_embedded_secrets_and_insecure_remote_endpoints():
    headers = authorization(register("runtime-security@example.com"))
    workspace_id = workspace(headers)
    base = {"name": "Agent", "kind": "openclaw", "endpoint_url": "https://runtime.example.com/runs", "secret_ref": "env:OPENCLAW_RUNTIME_TOKEN"}
    assert request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={**base, "token": "plaintext"}).status_code == 422
    assert request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={**base, "endpoint_url": "https://user:pass@runtime.example.com"}).status_code == 422
    insecure = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={**base, "endpoint_url": "http://runtime.example.com"})
    assert insecure.status_code == 422
    assert insecure.json()["detail"]["code"] == "insecure_runtime_endpoint"


def test_e2e_runtime_hosts_require_an_explicit_server_flag(monkeypatch):
    headers = authorization(register("runtime-e2e@example.com"))
    workspace_id = workspace(headers)
    payload = {"name": "Fake n8n", "kind": "n8n", "endpoint_url": "http://fake-n8n:8002", "secret_ref": "env:N8N_E2E_API_KEY", "n8n_minor": "2.32"}
    assert request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json=payload).status_code == 422

    monkeypatch.setenv("E2E_RUNTIME_ENABLED", "true")
    get_settings.cache_clear()
    created = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json=payload)
    assert created.status_code == 201


def test_runtime_profile_requires_matching_n8n_version_contract():
    headers = authorization(register("runtime-version@example.com"))
    workspace_id = workspace(headers)
    missing = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": "n8n", "kind": "n8n", "endpoint_url": "https://n8n.example.com", "secret_ref": "env:N8N_API_KEY"})
    extra = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": "Hermes", "kind": "hermes", "endpoint_url": "https://hermes.example.com", "secret_ref": "env:HERMES_RUNTIME_TOKEN", "n8n_minor": "2.32"})
    assert missing.status_code == extra.status_code == 422


def test_runtime_profile_verification_records_bounded_result(monkeypatch):
    headers = authorization(register("runtime-verify@example.com"))
    workspace_id = workspace(headers)
    created = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": "Development n8n", "kind": "n8n", "endpoint_url": "http://localhost:5678", "secret_ref": "env:N8N_TEST_API_KEY", "n8n_minor": "2.32"}).json()

    async def verified(profile):
        assert profile.secret_ref == "env:N8N_TEST_API_KEY"
        return RuntimeVerification("connection_verified", "2.32.4")

    monkeypatch.setattr("process_architect_api.runtime_connection_routes.verify_runtime_connection", verified)
    response = request("POST", f"/api/v1/runtime-connections/{created['id']}/verify", headers=headers)
    assert response.status_code == 200
    assert response.json()["result_code"] == "connection_verified"
    assert response.json()["profile"]["status"] == "verified"
    assert response.json()["profile"]["detected_version"] == "2.32.4"
    assert response.json()["profile"]["last_checked_at"]
    assert "do-not-log-this" not in response.text


def test_runtime_profile_failed_verification_can_be_disabled(monkeypatch):
    headers = authorization(register("runtime-failed@example.com"))
    workspace_id = workspace(headers)
    created = request("POST", f"/api/v1/workspaces/{workspace_id}/runtime-connections", headers=headers, json={"name": "Hermes", "kind": "hermes", "endpoint_url": "https://hermes.example.com/health", "secret_ref": "env:HERMES_TEST_TOKEN"}).json()

    async def failed(_profile):
        raise RuntimeVerificationError("authentication_failed")

    monkeypatch.setattr("process_architect_api.runtime_connection_routes.verify_runtime_connection", failed)
    response = request("POST", f"/api/v1/runtime-connections/{created['id']}/verify", headers=headers)
    assert response.status_code == 200
    assert response.json()["profile"]["status"] == "failed"
    assert response.json()["result_code"] == "authentication_failed"

    disabled = request("POST", f"/api/v1/runtime-connections/{created['id']}/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
