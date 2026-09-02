import asyncio

import httpx
import pytest

from process_architect_api.services.agent_package_deliveries import AgentPackageDeliveryError, PreparedAgentPackageDelivery, delete_stored_agent_package, store_inactive_agent_package


class Profile:
    endpoint_url = "https://openclaw.example.com/architect"
    secret_ref = "env:AGENT_PACKAGE_TEST_KEY"
    kind = "openclaw"
    n8n_minor = None


PREPARED = PreparedAgentPackageDelivery(
    package=b"PK\x03\x04test-package",
    package_sha256="a" * 64,
    package_size=16,
    file_count=4,
    process_name="Lead intake",
    readiness_score=100,
    blocker_count=0,
    ready=True,
    runtime="openclaw",
)


def _setup(monkeypatch):
    monkeypatch.setenv("AGENT_PACKAGE_TEST_KEY", "secret")
    monkeypatch.setattr("process_architect_api.services.agent_package_deliveries.validate_egress_target", lambda _url: None)
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)


def test_client_stores_inactive_package_and_deletes_it(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer secret"
        if request.method == "GET":
            return httpx.Response(200, request=request, json={"runtime": "openclaw", "version": "1.4.0"})
        if request.method == "POST":
            assert request.headers["X-Activation-Policy"] == "manual"
            assert request.headers["X-Package-SHA256"] == PREPARED.package_sha256
            assert request.content == PREPARED.package
            return httpx.Response(201, request=request, json={"id": "package-1", "status": "stored", "active": False, "sha256": PREPARED.package_sha256})
        return httpx.Response(204, request=request)

    transport = httpx.MockTransport(handler)
    remote_id = asyncio.run(store_inactive_agent_package(Profile(), PREPARED, "revision-1", "delivery-key-1", transport=transport))
    assert remote_id == "package-1"
    asyncio.run(delete_stored_agent_package(Profile(), remote_id, transport=transport))
    assert calls == [("GET", "/architect"), ("POST", "/architect/packages"), ("DELETE", "/architect/packages/package-1")]


def test_client_sends_the_certified_openclaw_version_when_present(monkeypatch):
    _setup(monkeypatch)
    prepared = PreparedAgentPackageDelivery(**{**PREPARED.__dict__, "runtime_version": "2026.8.2"})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, request=request, json={"runtime": "openclaw", "runtimeVersion": "2026.8.2"})
        assert request.headers["X-Agent-Runtime-Version"] == "2026.8.2"
        return httpx.Response(201, request=request, json={"id": "package-versioned", "status": "stored", "active": False})

    remote_id = asyncio.run(store_inactive_agent_package(Profile(), prepared, "revision-1", "delivery-key-versioned", transport=httpx.MockTransport(handler)))
    assert remote_id == "package-versioned"


def test_client_removes_package_if_runtime_does_not_confirm_inactive_storage(monkeypatch):
    _setup(monkeypatch)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, request=request, json={"runtime": "openclaw"})
        if request.method == "POST":
            return httpx.Response(201, request=request, json={"id": "unsafe-package", "status": "activated", "active": True})
        return httpx.Response(204, request=request)

    with pytest.raises(AgentPackageDeliveryError, match="remote_agent_package_not_inactive") as captured:
        asyncio.run(store_inactive_agent_package(Profile(), PREPARED, "revision-1", "delivery-key-2", transport=httpx.MockTransport(handler)))
    assert captured.value.remote_package_id == "unsafe-package"
    assert calls[-1] == ("DELETE", "/architect/packages/unsafe-package")
