"""Add organizations table and migrate to org-scoped multi-tenancy.

Creates the organizations table, adds organization_id FK to users/documents/deals,
auto-creates orgs from existing company_name values, backfills all FKs,
and swaps unique constraints/indexes from user-scoped to org-scoped.

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-09 00:00:00.000000 UTC
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create organizations table ────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_key", sa.String(), nullable=False, unique=True),
        sa.Column("custom_prompt", sa.Text(), nullable=True),
        sa.Column("classification_limit", sa.Integer(), nullable=False, server_default="12000"),
        sa.Column("vectorization_limit", sa.Integer(), nullable=False, server_default="800"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_id", "organizations", ["id"])

    # ── 2. Add nullable organization_id to users, documents, deals ───────────
    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column("deals", sa.Column("organization_id", sa.Integer(), nullable=True))

    # ── 3. Auto-create orgs from existing data ──────────────────────────────
    # 3a. One org per distinct company_name
    op.execute("""
        INSERT INTO organizations (name, name_key)
        SELECT DISTINCT
            company_name,
            lower(regexp_replace(company_name, '[^a-zA-Z0-9]', '', 'g'))
        FROM users
        WHERE company_name IS NOT NULL
          AND trim(company_name) != ''
        ON CONFLICT (name_key) DO NOTHING
    """)

    # 3b. Individual orgs for users without company_name
    op.execute("""
        INSERT INTO organizations (name, name_key)
        SELECT
            'Org for ' || email,
            'user_' || id::text
        FROM users
        WHERE company_name IS NULL OR trim(company_name) = ''
    """)

    # ── 4. Link users to their orgs ─────────────────────────────────────────
    # Users with company_name → matching org
    op.execute("""
        UPDATE users u
        SET organization_id = o.id
        FROM organizations o
        WHERE u.company_name IS NOT NULL
          AND trim(u.company_name) != ''
          AND o.name_key = lower(regexp_replace(u.company_name, '[^a-zA-Z0-9]', '', 'g'))
    """)

    # Users without company_name → individual org
    op.execute("""
        UPDATE users u
        SET organization_id = o.id
        FROM organizations o
        WHERE (u.company_name IS NULL OR trim(u.company_name) = '')
          AND o.name_key = 'user_' || u.id::text
    """)

    # ── 5. Backfill documents and deals ─────────────────────────────────────
    op.execute("""
        UPDATE documents d
        SET organization_id = u.organization_id
        FROM users u
        WHERE d.user_id = u.id
    """)

    op.execute("""
        UPDATE deals dl
        SET organization_id = u.organization_id
        FROM users u
        WHERE dl.user_id = u.id
    """)

    # ── 6. Copy custom_prompt from users to their org ───────────────────────
    op.execute("""
        UPDATE organizations o
        SET custom_prompt = u.custom_prompt
        FROM users u
        WHERE u.organization_id = o.id
          AND u.custom_prompt IS NOT NULL
          AND o.custom_prompt IS NULL
    """)

    # ── 7. Make organization_id NOT NULL (documents & deals) ────────────────
    op.alter_column("documents", "organization_id", nullable=False)
    op.alter_column("deals", "organization_id", nullable=False)

    # ── 8. Add FK constraints ───────────────────────────────────────────────
    op.create_foreign_key(
        "fk_users_organization_id", "users", "organizations",
        ["organization_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_documents_organization_id", "documents", "organizations",
        ["organization_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_deals_organization_id", "deals", "organizations",
        ["organization_id"], ["id"],
    )

    # ── 9. Drop old user-scoped indexes/constraints, create org-scoped ──────
    # Documents: unique index
    op.drop_index("ix_documents_user_file_id", table_name="documents")
    op.create_index(
        "ix_documents_org_file_id", "documents",
        ["organization_id", "file_id"], unique=True,
    )

    # Documents: status index
    op.drop_index("ix_documents_user_status", table_name="documents")
    op.create_index("ix_documents_org_status", "documents", ["organization_id", "status"])

    # Documents: checksum index (partial)
    op.drop_index("ix_documents_user_checksum", table_name="documents")
    op.create_index(
        "ix_documents_org_checksum", "documents",
        ["organization_id", "checksum"],
        postgresql_where=sa.text("checksum IS NOT NULL"),
    )

    # Documents: folder + type index
    op.drop_index("ix_documents_user_folder_type", table_name="documents")
    op.create_index(
        "ix_documents_org_folder_type", "documents",
        ["organization_id", "folder_path", "doc_type"],
    )

    # Documents: type + version index
    op.drop_index("ix_documents_user_type_version", table_name="documents")
    op.create_index(
        "ix_documents_org_type_version", "documents",
        ["organization_id", "doc_type", "version_status"],
    )

    # Documents: org_id standalone
    op.create_index("ix_documents_org_id", "documents", ["organization_id"])

    # Users: organization_id index
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    # Deals: drop old user-scoped unique, create org-scoped unique
    op.drop_constraint("uq_deals_user_name_key", "deals", type_="unique")
    op.create_unique_constraint("uq_deals_org_name_key", "deals", ["organization_id", "name_key"])
    op.create_index("ix_deals_organization_id", "deals", ["organization_id"])


def downgrade() -> None:
    # ── Reverse indexes/constraints ─────────────────────────────────────────
    op.drop_index("ix_deals_organization_id", table_name="deals")
    op.drop_constraint("uq_deals_org_name_key", "deals", type_="unique")
    op.create_unique_constraint("uq_deals_user_name_key", "deals", ["user_id", "name_key"])

    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_index("ix_documents_org_id", table_name="documents")
    op.drop_index("ix_documents_org_type_version", table_name="documents")
    op.drop_index("ix_documents_org_folder_type", table_name="documents")
    op.drop_index("ix_documents_org_checksum", table_name="documents")
    op.drop_index("ix_documents_org_status", table_name="documents")
    op.drop_index("ix_documents_org_file_id", table_name="documents")

    # Recreate old user-scoped indexes
    op.create_index(
        "ix_documents_user_file_id", "documents",
        ["user_id", "file_id"], unique=True,
    )
    op.create_index("ix_documents_user_status", "documents", ["user_id", "status"])
    op.create_index(
        "ix_documents_user_checksum", "documents",
        ["user_id", "checksum"],
        postgresql_where=sa.text("checksum IS NOT NULL"),
    )
    op.create_index(
        "ix_documents_user_folder_type", "documents",
        ["user_id", "folder_path", "doc_type"],
    )
    op.create_index(
        "ix_documents_user_type_version", "documents",
        ["user_id", "doc_type", "version_status"],
    )

    # ── Drop FK constraints ─────────────────────────────────────────────────
    op.drop_constraint("fk_deals_organization_id", "deals", type_="foreignkey")
    op.drop_constraint("fk_documents_organization_id", "documents", type_="foreignkey")
    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")

    # ── Drop organization_id columns ────────────────────────────────────────
    op.drop_column("deals", "organization_id")
    op.drop_column("documents", "organization_id")
    op.drop_column("users", "organization_id")

    # ── Drop organizations table ────────────────────────────────────────────
    op.drop_index("ix_organizations_id", table_name="organizations")
    op.drop_table("organizations")
