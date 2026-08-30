from process_architect_api.auth import hash_password
from process_architect_api.database import get_session_factory
from process_architect_api.db_models import RefreshSession, User, Workspace
from process_architect_api.services.e2e_cleanup import apply_e2e_cleanup, preview_e2e_cleanup


def test_cleanup_archives_only_marked_e2e_data():
    with get_session_factory()() as db:
        test_user = User(email="playwright-cleanup@example.com", password_hash=hash_password("password"))
        regular_user = User(email="customer@example.com", password_hash=hash_password("password"))
        db.add_all([test_user, regular_user])
        db.flush()
        test_workspace = Workspace(name="E2E workspace", created_by_user_id=test_user.id)
        regular_workspace = Workspace(name="Customer workspace", created_by_user_id=regular_user.id)
        db.add_all([test_workspace, regular_workspace, RefreshSession(user_id=test_user.id, token_hash="e2e-cleanup-token", expires_at=test_user.created_at)])
        db.commit()

        assert preview_e2e_cleanup(db)["matched_users"] == 1
        result = apply_e2e_cleanup(db)
        assert result["disabled_users"] == 1
        assert result["archived_workspaces"] == 1
        assert result["revoked_sessions"] == 1

        db.refresh(test_user); db.refresh(regular_user)
        db.refresh(test_workspace); db.refresh(regular_workspace)
        assert test_user.is_active is False
        assert regular_user.is_active is True
        assert test_workspace.archived_at is not None
        assert regular_workspace.archived_at is None
