"""Store multiple interview evidence sources per proposal.

Revision ID: 0020_multi_interview_evidence
Revises: 0019_interview_proposal_evidence
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0020_multi_interview_evidence"
down_revision: str | None = "0019_interview_proposal_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_proposal_evidence_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proposal_id", sa.String(36), nullable=False),
        sa.Column("analysis_id", sa.String(36), nullable=False),
        sa.Column("segments_sha256", sa.String(64), nullable=False),
        sa.Column("selected_fact_indices", sa.JSON(), nullable=False),
        sa.Column("segment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposed_patches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_id"], ["interview_analyses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("proposal_id", "analysis_id", name="uq_interview_proposal_evidence_source"),
    )
    op.create_index("ix_interview_proposal_evidence_sources_proposal_id", "interview_proposal_evidence_sources", ["proposal_id"])
    op.create_index("ix_interview_proposal_evidence_sources_analysis_id", "interview_proposal_evidence_sources", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("interview_proposal_evidence_sources")
