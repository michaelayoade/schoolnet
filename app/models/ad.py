import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# ── Enums ────────────────────────────────────────────────


class AdSlot(str, enum.Enum):
    homepage_hero = "homepage_hero"
    homepage_featured = "homepage_featured"
    search_sidebar = "search_sidebar"
    search_top = "search_top"
    profile_footer = "profile_footer"


class AdType(str, enum.Enum):
    banner = "banner"
    sponsored_school = "sponsored_school"
    featured = "featured"


class AdStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    expired = "expired"


# ── Ad ───────────────────────────────────────────────────


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (
        Index("ix_ads_slot_status", "slot", "status"),
        Index("ix_ads_status_schedule", "status", "starts_at", "ends_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slot: Mapped[AdSlot] = mapped_column(Enum(AdSlot), nullable=False)
    ad_type: Mapped[AdType] = mapped_column(Enum(AdType), nullable=False)
    status: Mapped[AdStatus] = mapped_column(Enum(AdStatus), default=AdStatus.draft)

    # Content — use image_url + target_url for banners, school_id for sponsored
    image_url: Mapped[str | None] = mapped_column(String(512))
    target_url: Mapped[str | None] = mapped_column(String(512))
    html_content: Mapped[str | None] = mapped_column(Text)
    alt_text: Mapped[str | None] = mapped_column(String(255))

    # Optional link to a school for sponsored/featured types
    school_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schools.id"), index=True
    )

    # Scheduling
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Priority — higher = shown first / more often
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # Budget
    budget_cents: Mapped[int | None] = mapped_column(Integer)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Analytics
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    school = relationship("School", foreign_keys=[school_id])
