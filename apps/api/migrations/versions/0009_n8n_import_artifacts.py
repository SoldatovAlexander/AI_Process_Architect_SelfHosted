"""Add immutable n8n import artifacts.

Revision ID: 0009_n8n_import_artifacts
Revises: 0008_user_template_library
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0009_n8n_import_artifacts"
down_revision: str | None = "0008_user_template_library"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "n8n_import_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_minor", sa.String(length=16), nullable=False),
        sa.Column("workflow_name", sa.String(length=200), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_workflow", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["process_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id"),
    )
    op.create_index("ix_n8n_import_artifacts_project_id", "n8n_import_artifacts", ["project_id"])
    op.create_index("ix_n8n_import_artifacts_revision_id", "n8n_import_artifacts", ["revision_id"])
    op.create_index("ix_n8n_import_artifacts_source_sha256", "n8n_import_artifacts", ["source_sha256"])
    op.create_index("ix_n8n_import_artifacts_created_by_user_id", "n8n_import_artifacts", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("n8n_import_artifacts")
