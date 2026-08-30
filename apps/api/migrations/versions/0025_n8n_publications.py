"""Add revision-bound inactive n8n publications.

Revision ID: 0025_n8n_publications
Revises: 0024_runtime_connection_profiles
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0025_n8n_publications"
down_revision: str | None = "0024_runtime_connection_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "n8n_publications",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("workflow_sha256", sa.String(64), nullable=False),
        sa.Column("remote_workflow_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('publishing', 'published', 'failed', 'deleted', 'deletion_failed')", name="ck_n8n_publication_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["runtime_connection_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "idempotency_key", name="uq_n8n_publication_profile_idempotency"),
    )
    op.create_index("ix_n8n_publications_project_id", "n8n_publications", ["project_id"])
    op.create_index("ix_n8n_publications_revision_id", "n8n_publications", ["revision_id"])
    op.create_index("ix_n8n_publications_profile_id", "n8n_publications", ["profile_id"])
    op.create_index("ix_n8n_publications_workflow_sha256", "n8n_publications", ["workflow_sha256"])
    op.create_index("ix_n8n_publications_status", "n8n_publications", ["status"])
    op.create_index("ix_n8n_publications_created_by_user_id", "n8n_publications", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("n8n_publications")
