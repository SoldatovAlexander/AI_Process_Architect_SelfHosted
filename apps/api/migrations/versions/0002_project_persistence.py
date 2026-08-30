"""Add workspaces, projects, and immutable process revisions.

Revision ID: 0002_project_persistence
Revises: 0001_auth
"""
from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql


revision: str = "0002_project_persistence"
down_revision: str | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_document = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "preferred_locale",
                sa.String(length=35),
                nullable=False,
                server_default="ru",
            )
        )
        batch.drop_column("role")

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("default_locale", sa.String(length=35), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_created_by_user_id", "workspaces", ["created_by_user_id"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_membership_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_membership_workspace_user"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_index("ix_memberships_workspace_id", "memberships", ["workspace_id"])

    if not context.is_offline_mode():
        connection = op.get_bind()
        existing_users = connection.execute(
            sa.text("SELECT id, preferred_locale FROM users")
        ).mappings()
        now = datetime.now(timezone.utc)
        for user in existing_users:
            workspace_id = str(uuid4())
            connection.execute(
                sa.text(
                    "INSERT INTO workspaces "
                    "(id, name, default_locale, created_by_user_id, created_at) "
                    "VALUES (:id, :name, :locale, :user_id, :created_at)"
                ),
                {
                    "id": workspace_id,
                    "name": "Personal workspace",
                    "locale": user["preferred_locale"],
                    "user_id": user["id"],
                    "created_at": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO memberships "
                    "(id, workspace_id, user_id, role, created_at) "
                    "VALUES (:id, :workspace_id, :user_id, :role, :created_at)"
                ),
                {
                    "id": str(uuid4()),
                    "workspace_id": workspace_id,
                    "user_id": user["id"],
                    "role": "owner",
                    "created_at": now,
                },
            )

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("default_locale", sa.String(length=35), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_project_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_created_by_user_id", "projects", ["created_by_user_id"])
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    op.create_table(
        "process_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("process_ir", json_document, nullable=False),
        sa.Column("forward_patch", json_document, nullable=True),
        sa.Column("inverse_patch", json_document, nullable=True),
        sa.Column("validation_result", json_document, nullable=False),
        sa.Column("parent_revision_id", sa.String(length=36), nullable=True),
        sa.Column("restored_from_revision_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('initial', 'user', 'analyst', 'import', 'undo', 'restore')",
            name="ck_revision_source",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["restored_from_revision_id"],
            ["process_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "version_number", name="uq_revision_project_version"),
    )
    op.create_index(
        "ix_process_revisions_created_by_user_id",
        "process_revisions",
        ["created_by_user_id"],
    )
    op.create_index("ix_process_revisions_project_id", "process_revisions", ["project_id"])

    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("current_revision_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_projects_current_revision_id",
            "process_revisions",
            ["current_revision_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("fk_projects_current_revision_id", type_="foreignkey")
        batch.drop_column("current_revision_id")

    op.drop_index("ix_process_revisions_project_id", table_name="process_revisions")
    op.drop_index("ix_process_revisions_created_by_user_id", table_name="process_revisions")
    op.drop_table("process_revisions")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_index("ix_projects_created_by_user_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_memberships_workspace_id", table_name="memberships")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("ix_workspaces_created_by_user_id", table_name="workspaces")
    op.drop_table("workspaces")

    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("role", sa.String(length=32), nullable=False, server_default="owner")
        )
        batch.drop_column("preferred_locale")
