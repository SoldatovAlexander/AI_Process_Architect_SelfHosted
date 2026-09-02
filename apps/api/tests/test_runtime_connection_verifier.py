import asyncio
import socket

import httpx
import pytest

from process_architect_api.services.runtime_connections import RuntimeVerificationError, validate_egress_target, verify_runtime_connection


class Profile:
    endpoint_url = "https://runtime.example.com"
    secret_ref = "env:RUNTIME_TEST_SECRET"
    kind = "n8n"
    n8n_minor = "2.32"


def test_n8n_verifier_authenticates_and_checks_minor(monkeypatch):
    monkeypatch.setenv("RUNTIME_TEST_SECRET", "do-not-log-this")
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-N8N-API-KEY"] == "do-not-log-this"
        if request.url.path == "/api/v1/workflows":
            return httpx.Response(200, request=request, json={"data": []})
        return httpx.Response(200, request=request, json={"data": {"versionCli": "2.32.7"}})

    result = asyncio.run(verify_runtime_connection(Profile(), transport=httpx.MockTransport(handler)))
    assert result.detected_version == "2.32.7"


def test_n8n_verifier_rejects_wrong_minor(monkeypatch):
    monkeypatch.setenv("RUNTIME_TEST_SECRET", "secret")
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request, json={"data": {"versionCli": "2.31.9"}}))
    with pytest.raises(RuntimeVerificationError, match="n8n_version_mismatch"):
        asyncio.run(verify_runtime_connection(Profile(), transport=transport))


def test_agent_verifier_requires_explicit_runtime_identity(monkeypatch):
    monkeypatch.setenv("RUNTIME_TEST_SECRET", "secret")
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)
    profile = Profile()
    profile.kind = "hermes"
    profile.n8n_minor = None
    transport = httpx.MockTransport(lambda request: httpx.Response(200, request=request, json={"status": "ok", "runtime": "openclaw"}))
    with pytest.raises(RuntimeVerificationError, match="runtime_identity_mismatch"):
        asyncio.run(verify_runtime_connection(profile, transport=transport))


def test_openclaw_verifier_records_only_certified_runtime_version(monkeypatch):
    monkeypatch.setenv("RUNTIME_TEST_SECRET", "secret")
    monkeypatch.setattr("process_architect_api.services.runtime_connections.validate_egress_target", lambda _url: None)
    profile = Profile()
    profile.kind = "openclaw"
    profile.n8n_minor = None

    certified = httpx.MockTransport(lambda request: httpx.Response(200, request=request, json={"runtime": "openclaw", "version": "bridge-2.0", "runtimeVersion": "2026.8.2"}))
    assert asyncio.run(verify_runtime_connection(profile, transport=certified)).detected_version == "2026.8.2"

    legacy = httpx.MockTransport(lambda request: httpx.Response(200, request=request, json={"runtime": "openclaw", "version": "bridge-1.4"}))
    assert asyncio.run(verify_runtime_connection(profile, transport=legacy)).detected_version is None


def test_verifier_blocks_link_local_metadata_targets(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))])
    with pytest.raises(RuntimeVerificationError, match="egress_target_blocked"):
        validate_egress_target("https://metadata.example.com")
