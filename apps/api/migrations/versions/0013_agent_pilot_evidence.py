"""Add agent pilot evaluation evidence.

Revision ID: 0013_agent_pilot_evidence
Revises: 0012_agent_run_journal
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0013_agent_pilot_evidence"
down_revision: str | None = "0012_agent_run_journal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_evaluation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column("suite_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model_fingerprint", sa.String(64), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("cost_microunits", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_evaluation_runtime"),
        sa.CheckConstraint("status IN ('passed', 'failed')", name="ck_agent_evaluation_status"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["process_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ("project_id", "revision_id", "status", "created_by_user_id"):
        op.create_index(f"ix_agent_evaluation_runs_{column}", "agent_evaluation_runs", [column])
    op.create_table(
        "agent_baseline_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("evaluation_run_id", sa.String(36), nullable=False),
        sa.Column("runtime", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("runtime IN ('openclaw', 'hermes')", name="ck_agent_baseline_runtime"),
        sa.CheckConstraint("action IN ('approve', 'rollback')", name="ck_agent_baseline_action"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["agent_evaluation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    for column in ("project_id", "evaluation_run_id", "runtime", "created_by_user_id"):
        op.create_index(f"ix_agent_baseline_decisions_{column}", "agent_baseline_decisions", [column])


def downgrade() -> None:
    op.drop_table("agent_baseline_decisions")
    op.drop_table("agent_evaluation_runs")
