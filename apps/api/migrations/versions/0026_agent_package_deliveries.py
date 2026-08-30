"""Add revision-bound inactive agent package deliveries.

Revision ID: 0026_agent_package_deliveries
Revises: 0025_n8n_publications
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0026_agent_package_deliveries"
down_revision: str | None = "0025_n8n_publications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_package_deliveries",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("package_size", sa.Integer(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("remote_package_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_package_delivery_runtime"),
        sa.CheckConstraint("status IN ('storing', 'stored', 'failed', 'deleted', 'deletion_failed')", name="ck_agent_package_delivery_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["runtime_connection_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "idempotency_key", name="uq_agent_package_delivery_profile_idempotency"),
    )
    for column in ("project_id", "revision_id", "profile_id", "runtime", "package_sha256", "status", "created_by_user_id"):
        op.create_index(f"ix_agent_package_deliveries_{column}", "agent_package_deliveries", [column])


def downgrade() -> None:
    op.drop_table("agent_package_deliveries")
