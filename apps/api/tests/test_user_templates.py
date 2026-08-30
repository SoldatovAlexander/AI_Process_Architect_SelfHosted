from copy import deepcopy

from process_architect_api.process_templates import get_process_template
from test_api import authorization, request


def _register(email: str) -> tuple[dict, dict]:
    tokens = request("POST", "/api/v1/auth/register", json={"email": email, "password": "correct-horse-battery-staple"}).json()
    headers = authorization(tokens)
    return headers, request("GET", "/api/v1/auth/me", headers=headers).json()


def test_user_can_collect_catalog_items_and_save_immutable_project_template():
    headers, user = _register("personal-library@example.com")
    process_ir = deepcopy(get_process_template("lead-qualification", "ru")["process_ir"])
    project = request("POST", "/api/v1/projects", headers=headers, json={
        "workspace_id": user["workspaces"][0]["workspace_id"],
        "name": "Мой процесс продаж",
        "default_locale": "ru",
        "process_ir": process_ir,
    }).json()

    collections = request("GET", "/api/v1/template-collections", headers=headers)
    assert collections.status_code == 200
    favorites = next(item for item in collections.json() if item["is_favorites"])

    sales = request("POST", "/api/v1/template-collections", headers=headers, json={"name": "Лучшие продажи"})
    assert sales.status_code == 201
    sales_id = sales.json()["id"]

    added = request("POST", f"/api/v1/template-collections/{favorites['id']}/items", headers=headers, json={
        "template_source": "catalog", "template_id": "lead-qualification",
    })
    assert added.status_code == 204

    saved = request("POST", f"/api/v1/projects/{project['id']}/user-templates", headers=headers, json={
        "name": "Квалификация для нашей компании",
        "description": "Проверенный внутренний вариант",
        "collection_ids": [sales_id],
        "favorite": True,
    })
    assert saved.status_code == 201
    template = saved.json()
    assert template["source"] == "user"
    assert template["favorite"] is True
    assert sales_id in template["collection_ids"]
    assert template["process_ir"] == process_ir

    changed_ir = deepcopy(process_ir)
    changed_ir["process"]["name"] = "Измененное имя"
    changed = request("POST", f"/api/v1/projects/{project['id']}/revisions", headers=headers, json={
        "base_revision_id": project["current_revision_id"],
        "patch": [{"op": "replace", "path": "/process/name", "value": "Измененное имя"}],
    })
    assert changed.status_code == 201
    personal = request("GET", "/api/v1/user-templates", headers=headers).json()
    assert personal[0]["process_ir"]["process"]["name"] != changed_ir["process"]["name"]

    deleted_collection = request("DELETE", f"/api/v1/template-collections/{sales_id}", headers=headers)
    assert deleted_collection.status_code == 204
    assert request("GET", "/api/v1/user-templates", headers=headers).json()[0]["id"] == template["id"]

    other_headers, _ = _register("other-personal-library@example.com")
    assert request("GET", "/api/v1/user-templates", headers=other_headers).json() == []
    denied = request("DELETE", f"/api/v1/user-templates/{template['id']}", headers=other_headers)
    assert denied.status_code == 404


def test_collection_rejects_duplicate_names_and_unknown_templates():
    headers, _ = _register("personal-library-validation@example.com")
    first = request("POST", "/api/v1/template-collections", headers=headers, json={"name": "Операции"})
    assert first.status_code == 201
    duplicate = request("POST", "/api/v1/template-collections", headers=headers, json={"name": "операции"})
    assert duplicate.status_code == 409
    unknown = request("POST", f"/api/v1/template-collections/{first.json()['id']}/items", headers=headers, json={
        "template_source": "catalog", "template_id": "does-not-exist",
    })
    assert unknown.status_code == 404

    favorites = next(item for item in request("GET", "/api/v1/template-collections", headers=headers).json() if item["is_favorites"])
    reserved = request("POST", "/api/v1/template-collections", headers=headers, json={"name": "favorites"})
    assert reserved.status_code == 409
    cannot_delete = request("DELETE", f"/api/v1/template-collections/{favorites['id']}", headers=headers)
    assert cannot_delete.status_code == 409
