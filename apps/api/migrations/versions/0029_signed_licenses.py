"""Add installation identity and signed workspace licenses.

Revision ID: 0029_signed_licenses
Revises: 0028_workspace_entitlements
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0029_signed_licenses"
down_revision: str | None = "0028_workspace_entitlements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "installation_states",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("deployment_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deployment_id"),
    )
    op.create_index("ix_installation_states_deployment_id", "installation_states", ["deployment_id"])
    op.create_table(
        "workspace_licenses",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("license_id", sa.String(128), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("activation_source", sa.String(16), nullable=False),
        sa.Column("activated_by_user_id", sa.String(36), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'superseded', 'revoked')", name="ck_workspace_license_status"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_id"),
    )
    for column in ("license_id", "workspace_id", "key_id", "status", "activated_by_user_id"):
        op.create_index(f"ix_workspace_licenses_{column}", "workspace_licenses", [column])


def downgrade() -> None:
    op.drop_table("workspace_licenses")
    op.drop_table("installation_states")
