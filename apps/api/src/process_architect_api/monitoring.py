from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select, text

from . import __version__
from .config import get_settings
from .database import get_engine, get_session_factory
from .db_models import AgentDispatchJob


HTTP_REQUESTS = Counter(
    "process_architect_http_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status_class"),
)
HTTP_DURATION = Histogram(
    "process_architect_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
AUTH_ATTEMPTS = Counter(
    "process_architect_auth_attempts_total",
    "Authentication operations by bounded outcome.",
    ("operation", "outcome"),
)
OPERATIONS = Counter(
    "process_architect_operations_total",
    "Product operations by bounded category and outcome.",
    ("operation", "outcome"),
)
LLM_REQUESTS = Counter(
    "process_architect_llm_requests_total",
    "LLM requests by bounded operation and outcome.",
    ("operation", "outcome"),
)
LLM_DURATION = Histogram(
    "process_architect_llm_request_duration_seconds",
    "LLM request duration in seconds.",
    ("operation",),
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 60, 90),
)
LLM_TOKENS = Counter(
    "process_architect_llm_tokens_total",
    "Tokens reported by the LLM provider.",
    ("operation", "direction"),
)
LLM_ESTIMATED_COST = Counter(
    "process_architect_llm_estimated_cost_picousd_total",
    "Estimated LLM cost in trillionths of a US dollar from the versioned pricing catalog.",
    ("operation",),
)
LLM_MONTHLY_BUDGET_RATIO = Gauge(
    "process_architect_llm_monthly_budget_ratio",
    "Current estimated monthly LLM cost divided by the configured service budget.",
)
LLM_MONTHLY_BUDGET_CONFIGURED = Gauge(
    "process_architect_llm_monthly_budget_configured",
    "Whether a positive monthly LLM service budget is configured.",
)
LLM_CONTRACT_ERRORS = Counter(
    "process_architect_llm_contract_errors_total",
    "LLM responses that violated a bounded application response contract.",
    ("operation",),
)
USAGE_TRANSITIONS = Counter(
    "process_architect_billing_usage_transitions_total",
    "Billing usage reservation transitions by bounded metric.",
    ("metric", "transition"),
)
BILLING_INVOICE_RECONCILIATIONS = Counter(
    "process_architect_billing_invoice_reconciliations_total",
    "Invoice reconciliation outcomes by bounded provider and status.",
    ("provider", "status"),
)
ENTITLEMENT_DECISIONS = Counter(
    "process_architect_entitlement_decisions_total",
    "Entitlement checks by bounded entitlement and outcome.",
    ("entitlement", "outcome"),
)
LICENSE_VALIDATIONS = Counter(
    "process_architect_license_validations_total",
    "License activation and validation outcomes without customer identifiers.",
    ("source", "outcome"),
)
DATABASE_UP = Gauge(
    "process_architect_database_up",
    "Whether the application can query its database.",
)
DISPATCH_QUEUE_JOBS = Gauge(
    "process_architect_dispatch_queue_jobs",
    "Agent dispatch jobs by bounded status.",
    ("status",),
)
DISPATCH_QUEUE_OLDEST_SECONDS = Gauge(
    "process_architect_dispatch_queue_oldest_seconds",
    "Age of the oldest queued or retrying dispatch job.",
)
BUILD_INFO = Gauge(
    "process_architect_build_info",
    "Application build information.",
    ("version",),
)
BUILD_INFO.labels(version=__version__).set(1)


_QUEUE_STATUSES = ("queued", "leased", "retry_wait", "dispatched", "dead_letter", "cancelled")
_LLM_OPERATIONS = {
    "process_draft",
    "analyst_turn",
    "interview_analysis",
    "cross_interview_conflicts",
}
_ENTITLEMENT_IDS = {
    "project.create",
    "project.max_active",
    "workspace.max_members",
    "export.spec",
    "export.bpmn",
    "export.n8n",
    "export.agent",
    "code.generate",
    "template.private",
    "interview.import",
    "runtime.publish",
    "agent.execute",
    "backup.export",
}
_LLM_USAGE_CAPTURE: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "llm_usage_capture", default=None
)


