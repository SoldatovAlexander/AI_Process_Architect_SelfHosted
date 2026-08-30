"""Add interview retention and residency policy metadata.

Revision ID: 0022_interview_retention
Revises: 0021_cross_interview_conflicts
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0022_interview_retention"
down_revision: str | None = "0021_cross_interview_conflicts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_documents") as batch:
        batch.drop_constraint("ck_interview_document_status", type_="check")
        batch.create_check_constraint("ck_interview_document_status", "status IN ('draft', 'reviewed', 'purged')")
        batch.add_column(sa.Column("data_residency", sa.String(64), nullable=False, server_default="local"))
        batch.add_column(sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("purge_reason", sa.String(32), nullable=True))
        batch.create_index("ix_interview_documents_retention_until", ["retention_until"])


def downgrade() -> None:
    with op.batch_alter_table("interview_documents") as batch:
        batch.drop_index("ix_interview_documents_retention_until")
        batch.drop_column("purge_reason")
        batch.drop_column("purged_at")
        batch.drop_column("retention_until")
        batch.drop_column("data_residency")
        batch.drop_constraint("ck_interview_document_status", type_="check")
        batch.create_check_constraint("ck_interview_document_status", "status IN ('draft', 'reviewed')")
