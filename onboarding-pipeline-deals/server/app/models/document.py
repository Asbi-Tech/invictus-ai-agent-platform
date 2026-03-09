from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, expression
from ..database import Base

if TYPE_CHECKING:
    from .organization import Organization
    from .user import User
    from .deal import Deal


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Unique per org — two users in the same org sharing a Drive file produce one row
    file_id: Mapped[str] = mapped_column(String, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_created_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    drive_created_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Status values: pending | processed | vectorized | failed
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    # Deal association (FK replaces the plain deal_name string)
    deal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("deals.id"), nullable=True, index=True
    )
    # Drive folder path for display/debugging (e.g. "Portfolio/Acme Corp/Q1 2025")
    folder_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Version tracking: current | superseded
    version_status: Mapped[str] = mapped_column(String, default="current", nullable=False)
    # External vectorizer pipeline doc ID (assigned by Invitus AI Insights after ingestion)
    vectorizer_doc_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="documents"
    )
    user: Mapped["User"] = relationship("User", back_populates="documents")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="documents")

    __table_args__ = (
        # (organization_id, file_id) — unique per org; same Drive file shared by org members = one row
        Index("ix_documents_org_file_id", "organization_id", "file_id", unique=True),
        # organization_id alone — prerequisite for every org-scoped query
        Index("ix_documents_org_id", "organization_id"),
        # (organization_id, status) — all_documents / get_latest_documents_per_type
        Index("ix_documents_org_status", "organization_id", "status"),
        # (organization_id, checksum) partial — bulk dedup check in get_unprocessed_files
        Index(
            "ix_documents_org_checksum",
            "organization_id", "checksum",
            postgresql_where=expression.text("checksum IS NOT NULL"),
        ),
        # (deal_id, doc_type) partial — deal-scoped GROUP BY in get_latest_documents_per_type
        Index(
            "ix_documents_deal_type",
            "deal_id", "doc_type",
            postgresql_where=expression.text("deal_id IS NOT NULL"),
        ),
        # (organization_id, folder_path, doc_type) — dealless GROUP BY + Pass B superseded filter
        Index("ix_documents_org_folder_type", "organization_id", "folder_path", "doc_type"),
        # (organization_id, doc_type, version_status) — _mark_superseded_versions
        Index("ix_documents_org_type_version", "organization_id", "doc_type", "version_status"),
        # Keep user_id index for credential resolution in worker
        Index("ix_documents_user_id", "user_id"),
    )
