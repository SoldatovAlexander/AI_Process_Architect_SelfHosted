import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects.postgresql import JSONB


ROOT = Path(__file__).resolve().parents[4]
DATABASE_URL = os.getenv("POSTGRES_TEST_URL")


@pytest.mark.integration
@pytest.mark.skipif(not DATABASE_URL, reason="POSTGRES_TEST_URL is not configured")
def test_alembic_head_on_postgresql():
    environment = os.environ.copy()
    environment["DATABASE_URL"] = DATABASE_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "apps/api/alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    assert {
        "users",
        "workspaces",
        "projects",
        "process_revisions",
        "analyst_sessions",
        "analyst_messages",
        "proposed_patches",
    } <= set(inspector.get_table_names())
    process_ir = next(
        column for column in inspector.get_columns("process_revisions") if column["name"] == "process_ir"
    )
    assert isinstance(process_ir["type"], JSONB)
    engine.dispose()
