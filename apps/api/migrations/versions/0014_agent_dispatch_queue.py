"""Add durable agent dispatch queue.

Revision ID: 0014_agent_dispatch_queue
Revises: 0013_agent_pilot_evidence
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0014_agent_dispatch_queue"
down_revision: str | None = "0013_agent_pilot_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_run_events", sa.Column("external_event_id", sa.String(128)))
    op.create_index("uq_agent_run_events_external_event", "agent_run_events", ["run_id", "external_event_id"], unique=True)
    op.create_table(
        "agent_dispatch_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'leased', 'retry_wait', 'dispatched', 'dead_letter', 'cancelled')", name="ck_agent_dispatch_job_status"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", name="uq_agent_dispatch_job_run"),
    )
    for column in ("run_id", "status", "next_attempt_at", "lease_expires_at"):
        op.create_index(f"ix_agent_dispatch_jobs_{column}", "agent_dispatch_jobs", [column])


def downgrade() -> None:
    op.drop_table("agent_dispatch_jobs")
    op.drop_index("uq_agent_run_events_external_event", table_name="agent_run_events")
    op.drop_column("agent_run_events", "external_event_id")
