"""Add usage reservations and immutable transition events.

Revision ID: 0032_billing_usage
Revises: 0031_billing_core
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0032_billing_usage"
down_revision: str | None = "0031_billing_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE workspace_commercial_states SET catalog_version = '1.1' WHERE catalog_version = '1.0'")
    )
    op.create_table(
        "billing_usage_reservations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_billing_usage_quantity_positive"),
        sa.CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="ck_billing_usage_reservation_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "metric", "idempotency_key", name="uq_billing_usage_idempotency"),
    )
    for column in ("workspace_id", "metric", "status", "period_start", "expires_at"):
        op.create_index(f"ix_billing_usage_reservations_{column}", "billing_usage_reservations", [column])

    op.create_table(
        "billing_usage_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("transition", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transition IN ('reserved', 'consumed', 'released')",
            name="ck_billing_usage_event_transition",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_billing_usage_event_quantity_positive"),
        sa.ForeignKeyConstraint(["reservation_id"], ["billing_usage_reservations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id", "transition", name="uq_billing_usage_event_transition"),
    )
    for column in ("reservation_id", "transition", "created_at"):
        op.create_index(f"ix_billing_usage_events_{column}", "billing_usage_events", [column])


def downgrade() -> None:
    op.drop_table("billing_usage_events")
    op.drop_table("billing_usage_reservations")
    op.execute(
        sa.text("UPDATE workspace_commercial_states SET catalog_version = '1.0' WHERE catalog_version = '1.1'")
    )
