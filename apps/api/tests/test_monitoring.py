from process_architect_api.config import get_settings
from process_architect_api.monitoring import (
    record_entitlement_decision,
    record_license_validation,
    record_llm_contract_error,
    record_llm_request,
    record_llm_estimated_cost,
)

from test_api import authorization, register, request


def test_metrics_use_route_templates_and_do_not_expose_request_content():
    email = "private-monitoring-user@example.com"
    registered = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert registered.status_code == 201

    missing_id = "private-project-id-that-must-not-be-a-label"
    response = request(
        "GET",
        f"/api/v1/projects/{missing_id}",
        headers=authorization(registered.json()),
    )
    assert response.status_code == 404

    metrics = request("GET", "/metrics")
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain")
    assert "process_architect_http_requests_total" in metrics.text
    assert 'route="/api/v1/projects/{project_id}"' in metrics.text
    assert "process_architect_database_up 1.0" in metrics.text
    assert email not in metrics.text
    assert missing_id not in metrics.text


def test_support_diagnostics_require_admin_role_and_are_privacy_safe(monkeypatch):
    unauthorized = request("GET", "/api/v1/ops/diagnostics")
    assert unauthorized.status_code == 401

    ordinary = register()
    assert request(
        "GET", "/api/v1/ops/diagnostics", headers=authorization(ordinary)
    ).status_code == 403

    monkeypatch.setenv("SERVICE_ADMIN_EMAILS", "monitoring-admin@example.com")
    get_settings.cache_clear()
    registered = request(
        "POST", "/api/v1/auth/register",
        json={"email": "monitoring-admin@example.com", "password": "correct-horse-battery-staple"},
    ).json()
    diagnostics = request(
        "GET",
        "/api/v1/ops/diagnostics",
        headers=authorization(registered),
    )
    assert diagnostics.status_code == 200
    payload = diagnostics.json()
    assert payload["version"] == "0.2.0-rc.1"
    assert payload["database"] == {"up": True, "dialect": "sqlite"}
    assert payload["dispatch_queue"]["jobs"]["queued"] == 0
    assert payload["configuration"]["system_llm_configured"] is False
    assert payload["configuration"]["llm_user_key_encryption_configured"] is True
    assert payload["configuration"]["deployment_profile"] == "default"
    assert payload["configuration"]["administration_mode"] == "self_hosted"
    assert payload["configuration"]["billing_enabled"] is False
    assert payload["configuration"]["license_mode"] == "none"
    assert payload["configuration"]["entitlement_catalog_version"] == "1.1"
    assert payload["configuration"]["self_hosted_default_plan"] == "self_hosted_full"
    assert "token" not in diagnostics.text.lower()
    assert "password" not in diagnostics.text.lower()


def test_metrics_and_diagnostics_can_be_disabled(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "false")
    monkeypatch.setenv("SUPPORT_DIAGNOSTICS_ENABLED", "false")
    get_settings.cache_clear()

    assert request("GET", "/metrics").status_code == 404
    tokens = register()
    response = request(
        "GET",
        "/api/v1/ops/diagnostics",
        headers=authorization(tokens),
    )
    assert response.status_code == 404


def test_llm_metrics_export_only_bounded_operation_and_usage_labels():
    record_llm_request(
        "interview_analysis",
        outcome="success",
        duration_seconds=0.25,
        usage={"prompt_tokens": 12, "completion_tokens": 8},
    )
    record_llm_contract_error("interview_analysis")
    record_llm_estimated_cost("interview_analysis", 1250000)

    metrics = request("GET", "/metrics").text
    assert (
        'process_architect_llm_requests_total{operation="interview_analysis",outcome="success"}'
        in metrics
    )
    assert (
        'process_architect_llm_tokens_total{direction="input",operation="interview_analysis"}'
        in metrics
    )
    assert (
        'process_architect_llm_contract_errors_total{operation="interview_analysis"}'
        in metrics
    )
    assert 'process_architect_llm_estimated_cost_picousd_total{operation="interview_analysis"}' in metrics
    assert "process_architect_llm_monthly_budget_ratio 0.0" in metrics
    assert "process_architect_llm_monthly_budget_configured 0.0" in metrics


def test_entitlement_metrics_use_only_bounded_labels():
    record_entitlement_decision("export.n8n", "allowed")
    record_entitlement_decision("private-workspace-id", "unexpected")

    metrics = request("GET", "/metrics").text
    assert (
        'process_architect_entitlement_decisions_total{entitlement="export.n8n",outcome="allowed"}'
        in metrics
    )
    assert (
        'process_architect_entitlement_decisions_total{entitlement="other",outcome="denied"}'
        in metrics
    )
    assert "private-workspace-id" not in metrics


def test_license_metrics_do_not_use_license_or_workspace_ids():
    record_license_validation("offline", "invalid_signature")

    metrics = request("GET", "/metrics").text
    assert (
        'process_architect_license_validations_total{outcome="invalid_signature",source="offline"}'
        in metrics
    )