@contextmanager
def capture_llm_usage():
    observations: list[dict[str, Any]] = []
    token = _LLM_USAGE_CAPTURE.set(observations)
    try:
        yield observations
    finally:
        _LLM_USAGE_CAPTURE.reset(token)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def _outcome(status_code: int) -> str:
    if status_code >= 500:
        return "server_error"
    if status_code >= 400:
        return "client_error"
    return "success"


def _operation(route: str) -> tuple[str, str] | None:
    auth_prefix = "/api/v1/auth/"
    if route.startswith(auth_prefix):
        operation = route.removeprefix(auth_prefix)
        if operation in {"register", "login", "refresh", "logout"}:
            return "auth", operation
    if route.startswith("/api/v1/exports/"):
        return "product", "export"
    if route.startswith("/api/v1/n8n-imports"):
        return "product", "n8n_import"
    if route.startswith("/api/v1/project-archives"):
        return "product", "project_archive"
    if route.startswith("/api/v1/admin/"):
        return "product", "administration"
    if "/interview" in route:
        return "product", "interview"
    if "/analyst/" in route or route == "/api/v1/analyst/draft":
        return "product", "analyst_turn"
    if "agent-dispatch" in route or "/runtime/agent-runs/" in route:
        return "product", "agent_dispatch"
    return None


async def metrics_middleware(request: Request, call_next):
    if not get_settings().metrics_enabled:
        return await call_next(request)

    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = _route_template(request)
        method = request.method
        outcome = _outcome(status_code)
        HTTP_REQUESTS.labels(method=method, route=route, status_class=f"{status_code // 100}xx").inc()
        HTTP_DURATION.labels(method=method, route=route).observe(perf_counter() - started)
        operation = _operation(route)
        if operation:
            metric_group, operation_name = operation
            if metric_group == "auth":
                AUTH_ATTEMPTS.labels(operation=operation_name, outcome=outcome).inc()
            else:
                OPERATIONS.labels(operation=operation_name, outcome=outcome).inc()


def record_llm_request(
    operation: str,
    *,
    outcome: str,
    duration_seconds: float,
    usage: dict[str, Any] | None = None,
) -> None:
    bounded_operation = operation if operation in _LLM_OPERATIONS else "other"
    bounded_outcome = outcome if outcome in {"success", "provider_error", "invalid_response"} else "provider_error"
    LLM_REQUESTS.labels(operation=bounded_operation, outcome=bounded_outcome).inc()
    LLM_DURATION.labels(operation=bounded_operation).observe(max(duration_seconds, 0))
    capture = _LLM_USAGE_CAPTURE.get()
    if capture is not None:
        capture.append({
            "operation": bounded_operation,
            "outcome": bounded_outcome,
            "durationSeconds": max(duration_seconds, 0),
            "usage": {
                key: value for key, value in (usage or {}).items()
                if key in {
                    "prompt_tokens", "completion_tokens", "total_tokens",
                    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                } and isinstance(value, int) and value >= 0
            },
        })
    if not isinstance(usage, dict):
        return
    for source, direction in (("prompt_tokens", "input"), ("completion_tokens", "output")):
        value = usage.get(source)
        if isinstance(value, int) and value >= 0:
            LLM_TOKENS.labels(operation=bounded_operation, direction=direction).inc(value)


def record_llm_estimated_cost(operation: str, cost_picousd: int) -> None:
    bounded_operation = operation if operation in _LLM_OPERATIONS else "other"
    if cost_picousd >= 0:
        LLM_ESTIMATED_COST.labels(operation=bounded_operation).inc(cost_picousd)


def set_llm_budget_ratio(*, configured: bool, ratio: float) -> None:
    LLM_MONTHLY_BUDGET_CONFIGURED.set(1 if configured else 0)
    LLM_MONTHLY_BUDGET_RATIO.set(max(ratio, 0) if configured else 0)


def record_llm_contract_error(operation: str) -> None:
    bounded_operation = operation if operation in _LLM_OPERATIONS else "other"
    LLM_CONTRACT_ERRORS.labels(operation=bounded_operation).inc()


def record_entitlement_decision(entitlement_id: str, outcome: str) -> None:
    bounded_entitlement = entitlement_id if entitlement_id in _ENTITLEMENT_IDS else "other"
    bounded_outcome = outcome if outcome in {"allowed", "denied"} else "denied"
    ENTITLEMENT_DECISIONS.labels(
        entitlement=bounded_entitlement,
        outcome=bounded_outcome,
    ).inc()


