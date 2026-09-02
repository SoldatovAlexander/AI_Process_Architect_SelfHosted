import json

import pytest

from process_architect_api.config import get_settings
from process_architect_api.deployment_profiles import (
    DeploymentProfileError,
    clear_deployment_profile_cache,
    get_deployment_profile,
)
from test_api import request


def load_profile(monkeypatch, profile_id: str):
    monkeypatch.setenv("DEPLOYMENT_PROFILE", profile_id)
    monkeypatch.setenv("DEPLOYMENT_PROFILE_PATH", "")
    get_settings.cache_clear()
    clear_deployment_profile_cache()
    return get_deployment_profile()


def test_builtin_profiles_separate_hosted_and_self_hosted_administration(monkeypatch):
    hosted = load_profile(monkeypatch, "hosted")
    assert hosted.administration.mode == "hosted"
    assert hosted.administration.billing_enabled is True
    assert hosted.administration.license_mode == "issuer"

    for profile_id in ("default", "restricted", "fully-local"):
        profile = load_profile(monkeypatch, profile_id)
        assert profile.administration.mode == "self_hosted"
        assert profile.administration.billing_enabled is False
        assert profile.administration.license_mode == "consumer"


def test_legacy_custom_profile_receives_safe_administration_defaults(tmp_path, monkeypatch):
    profile_path = tmp_path / "legacy-profile.json"
    profile_path.write_text(json.dumps({
        "schemaVersion": "1", "profileId": "customer", "revision": 1,
        "productName": "Customer Process Architect", "enabledLocales": ["en"],
        "llm": {
            "allowedProviders": ["openai_compatible"], "userCredentialsRequired": True,
            "systemFallbackAllowed": False, "customBaseUrlAllowed": True, "localEndpointsAllowed": True,
        },
        "network": {"egress": "local_only", "allowedHosts": ["localhost"]},
        "features": {
            "runtimeConnections": True, "codeGeneration": True,
            "externalDocumentSources": False, "monitoring": True,
        },
        "deploymentLocked": ["llm", "network"],
    }), encoding="utf-8")
    monkeypatch.setenv("DEPLOYMENT_PROFILE_PATH", str(profile_path))
    get_settings.cache_clear()
    clear_deployment_profile_cache()

    profile = get_deployment_profile()

    assert profile.administration.mode == "self_hosted"
    assert profile.administration.billing_enabled is False
    assert profile.administration.license_mode == "consumer"


def test_self_hosted_profile_cannot_enable_hosted_billing(tmp_path, monkeypatch):
    source = load_profile(monkeypatch, "default").model_dump(by_alias=True)
    source["profileId"] = "invalid-customer"
    source["administration"] = {"mode": "self_hosted", "billingEnabled": True, "licenseMode": "consumer"}
    path = tmp_path / "invalid-profile.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setenv("DEPLOYMENT_PROFILE_PATH", str(path))
    get_settings.cache_clear()
    clear_deployment_profile_cache()

    with pytest.raises(DeploymentProfileError, match="Billing can be enabled only"):
        get_deployment_profile()


def test_self_hosted_profile_rejects_stripe_webhooks(monkeypatch):
    load_profile(monkeypatch, "default")

    response = request("POST", "/api/v1/billing/webhooks/stripe", content=b"{}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "billing_webhook_unavailable"
