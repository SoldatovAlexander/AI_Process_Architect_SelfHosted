"""Add private user template collections.

Revision ID: 0008_user_template_library
Revises: 0007_process_rubric
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008_user_template_library"
down_revision: str | None = "0007_process_rubric"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_favorites", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_template_collection_user_name"),
    )
    op.create_index("ix_template_collections_user_id", "template_collections", ["user_id"])
    op.create_table(
        "user_process_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=35), nullable=False),
        sa.Column("target_mode", sa.String(length=32), nullable=False),
        sa.Column("process_ir", sa.JSON(), nullable=False),
        sa.Column("rubric_entry_ids", sa.JSON(), nullable=False),
        sa.Column("source_project_id", sa.String(length=36), nullable=True),
        sa.Column("source_revision_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["process_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_process_templates_user_id", "user_process_templates", ["user_id"])
    op.create_table(
        "template_collection_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("template_source", sa.String(length=32), nullable=False),
        sa.Column("template_id", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("template_source IN ('catalog', 'user')", name="ck_template_collection_item_source"),
        sa.ForeignKeyConstraint(["collection_id"], ["template_collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "template_source", "template_id", name="uq_template_collection_item"),
    )
    op.create_index("ix_template_collection_items_collection_id", "template_collection_items", ["collection_id"])
    op.create_index("ix_template_collection_items_template_id", "template_collection_items", ["template_id"])


def downgrade() -> None:
    op.drop_table("template_collection_items")
    op.drop_table("user_process_templates")
    op.drop_table("template_collections")
