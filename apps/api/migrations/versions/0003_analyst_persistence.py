"""Add Analyst sessions, messages, and proposed patches.

Revision ID: 0003_analyst_persistence
Revises: 0002_project_persistence
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003_analyst_persistence"
down_revision: str | None = "0002_project_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


json_document = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "analyst_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("started_from_revision_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=35), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('discovery', 'refinement', 'export_preparation')",
            name="ck_analyst_session_mode",
        ),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_analyst_session_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["started_from_revision_id"],
            ["process_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyst_sessions_created_by_user_id", "analyst_sessions", ["created_by_user_id"])
    op.create_index("ix_analyst_sessions_project_id", "analyst_sessions", ["project_id"])

    op.create_table(
        "analyst_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=35), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_analyst_message_role"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["analyst_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyst_messages_created_by_user_id", "analyst_messages", ["created_by_user_id"])
    op.create_index("ix_analyst_messages_session_id", "analyst_messages", ["session_id"])

    op.create_table(
        "proposed_patches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("base_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_id", sa.String(length=36), nullable=True),
        sa.Column("patch", json_document, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("validation_result", json_document, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("accepted_revision_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_proposed_patch_status",
        ),
        sa.ForeignKeyConstraint(["accepted_revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["analyst_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["analyst_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposed_patches_created_by_user_id", "proposed_patches", ["created_by_user_id"])
    op.create_index("ix_proposed_patches_project_id", "proposed_patches", ["project_id"])
    op.create_index("ix_proposed_patches_session_id", "proposed_patches", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_proposed_patches_session_id", table_name="proposed_patches")
    op.drop_index("ix_proposed_patches_project_id", table_name="proposed_patches")
    op.drop_index("ix_proposed_patches_created_by_user_id", table_name="proposed_patches")
    op.drop_table("proposed_patches")
    op.drop_index("ix_analyst_messages_session_id", table_name="analyst_messages")
    op.drop_index("ix_analyst_messages_created_by_user_id", table_name="analyst_messages")
    op.drop_table("analyst_messages")
    op.drop_index("ix_analyst_sessions_project_id", table_name="analyst_sessions")
    op.drop_index("ix_analyst_sessions_created_by_user_id", table_name="analyst_sessions")
    op.drop_table("analyst_sessions")
