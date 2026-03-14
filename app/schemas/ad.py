from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.ad import AdSlot, AdStatus, AdType


class AdBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=255)
    slot: AdSlot
    ad_type: AdType
    image_url: str | None = None
    target_url: str | None = None
    html_content: str | None = None
    alt_text: str | None = None
    school_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int = 0


class AdCreate(AdBase):
    budget_cents: int | None = None


class AdUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = Field(default=None, max_length=255)
    slot: AdSlot | None = None
    ad_type: AdType | None = None
    status: AdStatus | None = None
    image_url: str | None = None
    target_url: str | None = None
    html_content: str | None = None
    alt_text: str | None = None
    school_id: UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    priority: int | None = None
    budget_cents: int | None = None


class AdRead(AdBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    status: AdStatus
    impressions: int
    clicks: int
    budget_cents: int | None
    spent_cents: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
