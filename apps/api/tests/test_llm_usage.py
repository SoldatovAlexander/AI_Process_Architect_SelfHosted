from datetime import datetime, timezone

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import BillingUsageReservation, LLMUsageRecord, Workspace
from process_architect_api.deepseek import DeepSeekAnalystTurn, DeepSeekClient
from process_architect_api.deployment_profiles import clear_deployment_profile_cache
from process_architect_api.services.billing_usage import reserve_usage, settle_usage
from process_architect_api.services.llm_usage import calculate_llm_usage, record_llm_usage

from test_api import authorization, request
from test_projects_api import create_project


PASSWORD = "correct-horse-battery-staple"


def register(email: str) -> tuple[dict[str, str], dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": PASSWORD}).json()
    return authorization(tokens), tokens


def hosted_admin(monkeypatch) -> tuple[dict[str, str], str]:
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("SERVICE_ADMIN_EMAILS", "llm-cost-admin@example.com")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, _ = register("llm-cost-admin@example.com")
    workspace_id = request("GET", "/api/v1/auth/me", headers=headers).json()["workspaces"][0]["workspace_id"]
    return headers, workspace_id


def test_deepseek_v4_flash_cost_uses_reported_cache_breakdown():
    totals = calculate_llm_usage(
        provider="deepseek",
        model="deepseek-v4-flash",
        observations=[{
            "operation": "analyst_turn",
            "outcome": "success",
            "usage": {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 40,
                "prompt_cache_miss_tokens": 60,
                "completion_tokens": 20,
            },
        }],
    )

    assert totals.cache_hit_tokens == 40
    assert totals.cache_miss_tokens == 60
    assert totals.output_tokens == 20
    assert totals.cost_picousd == 14_112_000
    assert totals.pricing_basis == "reported_cache"


def test_missing_cache_breakdown_uses_conservative_cache_miss_price():
    totals = calculate_llm_usage(
        provider="deepseek",
        model="deepseek-v4-flash",
        observations=[{
            "outcome": "success",
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }],
    )

    assert totals.cache_hit_tokens == 0
    assert totals.cache_miss_tokens == 100
    assert totals.cost_picousd == 19_600_000
    assert totals.pricing_basis == "cache_miss_assumed"


def test_unknown_model_records_tokens_without_inventing_cost():
    totals = calculate_llm_usage(
        provider="openai_compatible",
        model="local-model",
        observations=[{
            "outcome": "success",
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }],
    )

    assert totals.input_tokens == 50
    assert totals.output_tokens == 10
    assert totals.cost_picousd is None
    assert totals.pricing_basis == "unpriced"


def test_admin_receives_budget_alert_and_numeric_usage(monkeypatch):
    monkeypatch.setenv("LLM_MONTHLY_BUDGET_USD", "0.00001")
    headers, workspace_id = hosted_admin(monkeypatch)
    with get_session_factory()() as db:
        workspace = db.get(Workspace, workspace_id)
        assert workspace is not None
        reservation, _ = reserve_usage(
            db,
            workspace=workspace,
            settings=get_settings(),
            metric="llm_turn",
            idempotency_key="llm-cost-operation-001",
        )
        record = record_llm_usage(
            db,
            workspace=workspace,
            reservation=reservation,
            operation="analyst_turn",
            provider="deepseek",
            model="deepseek-v4-flash",
            observations=[{
                "outcome": "success",
                "usage": {
                    "prompt_tokens": 100,
                    "prompt_cache_hit_tokens": 40,
                    "prompt_cache_miss_tokens": 60,
                    "completion_tokens": 20,
                },
            }],
            settings=get_settings(),
        )
        settle_usage(
            db,
            reservation_id=reservation.id,
            outcome="consumed",
            reason_code="llm_attempt_recorded",
        )
        db.commit()
        assert record.estimated_cost_picousd == 14_112_000

    response = request("GET", "/api/v1/admin/billing/llm-usage", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["inputTokens"] == 100
    assert payload["summary"]["outputTokens"] == 20
    assert payload["summary"]["status"] == "exceeded"
    assert payload["alerts"][0]["code"] == "llm_budget_exceeded"
    assert payload["breakdown"][0]["model"] == "deepseek-v4-flash"
    metrics = request("GET", "/metrics").text
    assert "process_architect_llm_monthly_budget_configured 1.0" in metrics
    assert "process_architect_llm_monthly_budget_ratio 1.4112" in metrics


def test_hosted_analyst_turn_reserves_settles_and_records_provider_usage(monkeypatch):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", "hosted")
    monkeypatch.setenv("SYSTEM_LLM_API_KEY", "service-owned-test-key")
    clear_deployment_profile_cache()
    get_settings.cache_clear()
    headers, project = create_project()
    session = request(
        "POST",
        f"/api/v1/projects/{project['id']}/analyst/sessions",
        headers=headers,
        json={"mode": "refinement", "locale": "en"},
    ).json()

    async def fake_proposal(self, messages):
        self.usage_observations.append({
            "operation": "analyst_turn",
            "outcome": "success",
            "usage": {"prompt_tokens": 120, "completion_tokens": 30},
        })
        return DeepSeekAnalystTurn(message="Which team owns the review?", summary="", patch=[])

    monkeypatch.setattr(DeepSeekClient, "propose_process_patch", fake_proposal)
    response = request(
        "POST",
        f"/api/v1/analyst/sessions/{session['id']}/turns",
        headers=headers,
        json={"content": "Please clarify the review responsibility."},
    )

    assert response.status_code == 201
    with get_session_factory()() as db:
        reservation = db.query(BillingUsageReservation).one()
        usage = db.query(LLMUsageRecord).one()
        assert reservation.status == "consumed"
        assert usage.reservation_id == reservation.id
        assert usage.input_tokens == 120
        assert usage.output_tokens == 30
        assert usage.estimated_cost_picousd == 25_200_000
