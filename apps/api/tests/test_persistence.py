import json
from pathlib import Path

import pytest

from process_architect_api.database import get_session_factory
from process_architect_api.db_models import ImmutableRevisionError, ProcessRevision, User
from process_architect_api.services.projects import create_project_with_initial_revision
from process_architect_api.services.workspaces import WorkspaceAccessDenied
from test_api import authorization, register, request


ROOT = Path(__file__).resolve().parents[3]
LEAD = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def current_user() -> dict:
    tokens = register()
    response = request("GET", "/api/v1/auth/me", headers=authorization(tokens))
    assert response.status_code == 200
    return response.json()


def test_creates_project_with_immutable_initial_revision():
    user_data = current_user()
    workspace_id = user_data["workspaces"][0]["workspace_id"]

    with get_session_factory()() as db:
        user = db.get(User, user_data["id"])
        project, revision = create_project_with_initial_revision(
            db,
            user=user,
            workspace_id=workspace_id,
            name="Lead automation",
            process_ir=LEAD,
        )

        assert project.current_revision_id == revision.id
        assert project.default_locale == "ru"
        assert revision.version_number == 1
        assert revision.parent_revision_id is None
        assert revision.forward_patch is None
        assert revision.inverse_patch is None
        assert revision.process_ir["process"]["id"] == "process_lead_intake"
        assert revision.validation_result["valid"] is True

        revision.source = "user"
        with pytest.raises(ImmutableRevisionError):
            db.commit()
        db.rollback()

        persisted = db.get(ProcessRevision, revision.id)
        db.delete(persisted)
        with pytest.raises(ImmutableRevisionError):
            db.commit()
        db.rollback()


def test_denies_project_creation_in_another_users_workspace():
    owner = current_user()
    workspace_id = owner["workspaces"][0]["workspace_id"]
    second = request(
        "POST",
        "/api/v1/auth/register",
        json={"email": "member@example.com", "password": "another-secure-password"},
    )
    second_me = request("GET", "/api/v1/auth/me", headers=authorization(second.json())).json()

    with get_session_factory()() as db:
        other_user = db.get(User, second_me["id"])
        with pytest.raises(WorkspaceAccessDenied):
            create_project_with_initial_revision(
                db,
                user=other_user,
                workspace_id=workspace_id,
                name="Forbidden project",
                process_ir=LEAD,
            )
