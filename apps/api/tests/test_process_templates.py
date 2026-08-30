from copy import deepcopy

from process_architect_api.process_templates import (
    ALL_TEMPLATE_SPECS,
    BATCH_071_300_TEMPLATE_SPECS,
    CATALOG_TEMPLATE_SPECS,
    LEGACY_CATALOG_TEMPLATE_SPECS,
    TEMPLATE_SPECS,
    get_process_template,
    list_process_templates,
)
from process_architect_api.rubric import RUBRIC_ENTRIES, DOMAIN_LABELS, entry_id
from process_architect_api.validation import validate_process_ir
from test_api import authorization, request


def _register(email: str = "template-owner@example.com") -> tuple[dict, dict]:
    tokens = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    ).json()
    headers = authorization(tokens)
    user = request("GET", "/api/v1/auth/me", headers=headers).json()
    return headers, user


def test_catalog_contains_ready_and_interview_draft_templates():
    assert len(TEMPLATE_SPECS) == 20
    assert len(LEGACY_CATALOG_TEMPLATE_SPECS) == 50
    assert len(BATCH_071_300_TEMPLATE_SPECS) == 226
    assert len(CATALOG_TEMPLATE_SPECS) == 276
    assert len(ALL_TEMPLATE_SPECS) == 296
    assert len({item.id for item in ALL_TEMPLATE_SPECS}) == 296

    for locale in ("ru", "en", "es"):
        templates = list_process_templates(locale)
        assert len(templates) == 296
        assert all("process_ir" not in item for item in templates)
        assert all(validate_process_ir(get_process_template(item["id"], locale)["process_ir"]).valid for item in templates)
        assert sum(item["status"] == "ready" for item in templates) == 20
        assert sum(item["status"] == "interview_draft" for item in templates) == 276
        assert all(item["step_count"] >= 8 for item in templates if item["status"] == "ready")
        assert all(item["step_count"] == 2 for item in templates if item["status"] == "interview_draft")
        assert all(item["preview_steps"] for item in templates)
        assert sum(item["agent_enabled"] for item in templates) == 28
        assert all(len(item["rubric_entry_ids"]) == 9 for item in templates)


def test_all_template_classifications_use_known_unique_rubric_dimensions():
    known_ids = {
        entry_id(dimension, code)
        for dimension, code, _, _, _ in RUBRIC_ENTRIES
    } | {entry_id("domain", code) for code in DOMAIN_LABELS}

    for template in list_process_templates("en"):
        entry_ids = template["rubric_entry_ids"]
        assert set(entry_ids) <= known_ids
        dimensions = [identifier.split(":", 2)[1] for identifier in entry_ids]
        assert len(dimensions) == len(set(dimensions)) == 9
        detailed = get_process_template(template["id"], "en")
        assert detailed["process_ir"]["classification"] == {
            "rubricVersion": "core-1.0",
            "status": "proposed",
            "entryIds": entry_ids,
            "classifiedAt": None,
            "classifiedByUserId": None,
        }


def test_templates_api_lists_and_recognizes_interview_process():
    headers, _ = _register()

    catalog = request("GET", "/api/v1/process-templates", headers=headers, params={"locale": "ru"})
    assert catalog.status_code == 200
    assert len(catalog.json()) == 296
    assert all(template["process_ir"] is None for template in catalog.json())

    agent_detail = request(
        "GET",
        "/api/v1/process-templates/catalog-autonomous-agents-autonomous-company-research-agent",
        headers=headers,
        params={"locale": "ru"},
    )
    assert agent_detail.status_code == 200
    assert agent_detail.json()["name"] == "Автономный агент исследования компаний"
    assert agent_detail.json()["process_ir"] is not None
    assert len(agent_detail.json()["process_ir"]["openQuestions"]) == 6

    suggestion = request(
        "POST",
        "/api/v1/process-templates/suggest",
        headers=headers,
        json={
            "locale": "ru",
            "text": "Лиды приходят с сайта, надо квалифицировать их и назначать менеджера в CRM.",
            "excluded_ids": [],
        },
    )
    assert suggestion.status_code == 200
    assert suggestion.json()["template"]["id"] == "lead-qualification"
    assert suggestion.json()["confidence"] >= 0.7

    catalog_suggestion = request(
        "POST",
        "/api/v1/process-templates/suggest",
        headers=headers,
        json={
            "locale": "ru",
            "text": "Нужен контроль SLA и автоматическая эскалация тикетов.",
            "excluded_ids": [],
        },
    )
    assert catalog_suggestion.status_code == 200
    assert catalog_suggestion.json()["template"]["id"] == "catalog-support-sla-monitoring-escalation"
    assert catalog_suggestion.json()["template"]["status"] == "interview_draft"

    no_suggestion = request(
        "POST",
        "/api/v1/process-templates/suggest",
        headers=headers,
        json={"locale": "ru", "text": "Пока просто обсуждаем идею", "excluded_ids": []},
    )
    assert no_suggestion.status_code == 200
    assert no_suggestion.json() is None


