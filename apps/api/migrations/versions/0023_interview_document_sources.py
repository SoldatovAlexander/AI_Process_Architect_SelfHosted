"""Add office files and linked documents as interview sources.

Revision ID: 0023_interview_document_sources
Revises: 0022_interview_retention
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0023_interview_document_sources"
down_revision: str | None = "0022_interview_retention"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_documents") as batch:
        batch.drop_constraint("ck_interview_document_format", type_="check")
        batch.create_check_constraint("ck_interview_document_format", "source_format IN ('plain', 'txt', 'md', 'srt', 'vtt', 'docx', 'odt', 'google_docs', 'yandex_docs')")
        batch.add_column(sa.Column("source_url", sa.String(2_000), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("interview_documents") as batch:
        batch.drop_column("source_url")
        batch.drop_constraint("ck_interview_document_format", type_="check")
        batch.create_check_constraint("ck_interview_document_format", "source_format IN ('plain', 'txt', 'md', 'srt', 'vtt')")
