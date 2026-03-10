"""Add worker_runs table for UI-triggered pipeline runs.

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-10 00:00:00.000000 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "triggered_by",
            sa.Integer,
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("current_stage", sa.String, nullable=True),
        sa.Column("progress_data", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_worker_runs_org_id", "worker_runs", ["organization_id"])
    op.create_index(
        "ix_worker_runs_org_status", "worker_runs", ["organization_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_worker_runs_org_status", table_name="worker_runs")
    op.drop_index("ix_worker_runs_org_id", table_name="worker_runs")
    op.drop_table("worker_runs")