def record_usage_transition(metric: str, transition: str) -> None:
    bounded_metric = metric if metric in {"llm_turn", "export", "runtime_publish", "agent_run"} else "other"
    bounded_transition = transition if transition in {"reserved", "consumed", "released"} else "released"
    USAGE_TRANSITIONS.labels(metric=bounded_metric, transition=bounded_transition).inc()


def record_invoice_reconciliation(provider: str, status: str) -> None:
    bounded_provider = provider if provider in {"stripe", "manual"} else "other"
    bounded_status = status if status in {"matched", "mismatch", "unpriced", "unmapped", "stale"} else "unmapped"
    BILLING_INVOICE_RECONCILIATIONS.labels(provider=bounded_provider, status=bounded_status).inc()


def record_license_validation(source: str, outcome: str) -> None:
    bounded_source = source if source in {"offline", "online", "runtime"} else "runtime"
    bounded_outcomes = {
        "success", "invalid_signature", "binding_mismatch", "expired", "revoked",
        "configuration_error", "server_error", "invalid_document",
    }
    bounded_outcome = outcome if outcome in bounded_outcomes else "invalid_document"
    LICENSE_VALIDATIONS.labels(source=bounded_source, outcome=bounded_outcome).inc()


def operational_snapshot() -> dict[str, Any]:
    settings = get_settings()
    from .deployment_profiles import get_deployment_profile
    from .entitlements import get_entitlement_catalog
    profile = get_deployment_profile()
    entitlement_catalog = get_entitlement_catalog()
    queue = {status: 0 for status in _QUEUE_STATUSES}
    database_up = False
    oldest_seconds = 0.0
    dialect = "unavailable"
    llm_budget = {"configured": False, "ratio": 0.0, "status": "unavailable"}

    try:
        engine = get_engine()
        dialect = engine.dialect.name
        with get_session_factory()() as session:
            from .services.llm_usage import llm_budget_snapshot

            session.execute(text("SELECT 1"))
            budget_snapshot = llm_budget_snapshot(session, settings)
            llm_budget = {
                "configured": budget_snapshot["budgetPicousd"] > 0,
                "ratio": budget_snapshot["budgetRatio"],
                "status": budget_snapshot["status"],
            }
            rows = session.execute(
                select(AgentDispatchJob.status, func.count(AgentDispatchJob.id)).group_by(
                    AgentDispatchJob.status
                )
            ).all()
            for status, count in rows:
                if status in queue:
                    queue[status] = int(count)
            oldest = session.scalar(
                select(func.min(AgentDispatchJob.created_at)).where(
                    AgentDispatchJob.status.in_(("queued", "retry_wait"))
                )
            )
            if oldest:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                oldest_seconds = max((datetime.now(timezone.utc) - oldest).total_seconds(), 0)
        database_up = True
    except Exception:
        database_up = False

    DATABASE_UP.set(1 if database_up else 0)
    for status, count in queue.items():
        DISPATCH_QUEUE_JOBS.labels(status=status).set(count)
    DISPATCH_QUEUE_OLDEST_SECONDS.set(oldest_seconds)

    return {
        "version": __version__,
        "environment": settings.app_env,
        "database": {"up": database_up, "dialect": dialect},
        "dispatch_queue": {"jobs": queue, "oldest_pending_seconds": round(oldest_seconds, 3)},
        "llm_budget": llm_budget,
        "configuration": {
            "auth_securely_configured": settings.auth_securely_configured,
            "deployment_profile": profile.profile_id,
            "administration_mode": profile.administration.mode,
            "billing_enabled": profile.administration.billing_enabled,
            "license_mode": profile.administration.license_mode,
            "entitlement_catalog_version": entitlement_catalog.catalog_version,
            "hosted_default_plan": settings.hosted_default_plan_id,
            "self_hosted_default_plan": settings.self_hosted_default_plan_id,
            "system_llm_configured": settings.system_llm_configured,
            "llm_user_key_encryption_configured": settings.llm_credential_encryption_configured,
            "metrics_enabled": settings.metrics_enabled,
            "transcript_retention_days": settings.transcript_retention_days,
            "transcript_data_residency": settings.transcript_data_residency,
        },
    }


def prometheus_payload() -> tuple[bytes, str]:
    operational_snapshot()
    return generate_latest(), CONTENT_TYPE_LATEST
