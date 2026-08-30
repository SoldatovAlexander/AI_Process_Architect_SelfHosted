"""Add workspace commercial entitlement state.

Revision ID: 0028_workspace_entitlements
Revises: 0027_user_llm_credentials
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0028_workspace_entitlements"
down_revision: str | None = "0027_user_llm_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_commercial_states",
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("catalog_version", sa.String(32), nullable=False),
        sa.Column("entitlement_overrides", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('trial', 'active', 'grace', 'read_only', 'expired', 'revoked')",
            name="ck_workspace_commercial_state_status",
        ),
        sa.CheckConstraint(
            "source IN ('deployment', 'subscription', 'license', 'manual')",
            name="ck_workspace_commercial_state_source",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index("ix_workspace_commercial_states_plan_id", "workspace_commercial_states", ["plan_id"])
    op.create_index("ix_workspace_commercial_states_status", "workspace_commercial_states", ["status"])
    op.create_index("ix_workspace_commercial_states_source", "workspace_commercial_states", ["source"])


def downgrade() -> None:
    op.drop_table("workspace_commercial_states")
