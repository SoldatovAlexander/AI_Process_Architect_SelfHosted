"""Allow template-based process revisions.

Revision ID: 0005_template_revision_source
Revises: 0004_analyst_prompt_version
"""
from typing import Sequence

from alembic import op


revision: str = "0005_template_revision_source"
down_revision: str | None = "0004_analyst_prompt_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("process_revisions") as batch:
        batch.drop_constraint("ck_revision_source", type_="check")
        batch.create_check_constraint(
            "ck_revision_source",
            "source IN ('initial', 'user', 'analyst', 'template', 'import', 'undo', 'restore')",
        )


def downgrade() -> None:
    with op.batch_alter_table("process_revisions") as batch:
        batch.drop_constraint("ck_revision_source", type_="check")
        batch.create_check_constraint(
            "ck_revision_source",
            "source IN ('initial', 'user', 'analyst', 'import', 'undo', 'restore')",
        )
