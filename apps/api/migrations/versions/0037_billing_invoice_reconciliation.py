"""Add provider-neutral invoice reconciliation snapshots.

Revision ID: 0037_billing_reconciliation
Revises: 0036_workspace_lifecycle
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0037_billing_reconciliation"
down_revision: str | None = "0036_workspace_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_invoices",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_invoice_id", sa.String(255), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("subscription_id", sa.String(36), nullable=True),
        sa.Column("external_customer_id", sa.String(255), nullable=True),
        sa.Column("external_subscription_id", sa.String(255), nullable=True),
        sa.Column("provider_status", sa.String(32), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider_amount_due_minor", sa.Integer(), nullable=False),
        sa.Column("provider_amount_paid_minor", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider_status IN ('draft', 'open', 'paid', 'payment_failed', 'void', 'uncollectible')",
            name="ck_billing_invoice_provider_status",
        ),
        sa.CheckConstraint("provider_amount_due_minor >= 0", name="ck_billing_invoice_amount_due_nonnegative"),
        sa.CheckConstraint("provider_amount_paid_minor >= 0", name="ck_billing_invoice_amount_paid_nonnegative"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["billing_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_invoice_id", name="uq_billing_invoice_provider_external"),
    )
    for column in (
        "provider", "workspace_id", "subscription_id", "external_customer_id",
        "external_subscription_id", "provider_status", "period_start",
    ):
        op.create_index(f"ix_billing_invoices_{column}", "billing_invoices", [column])

    with op.batch_alter_table("billing_events") as batch:
        batch.add_column(sa.Column("invoice_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_billing_events_invoice_id_billing_invoices",
            "billing_invoices",
            ["invoice_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_billing_events_invoice_id", ["invoice_id"])

    op.create_table(
        "billing_invoice_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("invoice_id", sa.String(36), nullable=False),
        sa.Column("billing_event_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("pricing_catalog_version", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("expected_amount_minor", sa.Integer(), nullable=True),
        sa.Column("provider_amount_due_minor", sa.Integer(), nullable=False),
        sa.Column("discrepancy_minor", sa.Integer(), nullable=True),
        sa.Column("reconciliation_status", sa.String(32), nullable=False),
        sa.Column("usage_sha256", sa.String(64), nullable=False),
        sa.Column("usage_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reconciliation_status IN ('matched', 'mismatch', 'unpriced', 'unmapped', 'stale')",
            name="ck_billing_invoice_snapshot_status",
        ),
        sa.CheckConstraint(
            "provider_amount_due_minor >= 0",
            name="ck_billing_invoice_snapshot_amount_nonnegative",
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["billing_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["billing_event_id"], ["billing_events.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("billing_event_id", name="uq_billing_invoice_snapshot_event"),
    )
    for column in ("invoice_id", "workspace_id", "reconciliation_status", "created_at"):
        op.create_index(f"ix_billing_invoice_snapshots_{column}", "billing_invoice_snapshots", [column])


def downgrade() -> None:
    op.drop_table("billing_invoice_snapshots")
    with op.batch_alter_table("billing_events") as batch:
        batch.drop_index("ix_billing_events_invoice_id")
        batch.drop_constraint("fk_billing_events_invoice_id_billing_invoices", type_="foreignkey")
        batch.drop_column("invoice_id")
    op.drop_table("billing_invoices")
