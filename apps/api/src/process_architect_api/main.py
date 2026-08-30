from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .auth import CurrentUser
from . import __version__
from .analyst_routes import router as analyst_router
from .auth_routes import router as auth_router
from .agent_run_routes import router as agent_run_router
from .agent_evaluation_routes import router as agent_evaluation_router
from .agent_dispatch_routes import router as agent_dispatch_router
from .agent_package_delivery_routes import router as agent_package_delivery_router
from .config import get_settings
from .database import get_db, get_session_factory, init_database
from .db_models import RubricVersion
from .deployment_profiles import get_deployment_profile, validate_deployment_configuration
from .deepseek import DeepSeekClient, DeepSeekConfigurationError, DeepSeekResponseError
from .export_routes import router as export_router
from .models import ProcessDescriptionRequest, ProcessDraftResponse, ValidationResult
from .monitoring import metrics_middleware, operational_snapshot, prometheus_payload
from .project_routes import router as project_router
from .project_archive_routes import router as project_archive_router
from .rubric_routes import router as rubric_router
from .template_routes import router as template_router
from .user_template_routes import router as user_template_router
from .n8n_import_routes import router as n8n_import_router
from .n8n_publication_routes import router as n8n_publication_router
from .runtime_connection_routes import router as runtime_connection_router
from .llm_routes import router as llm_router
from .entitlement_routes import router as entitlement_router
from .license_routes import router as license_router
from .workspace_routes import router as workspace_router
from .entitlements import get_entitlement_catalog
from .services.entitlements import ensure_all_workspace_commercial_states
from .services.licensing import ensure_installation_state
from .services.administration import bootstrap_service_admins
from .services.administration import AdminAccessDenied, require_admin_permission
from .services.llm_credentials import resolve_user_llm_connection
from .services.billing_usage import BillingUsageConflict, BillingUsageLimitExceeded
from .services.entitlements import resolve_entitlement_workspace
from .services.llm_usage import begin_llm_usage, finish_llm_usage
from .rubric import CURRENT_RUBRIC_VERSION
from .validation import validate_process_ir
from .process_ir import upgrade_process_ir


@asynccontextmanager
async def lifespan(application: FastAPI):
    validate_deployment_configuration()
    get_entitlement_catalog()
    init_database()
    with get_session_factory()() as db:
        ensure_all_workspace_commercial_states(db, get_settings())
        ensure_installation_state(db)
        db.commit()
        bootstrap_service_admins(db, get_settings())
    yield


app = FastAPI(
    title="AI Process Architect API",
    version=__version__,
    lifespan=lifespan,
)
app.middleware("http")(metrics_middleware)
app.include_router(auth_router)
app.include_router(agent_run_router)
app.include_router(agent_evaluation_router)
app.include_router(agent_dispatch_router)
app.include_router(agent_package_delivery_router)
app.include_router(export_router)
app.include_router(project_router)
app.include_router(project_archive_router)
app.include_router(analyst_router)
app.include_router(template_router)
app.include_router(rubric_router)
app.include_router(user_template_router)
app.include_router(n8n_import_router)
app.include_router(n8n_publication_router)
app.include_router(runtime_connection_router)
app.include_router(llm_router)
app.include_router(entitlement_router)
app.include_router(license_router)
app.include_router(workspace_router)

try:
    from .admin_routes import router as admin_router
except ModuleNotFoundError:
    # The public self-hosted source tree intentionally excludes hosted service administration.
    admin_router = None

if admin_router is not None:
    app.include_router(admin_router)

try:
    from .hosted.billing_webhook_routes import router as billing_webhook_router
except ModuleNotFoundError:
    # The public self-hosted source tree intentionally excludes payment adapters.
    billing_webhook_router = None

if billing_webhook_router is not None:
    app.include_router(billing_webhook_router)


@app.exception_handler(BillingUsageLimitExceeded)
async def billing_usage_limit_handler(_, error: BillingUsageLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": {
                "code": "usage_limit_exceeded",
                "metric": error.metric,
                "limit": error.limit,
                "used": error.used,
            }
        },
    )


@app.exception_handler(BillingUsageConflict)
async def billing_usage_conflict_handler(_, error: BillingUsageConflict) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": {"code": str(error)}},
    )


@app.get("/health")
def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    settings = get_settings()
    profile = get_deployment_profile()
    rubric_ready = db.get(RubricVersion, CURRENT_RUBRIC_VERSION) is not None
    if not rubric_ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "rubric_not_ready"})
    return {
        "status": "ok",
        "service": "process-architect-api",
        "version": __version__,
        "environment": settings.app_env,
        "auth": {
            "enabled": True,
            "securely_configured": settings.auth_securely_configured,
        },
        "llm": {
            "system_fallback_configured": settings.system_llm_configured,
            "system_fallback_enabled": settings.llm_system_fallback_enabled,
        },
        "deployment_profile": {"id": profile.profile_id, "revision": profile.revision},
        "dependencies": {"rubric": {"status": "ready", "version": CURRENT_RUBRIC_VERSION}},
    }


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if not get_settings().metrics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    payload, content_type = prometheus_payload()
    return Response(content=payload, media_type=content_type)


@app.get("/api/v1/ops/diagnostics", include_in_schema=False)
def support_diagnostics(current_user: CurrentUser) -> dict[str, Any]:
    if not get_settings().support_diagnostics_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        require_admin_permission(current_user, "admin.read")
    except AdminAccessDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_permission_required", "permission": str(error)},
        ) from error
    return operational_snapshot()


@app.post("/api/v1/processes/validate", response_model=ValidationResult)
def validate_process(
    current_user: CurrentUser,
    process_ir: dict[str, Any] = Body(),
) -> ValidationResult:
    return validate_process_ir(process_ir)


@app.post("/api/v1/analyst/draft", response_model=ProcessDraftResponse)
async def create_draft(
    request: ProcessDescriptionRequest,
    current_user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", min_length=8, max_length=128),
    ] = None,
) -> ProcessDraftResponse:
    settings = get_settings()
    workspace = resolve_entitlement_workspace(db, current_user)
    usage_meter = begin_llm_usage(
        db,
        workspace_id=workspace.id,
        settings=settings,
        operation="process_draft",
        idempotency_key=idempotency_key or f"server:{uuid4()}",
    )
    connection = resolve_user_llm_connection(db, current_user, settings)
    client: DeepSeekClient | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.deepseek_timeout_seconds) as http_client:
            client = DeepSeekClient(settings, http_client, connection)
            process_ir = upgrade_process_ir(
                await client.create_process_ir(request.description)
            )
    except DeepSeekConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "llm_not_configured", "message": str(error)},
        ) from error
    except (DeepSeekResponseError, httpx.HTTPError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "llm_request_failed", "message": str(error)},
        ) from error
    finally:
        finish_llm_usage(
            db,
            meter=usage_meter,
            provider=connection.provider,
            model=connection.model,
            observations=client.usage_observations if client is not None else [],
            settings=settings,
        )

    validation = validate_process_ir(process_ir)
    if not validation.valid:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "invalid_llm_output",
                "message": "The LLM output does not satisfy Process IR.",
                "validation": validation.model_dump(),
            },
        )

    return ProcessDraftResponse(
        process_ir=process_ir,
        validation=validation,
        provider=connection.provider,
        model=connection.model,
    )
