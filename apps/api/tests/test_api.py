import asyncio
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import delete

from process_architect_api.config import get_settings
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import RubricEntry, RubricEntryTranslation, RubricVersion
from process_architect_api.main import app


ROOT = Path(__file__).resolve().parents[3]
LEAD_FIXTURE = ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json"


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def register() -> dict:
    response = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return response.json()


def authorization(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_health_reports_enabled_auth_and_unconfigured_llm():
    response = request("GET", "/health")
    assert response.json()["version"] == "0.2.0-rc.1"

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["auth"] == {"enabled": True, "securely_configured": True}
    assert response.json()["llm"] == {
        "system_fallback_configured": False,
        "system_fallback_enabled": False,
    }
    assert response.json()["deployment_profile"] == {"id": "default", "revision": 1}
    assert response.json()["dependencies"] == {"rubric": {"status": "ready", "version": "core-1.0"}}


def test_health_rejects_database_without_required_rubric():
    with get_session_factory()() as db:
        db.execute(delete(RubricEntryTranslation))
        db.execute(delete(RubricEntry))
        db.execute(delete(RubricVersion))
        db.commit()

    response = request("GET", "/health")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "rubric_not_ready"


def test_validates_process_ir_fixture():
    process_ir = json.loads(LEAD_FIXTURE.read_text(encoding="utf-8"))
    tokens = register()

    response = request(
        "POST",
        "/api/v1/processes/validate",
        headers=authorization(tokens),
        json=process_ir,
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["counts"] == {"errors": 0, "warnings": 1}


def test_analyst_requires_api_key():
    tokens = register()
    response = request(
        "POST",
        "/api/v1/analyst/draft",
        headers=authorization(tokens),
        json={"description": "Заявка приходит с сайта и создаётся в CRM после проверки."},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_not_configured"


def test_process_endpoints_require_authentication():
    process_ir = json.loads(LEAD_FIXTURE.read_text(encoding="utf-8"))
    response = request("POST", "/api/v1/processes/validate", json=process_ir)
    assert response.status_code == 401


def test_authenticated_export_endpoints():
    process_ir = json.loads(LEAD_FIXTURE.read_text(encoding="utf-8"))
    headers = authorization(register())

    spec = request("POST", "/api/v1/exports/spec", headers=headers, json=process_ir)
    assert spec.status_code == 200
    assert spec.text.startswith("# Lead Intake - Implementation Spec")
    assert "-spec.md" in spec.headers["content-disposition"]

    app_spec = request(
        "POST",
        "/api/v1/exports/app-spec/codex?locale=ru",
        headers=headers,
        json=process_ir,
    )
    assert app_spec.status_code == 200
    assert "Codex / ChatGPT" in app_spec.text
    assert "Начальный промпт" in app_spec.text
    assert "app-spec-codex.md" in app_spec.headers["content-disposition"]

    bpmn = request("POST", "/api/v1/exports/bpmn", headers=headers, json=process_ir)
    assert bpmn.status_code == 200
    assert "bpmn:definitions" in bpmn.text

    drawio = request("POST", "/api/v1/exports/drawio", headers=headers, json=process_ir)
    assert drawio.status_code == 200
    assert "application/vnd.jgraph.mxfile" in drawio.headers["content-type"]
    assert ET.fromstring(drawio.text).tag == "mxfile"
    assert "-bpmn.drawio" in drawio.headers["content-disposition"]

    n8n = request("POST", "/api/v1/exports/n8n/2.32", headers=headers, json=process_ir)
    assert n8n.status_code == 403
    assert n8n.json()["detail"]["entitlementId"] == "export.n8n"


def test_localized_export_rejects_invalid_locale_without_server_error():
    process_ir = json.loads(LEAD_FIXTURE.read_text(encoding="utf-8"))

    response = request(
        "POST",
        "/api/v1/exports/app-spec/codex?locale=ru%3FworkspaceId%3Dinvalid",
        headers=authorization(register()),
        json=process_ir,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_locale"
