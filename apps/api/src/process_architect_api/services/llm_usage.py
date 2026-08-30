from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db_models import BillingUsageReservation, LLMUsageRecord, Workspace
from ..monitoring import record_llm_estimated_cost, set_llm_budget_ratio
from ..paths import WORKSPACE_ROOT
from .billing_usage import monthly_period
from .billing_usage import begin_metered_usage, settle_usage


PRICING_CATALOG_PATH = WORKSPACE_ROOT / "config" / "llm-pricing" / "v1" / "catalog.json"
PICOUSD_PER_USD = Decimal("1000000000000")


class LLMPrice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str
    model: str
    effective_from: datetime = Field(alias="effectiveFrom")
    input_cache_hit: int = Field(alias="inputCacheHitPicousdPerToken", ge=0)
    input_cache_miss: int = Field(alias="inputCacheMissPicousdPerToken", ge=0)
    output: int = Field(alias="outputPicousdPerToken", ge=0)
    time_windows: list[dict] = Field(default_factory=list, alias="timeWindows")


class LLMPricingCatalog(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: str = Field(alias="schemaVersion")
    catalog_version: str = Field(alias="catalogVersion")
    currency: str
    source: str
    models: list[LLMPrice]

    def price(self, provider: str, model: str) -> LLMPrice | None:
        return next((item for item in self.models if item.provider == provider and item.model == model), None)


@lru_cache
def get_llm_pricing_catalog() -> LLMPricingCatalog:
    return LLMPricingCatalog.model_validate_json(PRICING_CATALOG_PATH.read_text(encoding="utf-8"))


def clear_llm_pricing_catalog_cache() -> None:
    get_llm_pricing_catalog.cache_clear()


@dataclass(frozen=True)
class LLMUsageTotals:
    request_count: int
    input_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    output_tokens: int
    outcome: str
    cost_picousd: int | None
    pricing_catalog_version: str | None
    pricing_basis: str


@dataclass(frozen=True)
class LLMUsageMeter:
    workspace: Workspace
    reservation: BillingUsageReservation
    operation: str


def begin_llm_usage(
    db: Session,
    *,
    workspace_id: str,
    settings: Settings,
    operation: str,
    idempotency_key: str,
) -> LLMUsageMeter | None:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise RuntimeError("LLM usage workspace does not exist.")
    metered = begin_metered_usage(
        db,
        workspace_id=workspace.id,
        settings=settings,
        metric="llm_turn",
        operation=operation,
        request_key=idempotency_key,
    )
    if metered is None:
        return None
    reservation = db.get(BillingUsageReservation, metered.reservation_id)
    if reservation is None:
        raise RuntimeError("LLM usage reservation does not exist.")
    db.refresh(reservation)
    return LLMUsageMeter(workspace=workspace, reservation=reservation, operation=operation)


def finish_llm_usage(
    db: Session,
    *,
    meter: LLMUsageMeter | None,
    provider: str,
    model: str,
    observations: list[dict],
    settings: Settings,
) -> None:
    if meter is None:
        return
    record_llm_usage(
        db,
        workspace=meter.workspace,
        reservation=meter.reservation,
        operation=meter.operation,
        provider=provider,
        model=model,
        observations=observations,
        settings=settings,
    )
    settle_usage(
        db,
        reservation_id=meter.reservation.id,
        outcome="consumed" if observations else "released",
        reason_code="llm_attempt_recorded" if observations else "llm_not_requested",
    )
    db.commit()


def calculate_llm_usage(
    *,
    provider: str,
    model: str,
    observations: list[dict],
) -> LLMUsageTotals:
    input_tokens = 0
    output_tokens = 0
    cache_hit_tokens = 0
    cache_miss_tokens = 0
    cache_breakdown_reported = False
    outcomes: list[str] = []
    for observation in observations:
        usage = observation.get("usage") if isinstance(observation, dict) else None
        outcomes.append(str(observation.get("outcome", "provider_error")))
        if not isinstance(usage, dict):
            continue
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        hit = usage.get("prompt_cache_hit_tokens")
        miss = usage.get("prompt_cache_miss_tokens")
        input_tokens += prompt if isinstance(prompt, int) and prompt >= 0 else 0
        output_tokens += completion if isinstance(completion, int) and completion >= 0 else 0
        if isinstance(hit, int) and hit >= 0:
            cache_hit_tokens += hit
            cache_breakdown_reported = True
        if isinstance(miss, int) and miss >= 0:
            cache_miss_tokens += miss
            cache_breakdown_reported = True

    unclassified_input = max(input_tokens - cache_hit_tokens - cache_miss_tokens, 0)
    cache_miss_tokens += unclassified_input
    price = get_llm_pricing_catalog().price(provider, model)
    if price is None:
        cost = None
        catalog_version = None
        pricing_basis = "unpriced"
    else:
        cost = (
            cache_hit_tokens * price.input_cache_hit
            + cache_miss_tokens * price.input_cache_miss
            + output_tokens * price.output
        )
        catalog_version = get_llm_pricing_catalog().catalog_version
        pricing_basis = "reported_cache" if cache_breakdown_reported else "cache_miss_assumed"
    if "success" in outcomes:
        outcome = "success"
    elif input_tokens or output_tokens:
        outcome = "partial"
    else:
        outcome = "provider_error"
    return LLMUsageTotals(
        request_count=len(observations),
        input_tokens=input_tokens,
        cache_hit_tokens=cache_hit_tokens,
        cache_miss_tokens=cache_miss_tokens,
        output_tokens=output_tokens,
        outcome=outcome,
        cost_picousd=cost,
        pricing_catalog_version=catalog_version,
        pricing_basis=pricing_basis,
    )


def record_llm_usage(
    db: Session,
    *,
    workspace: Workspace,
    reservation: BillingUsageReservation,
    operation: str,
    provider: str,
    model: str,
    observations: list[dict],
    settings: Settings,
) -> LLMUsageRecord:
    existing = db.scalar(select(LLMUsageRecord).where(
        LLMUsageRecord.reservation_id == reservation.id
    ))
    if existing is not None:
        return existing
    totals = calculate_llm_usage(provider=provider, model=model, observations=observations)
    record = LLMUsageRecord(
        workspace_id=workspace.id,
        reservation_id=reservation.id,
        operation=operation,
        provider=provider,
        model=model,
        outcome=totals.outcome,
        request_count=totals.request_count,
        input_tokens=totals.input_tokens,
        cache_hit_tokens=totals.cache_hit_tokens,
        cache_miss_tokens=totals.cache_miss_tokens,
        output_tokens=totals.output_tokens,
        estimated_cost_picousd=totals.cost_picousd,
        pricing_catalog_version=totals.pricing_catalog_version,
        pricing_basis=totals.pricing_basis,
    )
    db.add(record)
    db.flush()
    if totals.cost_picousd is not None:
        record_llm_estimated_cost(operation, totals.cost_picousd)
    llm_budget_snapshot(db, settings)
    return record


def llm_budget_snapshot(db: Session, settings: Settings) -> dict:
    period_start, period_end = monthly_period()
    cost = db.scalar(select(func.sum(LLMUsageRecord.estimated_cost_picousd)).where(
        LLMUsageRecord.created_at >= period_start,
        LLMUsageRecord.created_at < period_end,
    )) or 0
    input_tokens = db.scalar(select(func.sum(LLMUsageRecord.input_tokens)).where(
        LLMUsageRecord.created_at >= period_start,
        LLMUsageRecord.created_at < period_end,
    )) or 0
    output_tokens = db.scalar(select(func.sum(LLMUsageRecord.output_tokens)).where(
        LLMUsageRecord.created_at >= period_start,
        LLMUsageRecord.created_at < period_end,
    )) or 0
    unpriced = db.scalar(select(func.count(LLMUsageRecord.id)).where(
        LLMUsageRecord.created_at >= period_start,
        LLMUsageRecord.created_at < period_end,
        LLMUsageRecord.estimated_cost_picousd.is_(None),
    )) or 0
    budget = int(settings.llm_monthly_budget_usd * PICOUSD_PER_USD)
    ratio = float(Decimal(cost) / Decimal(budget)) if budget > 0 else 0.0
    if budget <= 0:
        status = "unconfigured"
    elif cost >= budget:
        status = "exceeded"
    elif ratio * 100 >= settings.llm_budget_warning_percent:
        status = "warning"
    else:
        status = "ok"
    set_llm_budget_ratio(configured=budget > 0, ratio=ratio)
    return {
        "periodStart": period_start,
        "periodEnd": period_end,
        "inputTokens": int(input_tokens),
        "outputTokens": int(output_tokens),
        "estimatedCostPicousd": int(cost),
        "estimatedCostUsd": str((Decimal(cost) / PICOUSD_PER_USD).quantize(Decimal("0.000001"))),
        "unpricedRecords": int(unpriced),
        "budgetPicousd": budget,
        "budgetUsd": str(settings.llm_monthly_budget_usd),
        "warningPercent": settings.llm_budget_warning_percent,
        "budgetRatio": ratio,
        "status": status,
    }
