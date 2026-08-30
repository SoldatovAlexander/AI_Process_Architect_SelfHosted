"""Add encrypted user-owned LLM credentials.

Revision ID: 0027_user_llm_credentials
Revises: 0026_agent_package_deliveries
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0027_user_llm_credentials"
down_revision: str | None = "0026_agent_package_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("llm_provider", sa.String(32), nullable=True))
    op.create_table(
        "user_llm_credentials",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(2_000), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('deepseek', 'openai', 'openai_compatible')",
            name="ck_user_llm_credential_provider",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_llm_credential_provider"),
    )
    op.create_index("ix_user_llm_credentials_user_id", "user_llm_credentials", ["user_id"])
    op.create_index("ix_user_llm_credentials_provider", "user_llm_credentials", ["provider"])


def downgrade() -> None:
    op.drop_table("user_llm_credentials")
    op.drop_column("users", "llm_provider")
