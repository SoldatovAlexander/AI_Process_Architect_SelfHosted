"""Add Analyst prompt version metadata.

Revision ID: 0004_analyst_prompt_version
Revises: 0003_analyst_persistence
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004_analyst_prompt_version"
down_revision: str | None = "0003_analyst_persistence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("analyst_messages") as batch:
        batch.add_column(sa.Column("prompt_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analyst_messages") as batch:
        batch.drop_column("prompt_version")
