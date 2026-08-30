import asyncio

import httpx
import pytest

from process_architect_api.services.n8n_publications import N8nPublicationError, PreparedN8nPublication, delete_inactive_workflow, publish_inactive_workflow


class Profile:
    endpoint_url = "https://n8n.example.com"
    secret_ref = "env:N8N_PUBLICATION_TEST_KEY"
    kind = "n8n"
    n8n_minor = "2.32"


PREPARED = PreparedN8nPublication(
    payload={"name": "Lead intake", "nodes": [], "connections": {}, "settings": {"executionOrder": "v1"}},
    workflow_sha256="a" * 64,
    node_count=0,
    connection_count=0,
    source_mode="generated",
)


def test_client_creates_and_confirms_inactive_workflow(monkeypatch):
    monkeypatch.setenv("N8N_PUBLICATION_TEST_KEY", "secret")
    monkeypatch.setattr("process_architect_api.services.n8n_publications.validate_egress_target", lambda _url: None)
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers["X-N8N-API-KEY"] == "secret"
        if request.method == "GET" and request.url.query:
            return httpx.Response(200, request=request, headers={"X-N8N-Version": "2.32.7"}, json={"data": []})
        if request.method == "POST":
            assert "active" not in request.read().decode()
            return httpx.Response(201, request=request, json={"id": "workflow-1", "active": False})
        if request.method == "GET":
            return httpx.Response(200, request=request, json={"id": "workflow-1", "active": False})
        return httpx.Response(200, request=request, json={})

    transport = httpx.MockTransport(handler)
    assert asyncio.run(publish_inactive_workflow(Profile(), PREPARED, transport=transport)) == "workflow-1"
    asyncio.run(delete_inactive_workflow(Profile(), "workflow-1", transport=transport))
    assert calls == [("GET", "/api/v1/workflows"), ("POST", "/api/v1/workflows"), ("GET", "/api/v1/workflows/workflow-1"), ("DELETE", "/api/v1/workflows/workflow-1")]


def test_client_removes_workflow_if_n8n_reports_it_active(monkeypatch):
    monkeypatch.setenv("N8N_PUBLICATION_TEST_KEY", "secret")
    monkeypatch.setattr("process_architect_api.services.n8n_publications.validate_egress_target", lambda _url: None)
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.query:
            return httpx.Response(200, request=request, headers={"X-N8N-Version": "2.32.7"}, json={"data": []})
        if request.method == "POST" and request.url.path.endswith("/workflows"):
            return httpx.Response(201, request=request, json={"id": "unsafe-1"})
        if request.method == "GET":
            return httpx.Response(200, request=request, json={"id": "unsafe-1", "active": True})
        return httpx.Response(200, request=request, json={})

    with pytest.raises(N8nPublicationError, match="remote_workflow_not_inactive") as captured:
        asyncio.run(publish_inactive_workflow(Profile(), PREPARED, transport=httpx.MockTransport(handler)))
    assert captured.value.remote_workflow_id == "unsafe-1"
    assert calls[-2:] == [("POST", "/api/v1/workflows/unsafe-1/deactivate"), ("DELETE", "/api/v1/workflows/unsafe-1")]
