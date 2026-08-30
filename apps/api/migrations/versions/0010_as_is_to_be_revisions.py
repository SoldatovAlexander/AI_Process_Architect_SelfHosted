"""Distinguish AS-IS and TO-BE revisions.

Revision ID: 0010_as_is_to_be_revisions
Revises: 0009_n8n_import_artifacts
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0010_as_is_to_be_revisions"
down_revision: str | None = "0009_n8n_import_artifacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("process_revisions") as batch:
        batch.add_column(sa.Column("perspective", sa.String(length=16), nullable=False, server_default="to_be"))
        batch.create_check_constraint("ck_revision_perspective", "perspective IN ('as_is', 'to_be')")
    op.execute("UPDATE process_revisions SET perspective = 'as_is' WHERE source = 'import'")
    with op.batch_alter_table("analyst_sessions") as batch:
        batch.drop_constraint("ck_analyst_session_mode", type_="check")
        batch.create_check_constraint(
            "ck_analyst_session_mode",
            "mode IN ('discovery', 'refinement', 'export_preparation', 'as_is_completion')",
        )


def downgrade() -> None:
    with op.batch_alter_table("analyst_sessions") as batch:
        batch.drop_constraint("ck_analyst_session_mode", type_="check")
        batch.create_check_constraint(
            "ck_analyst_session_mode",
            "mode IN ('discovery', 'refinement', 'export_preparation')",
        )
    with op.batch_alter_table("process_revisions") as batch:
        batch.drop_constraint("ck_revision_perspective", type_="check")
        batch.drop_column("perspective")
