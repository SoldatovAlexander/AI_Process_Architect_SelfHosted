import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_CONFIG = ROOT / "apps" / "api" / "alembic.ini"


def test_revision_ids_fit_alembic_version_column():
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "migrations"))
    revisions = ScriptDirectory.from_config(config).walk_revisions()

    assert all(len(revision.revision) <= 32 for revision in revisions)


def run_alembic(database_url: str, revision: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_CONFIG), "upgrade", revision],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_backfills_personal_workspace_for_existing_users(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    run_alembic(database_url, "0001_auth")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, email, password_hash, role, is_active, created_at) "
                "VALUES (:id, :email, :password_hash, :role, :is_active, CURRENT_TIMESTAMP)"
            ),
            {
                "id": "existing-user",
                "email": "existing@example.com",
                "password_hash": "not-used-by-this-test",
                "role": "owner",
                "is_active": True,
            },
        )

    run_alembic(database_url, "head")
    with engine.connect() as connection:
        user = connection.execute(
            text("SELECT preferred_locale FROM users WHERE id = 'existing-user'")
        ).one()
        membership = connection.execute(
            text(
                "SELECT m.role, w.default_locale "
                "FROM memberships m JOIN workspaces w ON w.id = m.workspace_id "
                "WHERE m.user_id = 'existing-user'"
            )
        ).one()
        analyst_tables = {
            row.name
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name IN "
                    "('analyst_sessions', 'analyst_messages', 'proposed_patches')"
                )
            )
        }
        rubric_tables = {
            row.name
            for row in connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN "
                    "('rubric_versions', 'rubric_entries', 'rubric_entry_translations')"
                )
            )
        }
        entitlement_table = connection.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'workspace_commercial_states'"
            )
        ).scalar_one()
        license_tables = {
            row.name for row in connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('installation_states', 'workspace_licenses')"
            ))
        }
        admin_tables = {
            row.name for row in connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'admin_audit_events'"
            ))
        }
        billing_tables = {
            row.name for row in connection.execute(text(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name IN ('billing_subscriptions', 'billing_events', "
                "'billing_usage_reservations', 'billing_usage_events', "
                "'billing_invoices', 'billing_invoice_snapshots')"
            ))
        }
        llm_usage_table = connection.execute(text(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'llm_usage_records'"
        )).scalar_one()
        service_role = connection.execute(text(
            "SELECT service_role FROM users WHERE id = 'existing-user'"
        )).scalar_one()

    assert user.preferred_locale == "ru"
    assert membership.role == "owner"
    assert membership.default_locale == "ru"
    assert analyst_tables == {"analyst_sessions", "analyst_messages", "proposed_patches"}
    assert rubric_tables == {"rubric_versions", "rubric_entries", "rubric_entry_translations"}
    assert entitlement_table == "workspace_commercial_states"
    assert license_tables == {"installation_states", "workspace_licenses"}
    assert admin_tables == {"admin_audit_events"}
    assert billing_tables == {
        "billing_subscriptions", "billing_events", "billing_usage_reservations", "billing_usage_events",
        "billing_invoices", "billing_invoice_snapshots"
    }
    assert llm_usage_table == "llm_usage_records"
    assert service_role == "user"
    engine.dispose()
