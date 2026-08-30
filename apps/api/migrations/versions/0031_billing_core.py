"""Add provider-neutral subscriptions and immutable billing events.

Revision ID: 0031_billing_core
Revises: 0030_admin_rbac_audit
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0031_billing_core"
down_revision: str | None = "0030_admin_rbac_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_subscriptions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_customer_id", sa.String(255), nullable=True),
        sa.Column("external_subscription_id", sa.String(255), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('trialing', 'active', 'past_due', 'paused', 'canceled', 'expired')",
            name="ck_billing_subscription_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_subscription_id", name="uq_billing_subscription_provider_external"),
    )
    for column in ("workspace_id", "provider", "external_customer_id", "plan_id", "status"):
        op.create_index(f"ix_billing_subscriptions_{column}", "billing_subscriptions", [column])

    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("subscription_id", sa.String(36), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('processed', 'ignored', 'failed')", name="ck_billing_event_status"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_billing_event_provider_external"),
    )
    for column in ("provider", "event_type", "workspace_id", "subscription_id", "status", "received_at"):
        op.create_index(f"ix_billing_events_{column}", "billing_events", [column])


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_table("billing_subscriptions")