def test_templates_api_filters_by_multiple_rubric_facets():
    headers, _ = _register("template-filter-owner@example.com")
    selected = [entry_id("domain", "autonomous_agents"), entry_id("automation_mode", "ai_agent")]

    response = request(
        "GET",
        "/api/v1/process-templates",
        headers=headers,
        params=[("locale", "ru"), *(('rubricEntryId', identifier) for identifier in selected)],
    )

    assert response.status_code == 200
    templates = response.json()
    assert templates
    assert all(set(selected) <= set(template["rubric_entry_ids"]) for template in templates)
    assert all(template["agent_enabled"] for template in templates)

    invalid = request(
        "GET",
        "/api/v1/process-templates",
        headers=headers,
        params={"rubricEntryId": "core-1.0:domain:not-real"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_rubric_filter"


def test_template_suggestion_uses_rubric_text_and_explicit_facets():
    headers, _ = _register("template-rubric-suggestion-owner@example.com")

    from_text = request(
        "POST",
        "/api/v1/process-templates/suggest",
        headers=headers,
        json={"locale": "ru", "text": "Нужен процесс для автономных агентов", "excluded_ids": []},
    )
    assert from_text.status_code == 200
    assert entry_id("domain", "autonomous_agents") in from_text.json()["template"]["rubric_entry_ids"]

    from_facets = request(
        "POST",
        "/api/v1/process-templates/suggest",
        headers=headers,
        json={
            "locale": "ru",
            "text": "Нужно автоматизировать этот процесс",
            "excluded_ids": [],
            "rubric_entry_ids": [entry_id("domain", "autonomous_agents"), entry_id("automation_mode", "ai_agent")],
        },
    )
    assert from_facets.status_code == 200
    assert from_facets.json()["template"]["agent_enabled"] is True


def test_agent_catalog_template_is_exposed_with_agent_metadata():
    template = next(item for item in list_process_templates("en") if item["library_number"] == 263)

    assert template["id"] == "catalog-autonomous-agents-autonomous-company-research-agent"
    assert template["agent_enabled"] is True
    assert template["agent_topology"] == "single_tool_agent"
    assert template["status"] == "interview_draft"
    detailed = get_process_template(template["id"], "en")
    assert len(detailed["process_ir"]["openQuestions"]) == 6


def test_batch_titles_and_steps_are_localized():
    template_id = "catalog-autonomous-agents-autonomous-company-research-agent"
    assert get_process_template(template_id, "ru")["name"] == "Автономный агент исследования компаний"
    assert get_process_template(template_id, "es")["name"] == "Agente autónomo de investigación de empresas"
    assert get_process_template(template_id, "ru")["preview_steps"][0] == "Определить цель"
    assert get_process_template(template_id, "es")["preview_steps"][0] == "Definir objetivo"
    assert "autonomous company research agent" in get_process_template(template_id, "ru")["search_terms"]


def test_applying_template_creates_an_undoable_revision():
    headers, user = _register()
    initial_ir = deepcopy(get_process_template(TEMPLATE_SPECS[0].id, "ru")["process_ir"])
    initial_ir["process"]["id"] = "process_template_test"
    created = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Тест библиотеки",
            "default_locale": "ru",
            "process_ir": initial_ir,
        },
    ).json()

    applied = request(
        "POST",
        f"/api/v1/projects/{created['id']}/templates/invoice-approval",
        headers=headers,
        json={"base_revision_id": created["current_revision_id"], "locale": "ru"},
    )
    assert applied.status_code == 201
    changed = applied.json()
    assert changed["current_revision"]["version_number"] == 2
    assert changed["current_revision"]["source"] == "template"
    assert changed["current_revision"]["process_ir"]["process"]["name"] == "Согласование счета поставщика"
    assert changed["current_revision"]["process_ir"]["process"]["id"] == "process_template_test"

    undone = request(
        "POST",
        f"/api/v1/projects/{created['id']}/undo",
        headers=headers,
        json={"base_revision_id": changed["current_revision_id"]},
    )
    assert undone.status_code == 201
    assert undone.json()["current_revision"]["process_ir"] == initial_ir


def test_applying_current_template_is_idempotent():
    headers, user = _register("template-idempotency-owner@example.com")
    initial_ir = deepcopy(get_process_template(TEMPLATE_SPECS[0].id, "ru")["process_ir"])
    initial_ir["process"]["id"] = "process_template_idempotency_test"
    created = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Повторное применение шаблона",
            "default_locale": "ru",
            "process_ir": initial_ir,
        },
    ).json()

    applied = request(
        "POST",
        f"/api/v1/projects/{created['id']}/templates/lead-qualification",
        headers=headers,
        json={"base_revision_id": created["current_revision_id"], "locale": "ru"},
    )

    assert applied.status_code == 201
    unchanged = applied.json()
    assert unchanged["current_revision_id"] == created["current_revision_id"]
    assert unchanged["current_revision"]["version_number"] == 1

    revisions = request(
        "GET",
        f"/api/v1/projects/{created['id']}/revisions",
        headers=headers,
    )
    assert revisions.status_code == 200
    assert len(revisions.json()) == 1


def test_applying_catalog_template_starts_an_interview_draft():
    headers, user = _register("catalog-template-owner@example.com")
    initial_ir = deepcopy(get_process_template(TEMPLATE_SPECS[0].id, "ru")["process_ir"])
    initial_ir["process"]["id"] = "process_catalog_template_test"
    created = request(
        "POST",
        "/api/v1/projects",
        headers=headers,
        json={
            "workspace_id": user["workspaces"][0]["workspace_id"],
            "name": "Черновик из каталога",
            "default_locale": "ru",
            "process_ir": initial_ir,
        },
    ).json()

    applied = request(
        "POST",
        f"/api/v1/projects/{created['id']}/templates/catalog-sales-lead-dedup-sync",
        headers=headers,
        json={"base_revision_id": created["current_revision_id"], "locale": "ru"},
    )

    assert applied.status_code == 201
    process_ir = applied.json()["current_revision"]["process_ir"]
    assert process_ir["process"]["id"] == "process_catalog_template_test"
    assert process_ir["process"]["maturity"] == "draft"
    assert len(process_ir["steps"]) == 2
    assert process_ir["openQuestions"][0]["blocksAutomationReady"] is True
