"""Add tenant_id column to organizations table.

Allows each organization to configure its own RAG Gateway tenant ID
via the Settings UI, replacing the global VECTORIZER_TENANT_ID env var.

Revision ID: 0014
Revises: 0013
Create Date: 2026-03-11 00:00:00.000000 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("tenant_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "tenant_id")
