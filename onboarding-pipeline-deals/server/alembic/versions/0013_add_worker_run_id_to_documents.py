"""Add worker_run_id FK to documents table for run-level traceability.

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-11 00:00:00.000000 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("worker_run_id", sa.Integer(), sa.ForeignKey("worker_runs.id"), nullable=True),
    )
    op.create_index("ix_documents_worker_run_id", "documents", ["worker_run_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_worker_run_id", table_name="documents")
    op.drop_column("documents", "worker_run_id")
