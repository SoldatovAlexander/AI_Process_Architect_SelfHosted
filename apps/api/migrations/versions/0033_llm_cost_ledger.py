"""Add immutable LLM token and estimated-cost ledger.

Revision ID: 0033_llm_cost_ledger
Revises: 0032_billing_usage
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0033_llm_cost_ledger"
down_revision: str | None = "0032_billing_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_records",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_hit_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_miss_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_picousd", sa.Integer(), nullable=True),
        sa.Column("pricing_catalog_version", sa.String(32), nullable=True),
        sa.Column("pricing_basis", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('success', 'partial', 'provider_error')",
            name="ck_llm_usage_outcome",
        ),
        sa.CheckConstraint(
            "pricing_basis IN ('reported_cache', 'cache_miss_assumed', 'unpriced')",
            name="ck_llm_usage_pricing_basis",
        ),
        sa.CheckConstraint(
            "request_count >= 0 AND input_tokens >= 0 AND cache_hit_tokens >= 0 "
            "AND cache_miss_tokens >= 0 AND output_tokens >= 0",
            name="ck_llm_usage_nonnegative",
        ),
        sa.ForeignKeyConstraint(["reservation_id"], ["billing_usage_reservations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id", name="uq_llm_usage_reservation"),
    )
    for column in ("workspace_id", "operation", "provider", "model", "outcome", "created_at"):
        op.create_index(f"ix_llm_usage_records_{column}", "llm_usage_records", [column])


def downgrade() -> None:
    op.drop_table("llm_usage_records")
