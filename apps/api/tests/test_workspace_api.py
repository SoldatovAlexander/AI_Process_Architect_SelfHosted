from test_api import request
from test_projects_api import register_user
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import WorkspaceCommercialState


def test_owner_can_rename_workspace_and_auth_profile_reflects_it():
    headers, user = register_user("workspace-owner@example.com")
    workspace_id = user["workspaces"][0]["workspace_id"]

    renamed = request(
        "PATCH",
        f"/api/v1/workspaces/{workspace_id}",
        headers=headers,
        json={"name": "  Финансы   и контроль  "},
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Финансы и контроль"
    profile = request("GET", "/api/v1/auth/me", headers=headers).json()
    assert profile["workspaces"][0]["workspace_name"] == "Финансы и контроль"


def test_foreign_user_cannot_rename_workspace():
    owner_headers, owner = register_user("workspace-first-owner@example.com")
    foreign_headers, _ = register_user("workspace-foreign-user@example.com")
    workspace_id = owner["workspaces"][0]["workspace_id"]

    response = request(
        "PATCH",
        f"/api/v1/workspaces/{workspace_id}",
        headers=foreign_headers,
        json={"name": "Юристы"},
    )

    assert response.status_code == 404
    unchanged = request("GET", "/api/v1/auth/me", headers=owner_headers).json()
    assert unchanged["workspaces"][0]["workspace_name"] == "Personal workspace"


def test_user_creates_switches_and_scopes_projects_to_workspaces():
    headers, user = register_user("workspace-multiple@example.com")
    personal_id = user["workspaces"][0]["workspace_id"]
    created = request(
        "POST",
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Юристы", "default_locale": "ru"},
    )

    assert created.status_code == 200
    legal_id = created.json()["workspace_id"]
    profile = request("GET", "/api/v1/auth/me", headers=headers).json()
    assert profile["active_workspace_id"] == legal_id
    assert [item["workspace_name"] for item in profile["workspaces"]] == [
        "Personal workspace",
        "Юристы",
    ]

    switched = request(
        "PUT",
        f"/api/v1/workspaces/{personal_id}/active",
        headers=headers,
    )
    assert switched.status_code == 200
    assert request("GET", "/api/v1/auth/me", headers=headers).json()["active_workspace_id"] == personal_id

    assert request("GET", "/api/v1/projects", headers=headers, params={"workspace_id": legal_id}).json() == []


def test_workspace_creation_honors_per_user_limit(monkeypatch):
    monkeypatch.setenv("MAX_WORKSPACES_PER_USER", "1")
    from process_architect_api.config import get_settings
    get_settings.cache_clear()
    headers, _ = register_user("workspace-limit@example.com")

    response = request(
        "POST",
        "/api/v1/workspaces",
        headers=headers,
        json={"name": "Second", "default_locale": "en"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "workspace_limit_reached", "limit": 1}


def test_invitation_membership_transfer_and_last_owner_guards():
    owner_headers, owner = register_user("team-owner@example.com")
    member_headers, member = register_user("team-member@example.com")
    workspace_id = owner["workspaces"][0]["workspace_id"]
    member_id = member["id"]

    invited = request(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": "team-member@example.com", "expires_in_days": 7},
    )
    assert invited.status_code == 200
    token = invited.json()["acceptanceToken"]
    assert token not in str(request(
        "GET",
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
    ).json())

    accepted = request(
        "POST",
        "/api/v1/workspaces/invitations/accept",
        headers=member_headers,
        json={"token": token},
    )
    assert accepted.status_code == 200
    assert accepted.json()["workspace_id"] == workspace_id
    assert accepted.json()["role"] == "member"
    members = request(
        "GET", f"/api/v1/workspaces/{workspace_id}/members", headers=owner_headers
    ).json()
    assert {item["email"]: item["role"] for item in members} == {
        "team-owner@example.com": "owner",
        "team-member@example.com": "member",
    }

    blocked = request(
        "PATCH",
        f"/api/v1/workspaces/{workspace_id}/members/{owner['id']}",
        headers=owner_headers,
        json={"role": "member"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "workspace_last_owner"

    transferred = request(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/ownership-transfer",
        headers=owner_headers,
        json={"target_user_id": member_id},
    )
    assert transferred.status_code == 200
    assert {item["email"]: item["role"] for item in transferred.json()} == {
        "team-member@example.com": "owner",
        "team-owner@example.com": "member",
    }

    removed = request(
        "DELETE",
        f"/api/v1/workspaces/{workspace_id}/members/{owner['id']}",
        headers=member_headers,
    )
    assert removed.status_code == 200
    assert removed.json()["removed"] is True

    last_owner = request(
        "DELETE",
        f"/api/v1/workspaces/{workspace_id}/members/{member_id}",
        headers=member_headers,
    )
    assert last_owner.status_code == 409
    assert last_owner.json()["detail"]["code"] == "workspace_last_owner"


def test_invitation_cannot_be_accepted_by_a_different_email():
    owner_headers, owner = register_user("invite-owner@example.com")
    foreign_headers, _ = register_user("invite-foreign@example.com")
    workspace_id = owner["workspaces"][0]["workspace_id"]
    invited = request(
        "POST",
        f"/api/v1/workspaces/{workspace_id}/invitations",
        headers=owner_headers,
        json={"email": "intended@example.com"},
    ).json()

    response = request(
        "POST",
        "/api/v1/workspaces/invitations/accept",
        headers=foreign_headers,
        json={"token": invited["acceptanceToken"]},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "workspace_invitation_email_mismatch"


def test_workspace_archive_restore_and_scoped_audit_lifecycle():
    headers, user = register_user("archive-owner@example.com")
    first_id = user["workspaces"][0]["workspace_id"]
    second = request(
        "POST", "/api/v1/workspaces", headers=headers,
        json={"name": "Active department", "default_locale": "en"},
    ).json()

    archived = request(
        "POST", f"/api/v1/workspaces/{first_id}/archive", headers=headers
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    profile = request("GET", "/api/v1/auth/me", headers=headers).json()
    assert profile["active_workspace_id"] == second["workspace_id"]
    assert {item["workspace_id"]: item["status"] for item in profile["workspaces"]} == {
        first_id: "archived",
        second["workspace_id"]: "active",
    }

    blocked = request("PUT", f"/api/v1/workspaces/{first_id}/active", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "workspace_archived"
    assert request(
        "GET", "/api/v1/projects", headers=headers, params={"workspace_id": first_id}
    ).json() == []

    audit = request(
        "GET", f"/api/v1/workspaces/{first_id}/audit-events", headers=headers
    )
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "workspace.archived"
    assert {event["action"] for event in audit.json()} >= {"workspace.archived"}

    restored = request(
        "POST", f"/api/v1/workspaces/{first_id}/restore", headers=headers
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert request("PUT", f"/api/v1/workspaces/{first_id}/active", headers=headers).status_code == 200


def test_workspace_audit_is_tenant_scoped_and_owner_only():
    first_headers, first = register_user("audit-first@example.com")
    second_headers, second = register_user("audit-second@example.com")
    first_id = first["workspaces"][0]["workspace_id"]
    second_id = second["workspaces"][0]["workspace_id"]

    own = request("GET", f"/api/v1/workspaces/{first_id}/audit-events", headers=first_headers)
    foreign = request("GET", f"/api/v1/workspaces/{second_id}/audit-events", headers=first_headers)

    assert own.status_code == 200
    assert all(event["targetId"] != second_id for event in own.json())
    assert foreign.status_code == 404


def test_archived_workspace_does_not_consume_active_workspace_limit(monkeypatch):
    monkeypatch.setenv("MAX_WORKSPACES_PER_USER", "1")
    from process_architect_api.config import get_settings
    get_settings.cache_clear()
    headers, user = register_user("archive-limit@example.com")
    workspace_id = user["workspaces"][0]["workspace_id"]

    assert request(
        "POST", f"/api/v1/workspaces/{workspace_id}/archive", headers=headers
    ).status_code == 200
    replacement = request(
        "POST", "/api/v1/workspaces", headers=headers,
        json={"name": "Replacement", "default_locale": "ru"},
    )
    assert replacement.status_code == 200

    blocked_restore = request(
        "POST", f"/api/v1/workspaces/{workspace_id}/restore", headers=headers
    )
    assert blocked_restore.status_code == 409
    assert blocked_restore.json()["detail"] == {
        "code": "workspace_restore_member_limit",
        "limit": 1,
        "blockedMembers": 1,
    }


def test_workspace_member_entitlement_limits_pending_invitations():
    headers, user = register_user("member-limit-owner@example.com")
    workspace_id = user["workspaces"][0]["workspace_id"]
    with get_session_factory()() as db:
        state = db.get(WorkspaceCommercialState, workspace_id)
        assert state is not None
        state.entitlement_overrides = {"workspace.max_members": 1}
        db.commit()

    response = request(
        "POST", f"/api/v1/workspaces/{workspace_id}/invitations", headers=headers,
        json={"email": "member-limit-invitee@example.com"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "workspace_member_limit_reached",
        "limit": 1,
    }
