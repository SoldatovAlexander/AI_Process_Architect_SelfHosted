"""Add reviewed text interview sources.

Revision ID: 0016_interview_transcripts
Revises: 0015_agent_incidents
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0016_interview_transcripts"
down_revision: str | None = "0015_agent_incidents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("language", sa.String(35), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_format IN ('plain', 'txt', 'md', 'srt', 'vtt')", name="ck_interview_document_format"),
        sa.CheckConstraint("status IN ('draft', 'reviewed')", name="ck_interview_document_status"),
        sa.ForeignKeyConstraint(["session_id"], ["analyst_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "content_sha256", name="uq_interview_document_session_hash"),
    )
    op.create_index("ix_interview_documents_session_id", "interview_documents", ["session_id"])
    op.create_index("ix_interview_documents_created_by_user_id", "interview_documents", ["created_by_user_id"])
    op.create_table(
        "interview_segments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(160)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer()),
        sa.Column("end_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["interview_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_interview_segment_ordinal"),
    )
    op.create_index("ix_interview_segments_document_id", "interview_segments", ["document_id"])


def downgrade() -> None:
    op.drop_table("interview_segments")
    op.drop_table("interview_documents")
