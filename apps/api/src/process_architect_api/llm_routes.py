from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import CurrentUser
from .config import Settings, get_settings
from .database import get_db
from .db_models import UserLLMCredential
from .deployment_profiles import get_deployment_profile
from .services.llm_credentials import (
    LLMCredentialError,
    PROVIDER_DEFAULTS,
    delete_user_credential,
    list_user_credentials,
    select_user_provider,
    upsert_user_credential,
)


router = APIRouter(prefix="/api/v1/llm", tags=["llm"])
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


class LLMCredentialInput(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    api_key: str | None = Field(default=None, max_length=8_000)
    base_url: str = Field(default="", max_length=2_000)
    model: str = Field(min_length=1, max_length=255)


class LLMPreferenceInput(BaseModel):
    provider: str = Field(min_length=1, max_length=32)


def _credential_response(item: UserLLMCredential, selected: str | None) -> dict:
    return {
        "provider": item.provider,
        "base_url": item.base_url,
        "model": item.model,
        "key_configured": bool(item.encrypted_api_key),
        "is_active": item.is_active,
        "selected": item.provider == selected,
        "updated_at": item.updated_at,
    }


@router.get("/configuration")
def configuration(current_user: CurrentUser, db: DbSession, settings: AppSettings) -> dict:
    profile = get_deployment_profile()
    credential_management_enabled = profile.llm.user_credentials_required
    return {
        "deployment_profile": {
            "id": profile.profile_id,
            "revision": profile.revision,
            "product_name": profile.product_name,
            "allowed_providers": profile.llm.allowed_providers if profile.llm.user_credentials_required else [],
            "system_fallback_allowed": profile.llm.system_fallback_allowed,
            "system_fallback_enabled": settings.llm_system_fallback_enabled,
            "custom_base_url_allowed": profile.llm.custom_base_url_allowed,
            "local_endpoints_allowed": profile.llm.local_endpoints_allowed,
            "credential_management_enabled": credential_management_enabled,
        },
        "providers": [
            {
                "id": provider,
                "default_base_url": PROVIDER_DEFAULTS[provider]["base_url"],
                "requires_api_key": PROVIDER_DEFAULTS[provider]["requires_api_key"],
            }
            for provider in profile.llm.allowed_providers
            if credential_management_enabled
        ],
        "credentials": [
            _credential_response(item, current_user.llm_provider)
            for item in (list_user_credentials(db, current_user.id) if credential_management_enabled else [])
        ],
        "selected_provider": current_user.llm_provider if credential_management_enabled else None,
        "encryption_configured": settings.llm_credential_encryption_configured,
    }


@router.put("/credentials/{provider}")
def save_credential(
    provider: str,
    request: LLMCredentialInput,
    current_user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> dict:
    if not get_deployment_profile().llm.user_credentials_required:
        raise HTTPException(status_code=403, detail={"code": "llm_managed_by_service"})
    if request.provider != provider:
        raise HTTPException(status_code=422, detail={"code": "llm_provider_mismatch"})
    try:
        credential = upsert_user_credential(
            db,
            user=current_user,
            provider=provider,
            base_url=request.base_url,
            model=request.model,
            api_key=request.api_key,
            settings=settings,
        )
    except LLMCredentialError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_llm_credential", "message": str(error)}) from error
    return _credential_response(credential, current_user.llm_provider)


@router.put("/preference", status_code=status.HTTP_204_NO_CONTENT)
def set_preference(
    request: LLMPreferenceInput,
    current_user: CurrentUser,
    db: DbSession,
) -> Response:
    if not get_deployment_profile().llm.user_credentials_required:
        raise HTTPException(status_code=403, detail={"code": "llm_managed_by_service"})
    try:
        select_user_provider(db, current_user, request.provider)
    except LLMCredentialError as error:
        raise HTTPException(status_code=422, detail={"code": "invalid_llm_preference", "message": str(error)}) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/credentials/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def remove_credential(provider: str, current_user: CurrentUser, db: DbSession) -> Response:
    if not get_deployment_profile().llm.user_credentials_required:
        raise HTTPException(status_code=403, detail={"code": "llm_managed_by_service"})
    delete_user_credential(db, current_user, provider)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
