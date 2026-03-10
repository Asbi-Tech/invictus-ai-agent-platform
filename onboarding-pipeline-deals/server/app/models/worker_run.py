from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from ..database import Base


class WorkerRun(Base):
    __tablename__ = "worker_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=False
    )
    triggered_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    # pending | running | completed | failed | cancelled
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # discovering_files | downloading | analyzing | persisting | version_management | vectorizing
    current_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Flexible progress counters: {"files_found": N, "downloaded": N, ...}
    progress_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_worker_runs_org_id", "organization_id"),
        Index("ix_worker_runs_org_status", "organization_id", "status"),
    )
