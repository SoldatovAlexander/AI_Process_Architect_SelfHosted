from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import get_settings
from .paths import WORKSPACE_ROOT


PROFILE_SCHEMA_PATH = WORKSPACE_ROOT / "02_architecture" / "schemas" / "deployment-profile-v1.schema.json"
BUILTIN_PROFILE_ROOT = WORKSPACE_ROOT / "config" / "deployment_profiles" / "v1"
BUILTIN_PROFILE_IDS = {"hosted", "default", "restricted", "fully-local"}


class LLMPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    allowed_providers: list[Literal["deepseek", "openai", "openai_compatible"]] = Field(alias="allowedProviders", min_length=1)
    user_credentials_required: bool = Field(alias="userCredentialsRequired")
    system_fallback_allowed: bool = Field(alias="systemFallbackAllowed")
    custom_base_url_allowed: bool = Field(alias="customBaseUrlAllowed")
    local_endpoints_allowed: bool = Field(alias="localEndpointsAllowed")


class NetworkPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    egress: Literal["unrestricted", "allowlist", "local_only"]
    allowed_hosts: list[str] = Field(default_factory=list, alias="allowedHosts")


class FeaturePolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    runtime_connections: bool = Field(alias="runtimeConnections")
    code_generation: bool = Field(alias="codeGeneration")
    external_document_sources: bool = Field(alias="externalDocumentSources")
    monitoring: bool


class AdministrationPolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: Literal["hosted", "self_hosted"] = "self_hosted"
    billing_enabled: bool = Field(default=False, alias="billingEnabled")
    license_mode: Literal["issuer", "consumer", "none"] = Field(default="none", alias="licenseMode")

    @model_validator(mode="after")
    def validate_mode_capabilities(self):
        if self.billing_enabled and self.mode != "hosted":
            raise ValueError("Billing can be enabled only in hosted administration mode.")
        if self.license_mode == "issuer" and self.mode != "hosted":
            raise ValueError("License issuer mode is available only to the hosted control plane.")
        if self.mode == "hosted" and self.license_mode == "consumer":
            raise ValueError("Hosted administration cannot consume a workspace license.")
        return self


class DeploymentProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: Literal["1"] = Field(alias="schemaVersion")
    profile_id: str = Field(alias="profileId", pattern=r"^[a-z][a-z0-9-]{1,63}$")
    revision: int = Field(ge=1)
    product_name: str = Field(alias="productName", min_length=1, max_length=120)
    enabled_locales: list[str] = Field(alias="enabledLocales", min_length=1)
    llm: LLMPolicy
    network: NetworkPolicy
    features: FeaturePolicy
    administration: AdministrationPolicy = Field(default_factory=AdministrationPolicy)
    deployment_locked: list[str] = Field(alias="deploymentLocked")


class DeploymentProfileError(RuntimeError):
    pass


def _profile_path() -> Path:
    settings = get_settings()
    if settings.deployment_profile_path.strip():
        return Path(settings.deployment_profile_path).expanduser().resolve()
    if settings.deployment_profile not in BUILTIN_PROFILE_IDS:
        raise DeploymentProfileError(
            f"Unknown deployment profile: {settings.deployment_profile}. Use a built-in profile or DEPLOYMENT_PROFILE_PATH."
        )
    return BUILTIN_PROFILE_ROOT / f"{settings.deployment_profile}.json"


@lru_cache
def get_deployment_profile() -> DeploymentProfile:
    path = _profile_path()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentProfileError(f"Cannot read deployment profile {path}: {error}") from error
    errors = sorted(Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.path))
    if errors:
        details = "; ".join(f"/{'/'.join(map(str, error.path))}: {error.message}" for error in errors[:10])
        raise DeploymentProfileError(f"Invalid deployment profile {path}: {details}")
    try:
        return DeploymentProfile.model_validate(document)
    except ValueError as error:
        raise DeploymentProfileError(f"Invalid deployment profile {path}: {error}") from error


def clear_deployment_profile_cache() -> None:
    get_deployment_profile.cache_clear()


def validate_deployment_configuration() -> DeploymentProfile:
    profile = get_deployment_profile()
    settings = get_settings()
    if profile.llm.user_credentials_required and not settings.llm_credential_encryption_configured:
        raise DeploymentProfileError(
            "LLM_CREDENTIAL_ENCRYPTION_KEY is required by this self-hosted deployment profile."
        )
    if not profile.llm.user_credentials_required and not settings.system_llm_configured:
        raise DeploymentProfileError(
            "A complete SYSTEM_LLM_* configuration is required by the hosted deployment profile."
        )
    return profile
