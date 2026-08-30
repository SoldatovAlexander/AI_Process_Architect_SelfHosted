"""Add governed agent incident journal.

Revision ID: 0015_agent_incidents
Revises: 0014_agent_dispatch_queue
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0015_agent_incidents"
down_revision: str | None = "0014_agent_dispatch_queue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_incidents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("resolution_code", sa.String(64)),
        sa.Column("replay_run_id", sa.String(36)),
        sa.Column("resolved_by_user_id", sa.String(36)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('open', 'resolved', 'replayed')", name="ck_agent_incident_status"),
        sa.CheckConstraint("category IN ('dispatch', 'runtime', 'limit', 'timeout', 'escalation')", name="ck_agent_incident_category"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", name="uq_agent_incident_run"),
    )
    for column in ("project_id", "run_id", "status", "category", "replay_run_id"):
        op.create_index(f"ix_agent_incidents_{column}", "agent_incidents", [column])


def downgrade() -> None:
    op.drop_table("agent_incidents")
