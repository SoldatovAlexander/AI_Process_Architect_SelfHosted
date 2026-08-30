"""Track portable project archive restores.

Revision ID: 0011_project_archive_restores
Revises: 0010_as_is_to_be_revisions
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0011_project_archive_restores"
down_revision: str | None = "0010_as_is_to_be_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_archive_restores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("archive_sha256", sa.String(length=64), nullable=False),
        sa.Column("source_project_id", sa.String(length=36), nullable=False),
        sa.Column("restored_project_id", sa.String(length=36), nullable=False),
        sa.Column("restored_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["restored_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["restored_project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_archive_restores_archive_sha256", "project_archive_restores", ["archive_sha256"], unique=True)
    op.create_index("ix_project_archive_restores_source_project_id", "project_archive_restores", ["source_project_id"])
    op.create_index("ix_project_archive_restores_restored_project_id", "project_archive_restores", ["restored_project_id"])
    op.create_index("ix_project_archive_restores_restored_by_user_id", "project_archive_restores", ["restored_by_user_id"])


def downgrade() -> None:
    op.drop_table("project_archive_restores")
