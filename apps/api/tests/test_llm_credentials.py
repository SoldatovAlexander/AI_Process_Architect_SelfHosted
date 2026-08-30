import asyncio

import httpx
import pytest
from sqlalchemy import select

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import User, UserLLMCredential
from process_architect_api.deployment_profiles import DeploymentProfileError, clear_deployment_profile_cache, get_deployment_profile, validate_deployment_configuration
from process_architect_api.main import app
from process_architect_api.services.llm_credentials import resolve_user_llm_connection


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def register(email: str) -> dict[str, str]:
    response = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"})
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_user_can_store_select_and_remove_encrypted_provider_key():
    first = register("first@example.com")
    second = register("second@example.com")
    secret = "sk-user-secret-that-must-never-leak"

    saved = request(
        "PUT",
        "/api/v1/llm/credentials/openai",
        headers=first,
        json={"provider": "openai", "api_key": secret, "base_url": "", "model": "gpt-5-mini"},
    )
    assert saved.status_code == 200
    assert saved.json()["key_configured"] is True
    assert secret not in saved.text

    own = request("GET", "/api/v1/llm/configuration", headers=first)
    other = request("GET", "/api/v1/llm/configuration", headers=second)
    assert own.json()["selected_provider"] == "openai"
    assert own.json()["credentials"][0]["base_url"] == "https://api.openai.com/v1"
    assert other.json()["credentials"] == []
    assert secret not in own.text

    with get_session_factory()() as db:
        stored = db.scalar(select(UserLLMCredential))
        assert stored is not None
        assert stored.encrypted_api_key != secret
        assert secret not in (stored.encrypted_api_key or "")

    removed = request("DELETE", "/api/v1/llm/credentials/openai", headers=first)
    assert removed.status_code == 204
    assert request("GET", "/api/v1/llm/configuration", headers=first).json()["credentials"] == []


def test_key_can_be_omitted_when_updating_existing_credential():
    headers = register("edit@example.com")
    payload = {"provider": "deepseek", "api_key": "secret", "base_url": "", "model": "deepseek-chat"}
    assert request("PUT", "/api/v1/llm/credentials/deepseek", headers=headers, json=payload).status_code == 200
    payload.update({"api_key": None, "model": "deepseek-reasoner"})
    response = request("PUT", "/api/v1/llm/credentials/deepseek", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["model"] == "deepseek-reasoner"
    assert response.json()["key_configured"] is True


def test_fully_local_profile_accepts_local_keyless_endpoint_and_blocks_remote(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "fully-local")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    headers = register("local@example.com")

    local = request(
        "PUT",
        "/api/v1/llm/credentials/openai_compatible",
        headers=headers,
        json={"provider": "openai_compatible", "api_key": None, "base_url": "http://ollama:11434/v1", "model": "qwen3"},
    )
    assert local.status_code == 200
    assert local.json()["key_configured"] is False

    remote = request(
        "PUT",
        "/api/v1/llm/credentials/openai_compatible",
        headers=headers,
        json={"provider": "openai_compatible", "api_key": None, "base_url": "https://llm.example.com/v1", "model": "custom"},
    )
    assert remote.status_code == 422
    assert "blocks remote" in remote.json()["detail"]["message"]


def test_hosted_profile_uses_service_configuration_and_disables_user_keys(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("SYSTEM_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SYSTEM_LLM_API_KEY", "service-owned-secret")
    monkeypatch.setenv("SYSTEM_LLM_MODEL", "gpt-5-mini")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    headers = register("hosted@example.com")

    configuration = request("GET", "/api/v1/llm/configuration", headers=headers)
    assert configuration.status_code == 200
    assert configuration.json()["deployment_profile"]["credential_management_enabled"] is False
    assert configuration.json()["providers"] == []
    assert "service-owned-secret" not in configuration.text

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == "hosted@example.com"))
        assert user is not None
        connection = resolve_user_llm_connection(db, user, get_settings())
        assert (connection.provider, connection.base_url, connection.model, connection.source) == (
            "openai",
            "https://api.openai.com/v1",
            "gpt-5-mini",
            "system",
        )
        assert connection.api_key == "service-owned-secret"

    save = request(
        "PUT",
        "/api/v1/llm/credentials/openai",
        headers=headers,
        json={"provider": "openai", "api_key": "user-secret", "base_url": "", "model": "gpt-5-mini"},
    )
    assert save.status_code == 403
    assert save.json()["detail"]["code"] == "llm_managed_by_service"


def test_builtin_deployment_profiles_validate():
    for profile_id in ("hosted", "default", "restricted", "fully-local"):
        get_settings().deployment_profile = profile_id
        clear_deployment_profile_cache()
        assert get_deployment_profile().profile_id == profile_id


def test_self_hosted_profile_fails_fast_without_encryption_key(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "default")
    monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    with pytest.raises(DeploymentProfileError, match="LLM_CREDENTIAL_ENCRYPTION_KEY"):
        validate_deployment_configuration()


def test_hosted_profile_fails_fast_without_service_provider(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("AI_PROCESS_API", "")
    monkeypatch.setenv("SYSTEM_LLM_API_KEY", "")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    with pytest.raises(DeploymentProfileError, match="SYSTEM_LLM"):
        validate_deployment_configuration()
