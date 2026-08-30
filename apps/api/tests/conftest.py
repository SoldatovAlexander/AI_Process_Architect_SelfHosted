import pytest

from process_architect_api.config import get_settings
from process_architect_api.database import get_engine, get_session_factory, init_database
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from process_architect_api.entitlements import clear_entitlement_catalog_cache

try:
    from process_architect_api.hosted.billing_pricing import clear_billing_pricing_catalog_cache
except ModuleNotFoundError:
    def clear_billing_pricing_catalog_cache() -> None:
        """Hosted billing is intentionally absent from public self-hosted test builds."""


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-with-at-least-32-characters")
    # Empty environment values override a developer's root .env during tests.
    monkeypatch.setenv("AI_PROCESS_API", "")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("LLM_SYSTEM_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", "test-credential-encryption-key")
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "default")
    monkeypatch.setenv("DEPLOYMENT_PROFILE_PATH", "")
    monkeypatch.setenv("SERVICE_ADMIN_EMAILS", "")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    clear_entitlement_catalog_cache()
    clear_billing_pricing_catalog_cache()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    init_database()
    yield
    get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    clear_entitlement_catalog_cache()
    clear_billing_pricing_catalog_cache()
