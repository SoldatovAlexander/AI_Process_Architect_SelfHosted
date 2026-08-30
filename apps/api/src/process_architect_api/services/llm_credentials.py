from __future__ import annotations

import base64
import hashlib
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import User, UserLLMCredential
from ..deployment_profiles import DeploymentProfile, get_deployment_profile


PROVIDER_DEFAULTS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "requires_api_key": True},
    "openai": {"base_url": "https://api.openai.com/v1", "requires_api_key": True},
    "openai_compatible": {"base_url": "", "requires_api_key": False},
}


class LLMCredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedLLMConnection:
    provider: str
    api_key: str | None
    base_url: str
    model: str
    source: str

    @property
    def configured(self) -> bool:
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})
        return bool(self.base_url and self.model and (self.api_key or not defaults.get("requires_api_key", True)))


def _fernet(settings: Settings) -> Fernet:
    secret = settings.llm_credential_encryption_key
    if not secret or not secret.get_secret_value().strip():
        raise LLMCredentialError(
            "LLM_CREDENTIAL_ENCRYPTION_KEY must be configured before user LLM keys can be stored."
        )
    digest = hashlib.sha256(secret.get_secret_value().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_api_key(value: str | None, settings: Settings) -> str | None:
    if not value:
        return None
    return _fernet(settings).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_api_key(value: str | None, settings: Settings) -> str | None:
    if not value:
        return None
    try:
        return _fernet(settings).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as error:
        raise LLMCredentialError("The stored LLM key cannot be decrypted with this installation key.") from error


def _is_local_host(hostname: str) -> bool:
    if hostname in {"localhost", "host.docker.internal", "ollama"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_private or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def validate_provider_configuration(
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
    profile: DeploymentProfile,
) -> tuple[str, str, str | None]:
    if provider not in profile.llm.allowed_providers or provider not in PROVIDER_DEFAULTS:
        raise LLMCredentialError("This LLM provider is not allowed by the deployment profile.")
    normalized_model = model.strip()
    if not normalized_model or len(normalized_model) > 255:
        raise LLMCredentialError("Specify a valid model identifier.")
    defaults = PROVIDER_DEFAULTS[provider]
    if provider == "openai_compatible":
        if not profile.llm.custom_base_url_allowed:
            raise LLMCredentialError("Custom LLM endpoints are disabled by the deployment profile.")
        normalized_url = base_url.strip().rstrip("/")
    else:
        normalized_url = defaults["base_url"]
    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LLMCredentialError("Use an HTTP(S) LLM endpoint without credentials, query, or fragment.")
    local = _is_local_host(parsed.hostname)
    if parsed.scheme != "https" and not (profile.llm.local_endpoints_allowed and local):
        raise LLMCredentialError("LLM endpoints require HTTPS unless the profile allows local endpoints.")
    if profile.network.egress == "local_only" and not local:
        raise LLMCredentialError("The fully-local profile blocks remote LLM endpoints.")
    if profile.network.egress == "allowlist" and parsed.hostname not in profile.network.allowed_hosts:
        raise LLMCredentialError("The LLM endpoint is not in the deployment egress allowlist.")
    normalized_key = api_key.strip() if api_key else None
    if defaults["requires_api_key"] and not normalized_key:
        raise LLMCredentialError("This provider requires an API key.")
    return normalized_url, normalized_model, normalized_key


def list_user_credentials(db: Session, user_id: str) -> list[UserLLMCredential]:
    return list(
        db.scalars(
            select(UserLLMCredential)
            .where(UserLLMCredential.user_id == user_id)
            .order_by(UserLLMCredential.provider)
        )
    )


def upsert_user_credential(
    db: Session,
    *,
    user: User,
    provider: str,
    base_url: str,
    model: str,
    api_key: str | None,
    settings: Settings,
) -> UserLLMCredential:
    profile = get_deployment_profile()
    credential = db.scalar(
        select(UserLLMCredential).where(
            UserLLMCredential.user_id == user.id,
            UserLLMCredential.provider == provider,
        )
    )
    effective_api_key = api_key
    if effective_api_key is None and credential is not None:
        effective_api_key = decrypt_api_key(credential.encrypted_api_key, settings)
    normalized_url, normalized_model, normalized_key = validate_provider_configuration(
        provider, base_url, model, effective_api_key, profile
    )
    if credential is None:
        credential = UserLLMCredential(user_id=user.id, provider=provider)
        db.add(credential)
    credential.base_url = normalized_url
    credential.model = normalized_model
    credential.is_active = True
    if api_key is not None and normalized_key is not None:
        credential.encrypted_api_key = encrypt_api_key(normalized_key, settings)
    elif provider == "openai_compatible":
        credential.encrypted_api_key = None
    if provider in {"deepseek", "openai"} and not credential.encrypted_api_key:
        raise LLMCredentialError("This provider requires an API key.")
    if not user.llm_provider:
        user.llm_provider = provider
    db.commit()
    db.refresh(credential)
    return credential


def select_user_provider(db: Session, user: User, provider: str) -> None:
    profile = get_deployment_profile()
    if provider not in profile.llm.allowed_providers:
        raise LLMCredentialError("This LLM provider is not allowed by the deployment profile.")
    credential = db.scalar(
        select(UserLLMCredential).where(
            UserLLMCredential.user_id == user.id,
            UserLLMCredential.provider == provider,
            UserLLMCredential.is_active.is_(True),
        )
    )
    if credential is None:
        raise LLMCredentialError("Configure this LLM provider before selecting it.")
    user.llm_provider = provider
    db.commit()


def delete_user_credential(db: Session, user: User, provider: str) -> None:
    credential = db.scalar(
        select(UserLLMCredential).where(
            UserLLMCredential.user_id == user.id,
            UserLLMCredential.provider == provider,
        )
    )
    if credential:
        db.delete(credential)
    if user.llm_provider == provider:
        user.llm_provider = None
    db.commit()


def resolve_user_llm_connection(db: Session, user: User, settings: Settings) -> ResolvedLLMConnection:
    profile = get_deployment_profile()
    system_connection = _resolve_system_connection(settings, profile)
    if not profile.llm.user_credentials_required:
        return system_connection
    credentials = {item.provider: item for item in list_user_credentials(db, user.id) if item.is_active}
    provider = user.llm_provider if user.llm_provider in credentials else next(iter(credentials), None)
    if provider:
        credential = credentials[provider]
        return ResolvedLLMConnection(
            provider=provider,
            api_key=decrypt_api_key(credential.encrypted_api_key, settings),
            base_url=credential.base_url,
            model=credential.model,
            source="user",
        )
    if settings.llm_system_fallback_enabled and profile.llm.system_fallback_allowed:
        return system_connection
    fallback_provider = profile.llm.allowed_providers[0]
    return ResolvedLLMConnection(
        provider=fallback_provider,
        api_key=None,
        base_url=PROVIDER_DEFAULTS[fallback_provider]["base_url"],
        model=settings.deepseek_model if fallback_provider == "deepseek" else "",
        source="missing",
    )


def _resolve_system_connection(settings: Settings, profile: DeploymentProfile) -> ResolvedLLMConnection:
    provider = settings.system_llm_provider.strip() or "deepseek"
    if provider not in profile.llm.allowed_providers or provider not in PROVIDER_DEFAULTS:
        return ResolvedLLMConnection(provider=provider, api_key=None, base_url="", model="", source="missing")
    legacy_deepseek = provider == "deepseek" and not settings.system_llm_base_url.strip()
    base_url = str(settings.deepseek_base_url).rstrip("/") if legacy_deepseek else (settings.system_llm_base_url.strip().rstrip("/") or PROVIDER_DEFAULTS[provider]["base_url"])
    model = settings.deepseek_model if legacy_deepseek else settings.system_llm_model.strip()
    secret = settings.system_llm_api_key or (settings.deepseek_api_key if provider == "deepseek" else None)
    api_key = secret.get_secret_value().strip() if secret and secret.get_secret_value().strip() else None
    try:
        base_url, model, api_key = validate_provider_configuration(provider, base_url, model, api_key, profile)
    except LLMCredentialError:
        return ResolvedLLMConnection(provider=provider, api_key=None, base_url="", model="", source="missing")
    return ResolvedLLMConnection(provider=provider, api_key=api_key, base_url=base_url, model=model, source="system")
