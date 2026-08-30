"""Add service administration roles and immutable audit events.

Revision ID: 0030_admin_rbac_audit
Revises: 0029_signed_licenses
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0030_admin_rbac_audit"
down_revision: str | None = "0029_signed_licenses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("service_role", sa.String(32), nullable=False, server_default="user"))
        batch.create_check_constraint(
            "ck_user_service_role",
            "service_role IN ('user', 'service_admin', 'support', 'billing_admin', 'viewer')",
        )
        batch.create_index("ix_users_service_role", ["service_role"])
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(96), nullable=False),
        sa.Column("target_type", sa.String(48), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_user_id", "action", "target_type", "target_id", "created_at"):
        op.create_index(f"ix_admin_audit_events_{column}", "admin_audit_events", [column])


def downgrade() -> None:
    op.drop_table("admin_audit_events")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_service_role")
        batch.drop_constraint("ck_user_service_role", type_="check")
        batch.drop_column("service_role")
