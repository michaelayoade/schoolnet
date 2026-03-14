"""Ad management service."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload

from app.models.ad import Ad, AdSlot, AdStatus
from app.schemas.ad import AdCreate, AdUpdate

logger = logging.getLogger(__name__)

# Click fraud protection: in-memory cooldown tracker
_click_lock = threading.Lock()
_click_timestamps: dict[tuple[UUID, str], float] = {}
_CLICK_COOLDOWN_SECONDS = 30


_CLICK_CLEANUP_THRESHOLD = 1000  # evict stale entries when dict exceeds this size


def _is_click_allowed(ad_id: UUID, ip: str) -> bool:
    """Return True if this (ad, ip) pair is not within the cooldown window."""
    key = (ad_id, ip)
    now = time.monotonic()
    with _click_lock:
        # Periodic cleanup to prevent unbounded memory growth
        if len(_click_timestamps) > _CLICK_CLEANUP_THRESHOLD:
            stale = [k for k, ts in _click_timestamps.items() if (now - ts) >= _CLICK_COOLDOWN_SECONDS]
            for k in stale:
                del _click_timestamps[k]
        last = _click_timestamps.get(key)
        if last is not None and (now - last) < _CLICK_COOLDOWN_SECONDS:
            return False
        _click_timestamps[key] = now
    return True


class AdService:
    """Service for managing advertisements."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, ad_id: UUID) -> Ad | None:
        return self.db.get(Ad, ad_id)

    def list_all(
        self,
        *,
        status: AdStatus | None = None,
        slot: AdSlot | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Ad]:
        stmt = select(Ad).options(joinedload(Ad.school)).where(Ad.is_active.is_(True))
        if status:
            stmt = stmt.where(Ad.status == status)
        if slot:
            stmt = stmt.where(Ad.slot == slot)
        stmt = stmt.order_by(Ad.created_at.desc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).unique().all())

    def count(
        self,
        *,
        status: AdStatus | None = None,
        slot: AdSlot | None = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Ad).where(Ad.is_active.is_(True))
        if status:
            stmt = stmt.where(Ad.status == status)
        if slot:
            stmt = stmt.where(Ad.slot == slot)
        return self.db.scalar(stmt) or 0

    def create(self, data: AdCreate) -> Ad:
        ad = Ad(**data.model_dump(exclude_none=True))
        self.db.add(ad)
        self.db.flush()
        logger.info("Created ad: %s (slot=%s)", ad.id, ad.slot.value)
        return ad

    def update(self, ad: Ad, data: AdUpdate) -> Ad:
        updates = data.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(ad, key, value)
        self.db.flush()
        logger.info("Updated ad: %s", ad.id)
        return ad

    def delete(self, ad: Ad) -> None:
        ad.is_active = False
        self.db.flush()
        logger.info("Soft-deleted ad: %s", ad.id)

    def activate(self, ad: Ad) -> Ad:
        ad.status = AdStatus.active
        self.db.flush()
        logger.info("Activated ad: %s", ad.id)
        return ad

    def pause(self, ad: Ad) -> Ad:
        ad.status = AdStatus.paused
        self.db.flush()
        logger.info("Paused ad: %s", ad.id)
        return ad

    def active_for_slot(self, slot: AdSlot, *, limit: int = 5) -> list[Ad]:
        """Return active, in-schedule, within-budget ads for a given slot."""
        now = datetime.now(UTC)
        stmt = (
            select(Ad)
            .options(joinedload(Ad.school))
            .where(
                Ad.is_active.is_(True),
                Ad.status == AdStatus.active,
                Ad.slot == slot,
                or_(Ad.starts_at.is_(None), Ad.starts_at <= now),
                or_(Ad.ends_at.is_(None), Ad.ends_at >= now),
                or_(Ad.budget_cents.is_(None), Ad.spent_cents < Ad.budget_cents),
            )
            .order_by(Ad.priority.desc(), Ad.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

    def record_impression(self, ad_id: UUID) -> None:
        """Increment impression counter."""
        stmt = update(Ad).where(Ad.id == ad_id).values(impressions=Ad.impressions + 1)
        self.db.execute(stmt)

    def record_click(self, ad_id: UUID, ip: str | None = None) -> bool:
        """Increment click counter. Returns False if rate-limited."""
        if ip and not _is_click_allowed(ad_id, ip):
            logger.debug("Click rate-limited: ad=%s ip=%s", ad_id, ip)
            return False
        stmt = update(Ad).where(Ad.id == ad_id).values(
            clicks=Ad.clicks + 1,
            spent_cents=Ad.spent_cents + 1,
        )
        self.db.execute(stmt)
        return True

    def expire_stale(self) -> int:
        """Mark active ads past their end date as expired. Returns count."""
        now = datetime.now(UTC)
        stmt = (
            update(Ad)
            .where(
                Ad.status == AdStatus.active,
                Ad.ends_at.isnot(None),
                Ad.ends_at < now,
            )
            .values(status=AdStatus.expired)
        )
        result = self.db.execute(stmt)
        count = result.rowcount
        if count:
            logger.info("Expired %d stale ads", count)
        return count
