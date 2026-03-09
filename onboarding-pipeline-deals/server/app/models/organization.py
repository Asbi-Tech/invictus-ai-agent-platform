from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base

if TYPE_CHECKING:
    from .user import User
    from .document import Document
    from .deal import Deal


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Lowercase alphanumeric slug for deduplication
    name_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Firm context prompt (moved from users.custom_prompt)
    custom_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Per-org quota limits
    classification_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="12000"
    )
    vectorization_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="800"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="organization"
    )
    deals: Mapped[list["Deal"]] = relationship("Deal", back_populates="organization")
