"""Add workspace archive state and scoped audit events.

Revision ID: 0036_workspace_lifecycle
Revises: 0035_workspace_invitations
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0036_workspace_lifecycle"
down_revision: str | None = "0035_workspace_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("archived_by_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_workspaces_archived_by_user_id_users",
            "users",
            ["archived_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_index("ix_workspaces_archived_at", ["archived_at"])
        batch.create_index("ix_workspaces_archived_by_user_id", ["archived_by_user_id"])
    with op.batch_alter_table("admin_audit_events") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_admin_audit_events_workspace_id_workspaces",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_admin_audit_events_workspace_id", ["workspace_id"])
    op.execute(
        "UPDATE admin_audit_events SET workspace_id = target_id "
        "WHERE target_type = 'workspace' AND target_id IN (SELECT id FROM workspaces)"
    )


def downgrade() -> None:
    with op.batch_alter_table("admin_audit_events") as batch:
        batch.drop_index("ix_admin_audit_events_workspace_id")
        batch.drop_constraint("fk_admin_audit_events_workspace_id_workspaces", type_="foreignkey")
        batch.drop_column("workspace_id")
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_index("ix_workspaces_archived_by_user_id")
        batch.drop_index("ix_workspaces_archived_at")
        batch.drop_constraint("fk_workspaces_archived_by_user_id_users", type_="foreignkey")
        batch.drop_column("archived_by_user_id")
        batch.drop_column("archived_at")
