"""Add reviewable semantic conflicts across interviews.

Revision ID: 0021_cross_interview_conflicts
Revises: 0020_multi_interview_evidence
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0021_cross_interview_conflicts"
down_revision: str | None = "0020_multi_interview_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_interview_conflict_scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["analyst_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "evidence_sha256", name="uq_cross_interview_conflict_scan"),
    )
    op.create_index("ix_cross_interview_conflict_scans_session_id", "cross_interview_conflict_scans", ["session_id"])
    op.create_index("ix_cross_interview_conflict_scans_evidence_sha256", "cross_interview_conflict_scans", ["evidence_sha256"])
    op.create_index("ix_cross_interview_conflict_scans_created_by_user_id", "cross_interview_conflict_scans", ["created_by_user_id"])
    op.create_table(
        "cross_interview_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("fact_references", sa.JSON(), nullable=False),
        sa.Column("segment_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["analyst_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("session_id", "evidence_sha256", "fingerprint", name="uq_cross_interview_conflict_evidence"),
        sa.CheckConstraint("status IN ('pending', 'confirmed', 'dismissed')", name="ck_cross_interview_conflict_status"),
    )
    op.create_index("ix_cross_interview_conflicts_session_id", "cross_interview_conflicts", ["session_id"])
    op.create_index("ix_cross_interview_conflicts_evidence_sha256", "cross_interview_conflicts", ["evidence_sha256"])
    op.create_index("ix_cross_interview_conflicts_created_by_user_id", "cross_interview_conflicts", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_table("cross_interview_conflicts")
    op.drop_table("cross_interview_conflict_scans")
