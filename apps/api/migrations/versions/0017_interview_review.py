"""Add transcript review concurrency metadata.

Revision ID: 0017_interview_review
Revises: 0016_interview_transcripts
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0017_interview_review"
down_revision: str | None = "0016_interview_transcripts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_documents") as batch:
        batch.add_column(sa.Column("segments_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("reviewed_by_user_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key("fk_interview_documents_reviewed_by", "users", ["reviewed_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_interview_documents_reviewed_by_user_id", "interview_documents", ["reviewed_by_user_id"])

    connection = op.get_bind()
    documents = connection.execute(sa.text("SELECT id FROM interview_documents")).fetchall()
    for document in documents:
        segments = connection.execute(sa.text("SELECT ordinal, speaker, text, start_ms, end_ms FROM interview_segments WHERE document_id = :id ORDER BY ordinal"), {"id": document.id}).mappings().all()
        import hashlib
        import json
        digest = hashlib.sha256(json.dumps([dict(item) for item in segments], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        connection.execute(sa.text("UPDATE interview_documents SET segments_sha256 = :digest WHERE id = :id"), {"digest": digest, "id": document.id})
    with op.batch_alter_table("interview_documents") as batch:
        batch.alter_column("segments_sha256", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_interview_documents_reviewed_by_user_id", table_name="interview_documents")
    with op.batch_alter_table("interview_documents") as batch:
        batch.drop_constraint("fk_interview_documents_reviewed_by", type_="foreignkey")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by_user_id")
        batch.drop_column("segments_sha256")
