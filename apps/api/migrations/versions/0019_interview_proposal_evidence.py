"""Link interview evidence to Process IR proposals.

Revision ID: 0019_interview_proposal_evidence
Revises: 0018_interview_analysis
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0019_interview_proposal_evidence"
down_revision: str | None = "0018_interview_analysis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "interview_proposal_evidence",
        sa.Column("proposal_id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), nullable=False),
        sa.Column("segments_sha256", sa.String(64), nullable=False),
        sa.Column("selected_fact_indices", sa.JSON(), nullable=False),
        sa.Column("segment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposed_patches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_id"], ["interview_analyses.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_interview_proposal_evidence_analysis_id", "interview_proposal_evidence", ["analysis_id"])


def downgrade() -> None:
    op.drop_table("interview_proposal_evidence")
