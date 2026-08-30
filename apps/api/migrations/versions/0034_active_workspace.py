"""Persist the active workspace selected by a user.

Revision ID: 0034_active_workspace
Revises: 0033_llm_cost_ledger
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0034_active_workspace"
down_revision: str | None = "0033_llm_cost_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("active_workspace_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_users_active_workspace",
            "workspaces",
            ["active_workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
    connection = op.get_bind()
    users = connection.execute(sa.text("SELECT id FROM users")).fetchall()
    for (user_id,) in users:
        workspace_id = connection.execute(
            sa.text(
                "SELECT workspace_id FROM memberships "
                "WHERE user_id = :user_id ORDER BY created_at, id LIMIT 1"
            ),
            {"user_id": user_id},
        ).scalar()
        if workspace_id:
            connection.execute(
                sa.text("UPDATE users SET active_workspace_id = :workspace_id WHERE id = :user_id"),
                {"workspace_id": workspace_id, "user_id": user_id},
            )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("fk_users_active_workspace", type_="foreignkey")
        batch.drop_column("active_workspace_id")
