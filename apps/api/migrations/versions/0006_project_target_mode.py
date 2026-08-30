"""Add process or agent project target.

Revision ID: 0006_project_target_mode
Revises: 0005_template_revision_source
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0006_project_target_mode"
down_revision: str | None = "0005_template_revision_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("target_mode", sa.String(length=32), nullable=False, server_default="process"))
        batch.create_check_constraint("ck_project_target_mode", "target_mode IN ('process', 'agent')")


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("ck_project_target_mode", type_="check")
        batch.drop_column("target_mode")
