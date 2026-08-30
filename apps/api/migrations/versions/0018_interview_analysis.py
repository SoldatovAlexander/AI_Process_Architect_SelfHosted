"""Add evidence-linked interview analysis.

Revision ID: 0018_interview_analysis
Revises: 0017_interview_review
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0018_interview_analysis"
down_revision: str | None = "0017_interview_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("segments_sha256", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["interview_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("document_id", "segments_sha256", name="uq_interview_analysis_document_hash"),
    )
    op.create_index("ix_interview_analyses_document_id", "interview_analyses", ["document_id"])
    op.create_index("ix_interview_analyses_created_by_user_id", "interview_analyses", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("interview_analyses")
