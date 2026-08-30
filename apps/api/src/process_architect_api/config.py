from decimal import Decimal
from functools import lru_cache

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import WORKSPACE_ROOT


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = f"sqlite:///{WORKSPACE_ROOT / 'artifacts' / 'process-architect.db'}"
    auth_secret_key: SecretStr = SecretStr("development-only-secret-change-me")
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_PROCESS_API", "DEEPSEEK_API_KEY"),
    )
    deepseek_base_url: AnyHttpUrl = AnyHttpUrl("https://api.deepseek.com")
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 60.0
    system_llm_provider: str = "deepseek"
    system_llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("SYSTEM_LLM_API_KEY", "AI_PROCESS_API", "DEEPSEEK_API_KEY"),
    )
    system_llm_base_url: str = ""
    system_llm_model: str = ""
    llm_system_fallback_enabled: bool = False
    llm_credential_encryption_key: SecretStr | None = None
    deployment_profile: str = "default"
    deployment_profile_path: str = ""
    hosted_default_plan_id: str = "hosted_pilot"
    self_hosted_default_plan_id: str = "self_hosted_full"
    license_trusted_keys_path: str = str(WORKSPACE_ROOT / "config" / "licensing" / "trusted-public-keys.json")
    license_revocations_path: str = str(WORKSPACE_ROOT / "config" / "licensing" / "revocations.json")
    license_server_url: str = ""
    license_server_token: SecretStr | None = None
    license_issuer_private_key_path: str = ""
    license_issuer_key_id: str = ""
    license_issuer_default_months: int = Field(default=1, ge=1, le=3)
    license_issuer_max_months: int = Field(default=3, ge=1, le=3)
    license_clock_skew_seconds: int = Field(default=300, ge=0, le=3600)
    service_admin_emails: str = ""
    billing_grace_days: int = Field(default=7, ge=0, le=90)
    billing_usage_reservation_minutes: int = Field(default=60, ge=1, le=1440)
    billing_pricing_catalog_path: str = str(
        WORKSPACE_ROOT / "config" / "billing-pricing" / "v1" / "catalog.json"
    )
    billing_stripe_webhook_secret: SecretStr | None = None
    billing_stripe_webhook_tolerance_seconds: int = Field(default=300, ge=1, le=3600)
    billing_webhook_max_bytes: int = Field(default=1_048_576, ge=1_024, le=10_485_760)
    llm_monthly_budget_usd: Decimal = Field(default=Decimal("0"), ge=0)
    llm_budget_warning_percent: int = Field(default=80, ge=1, le=100)
    max_workspaces_per_user: int = Field(default=10, ge=1, le=100)
    agent_worker_poll_seconds: float = 2.0
    agent_worker_lease_seconds: int = 90
    agent_worker_max_attempts: int = 5
    agent_worker_dispatch_enabled: bool = True
    e2e_runtime_enabled: bool = False
    openclaw_runtime_url: str = ""
    openclaw_runtime_token: SecretStr | None = None
    hermes_runtime_url: str = ""
    hermes_runtime_token: SecretStr | None = None
    agent_runtime_callback_token: SecretStr | None = None
    agent_runtime_callback_base_url: str = ""
    transcript_retention_days: int = Field(default=0, ge=0, le=3650)
    transcript_data_residency: str = Field(default="local", min_length=1, max_length=64)
    metrics_enabled: bool = True
    support_diagnostics_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=WORKSPACE_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def deepseek_configured(self) -> bool:
        return bool(
            self.deepseek_api_key
            and self.deepseek_api_key.get_secret_value().strip()
        )

    @property
    def system_llm_configured(self) -> bool:
        key_optional = self.system_llm_provider == "openai_compatible"
        configured_key = self.system_llm_api_key or (
            self.deepseek_api_key if self.system_llm_provider == "deepseek" else None
        )
        endpoint_configured = bool(self.system_llm_base_url.strip()) or self.system_llm_provider in {"deepseek", "openai"}
        model_configured = bool(self.system_llm_model.strip()) or self.system_llm_provider == "deepseek"
        return bool(
            endpoint_configured
            and model_configured
            and (key_optional or (configured_key and configured_key.get_secret_value().strip()))
        )

    @property
    def llm_credential_encryption_configured(self) -> bool:
        return bool(
            self.llm_credential_encryption_key
            and self.llm_credential_encryption_key.get_secret_value().strip()
        )

    @property
    def auth_securely_configured(self) -> bool:
        secret = self.auth_secret_key.get_secret_value()
        return len(secret) >= 32 and secret != "development-only-secret-change-me"

    @property
    def service_admin_email_set(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.service_admin_emails.split(",")
            if value.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
