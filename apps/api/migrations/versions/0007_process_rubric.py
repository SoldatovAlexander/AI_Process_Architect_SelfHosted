"""Add versioned process rubric tables.

Revision ID: 0007_process_rubric
Revises: 0006_project_target_mode
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0007_process_rubric"
down_revision: str | None = "0006_project_target_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rubric_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rubric_entries",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("version_id", sa.String(length=64), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("parent_id", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("deprecated", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["rubric_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["version_id"], ["rubric_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "dimension", "code", name="uq_rubric_entry_version_dimension_code"),
    )
    op.create_index("ix_rubric_entries_version_id", "rubric_entries", ["version_id"])
    op.create_index("ix_rubric_entries_dimension", "rubric_entries", ["dimension"])
    op.create_table(
        "rubric_entry_translations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entry_id", sa.String(length=128), nullable=False),
        sa.Column("locale", sa.String(length=35), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("synonyms", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["rubric_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", "locale", name="uq_rubric_translation_entry_locale"),
    )
    op.create_index("ix_rubric_entry_translations_entry_id", "rubric_entry_translations", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_rubric_entry_translations_entry_id", table_name="rubric_entry_translations")
    op.drop_table("rubric_entry_translations")
    op.drop_index("ix_rubric_entries_dimension", table_name="rubric_entries")
    op.drop_index("ix_rubric_entries_version_id", table_name="rubric_entries")
    op.drop_table("rubric_entries")
    op.drop_table("rubric_versions")
