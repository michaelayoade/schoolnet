"""Celery tasks for ad management."""

import logging

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def expire_stale_ads_task(self) -> dict:
    """Mark active ads past their end date as expired."""
    db: Session | None = None
    try:
        db = SessionLocal()
        from app.services.ad import AdService

        svc = AdService(db)
        count = svc.expire_stale()
        db.commit()
        logger.info("expire_stale_ads_task completed: %d ads expired", count)
        return {"success": True, "expired_count": count}
    except (OSError, ConnectionError) as exc:
        logger.warning("expire_stale_ads_task failed (retrying): %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    finally:
        if db:
            db.close()
