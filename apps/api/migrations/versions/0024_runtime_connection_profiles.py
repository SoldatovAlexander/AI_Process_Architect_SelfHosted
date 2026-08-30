"""Add workspace runtime connection profiles.

Revision ID: 0024_runtime_connection_profiles
Revises: 0023_interview_document_sources
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0024_runtime_connection_profiles"
down_revision: str | None = "0023_interview_document_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_connection_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("endpoint_url", sa.String(2_000), nullable=False),
        sa.Column("secret_ref", sa.String(255), nullable=False),
        sa.Column("n8n_minor", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('n8n', 'openclaw', 'hermes')", name="ck_runtime_profile_kind"),
        sa.Column("detected_version", sa.String(64), nullable=True),
        sa.Column("last_check_code", sa.String(64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'verified', 'failed', 'disabled')", name="ck_runtime_profile_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_runtime_profile_workspace_name"),
    )
    op.create_index("ix_runtime_connection_profiles_workspace_id", "runtime_connection_profiles", ["workspace_id"])
    op.create_index("ix_runtime_connection_profiles_kind", "runtime_connection_profiles", ["kind"])
    op.create_index("ix_runtime_connection_profiles_status", "runtime_connection_profiles", ["status"])
    op.create_index("ix_runtime_connection_profiles_created_by_user_id", "runtime_connection_profiles", ["created_by_user_id"])
    op.create_table(
        "runtime_connection_checks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_code", sa.String(64), nullable=False),
        sa.Column("detected_version", sa.String(64), nullable=True),
        sa.Column("checked_by_user_id", sa.String(36), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('verified', 'failed')", name="ck_runtime_connection_check_status"),
        sa.ForeignKeyConstraint(["checked_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["runtime_connection_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_connection_checks_profile_id", "runtime_connection_checks", ["profile_id"])
    op.create_index("ix_runtime_connection_checks_status", "runtime_connection_checks", ["status"])
    op.create_index("ix_runtime_connection_checks_checked_by_user_id", "runtime_connection_checks", ["checked_by_user_id"])


def downgrade() -> None:
    op.drop_table("runtime_connection_checks")
    op.drop_table("runtime_connection_profiles")
