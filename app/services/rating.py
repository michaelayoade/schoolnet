"""Rating service — school rating business logic."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.school import Application, Rating

logger = logging.getLogger(__name__)


class RatingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        school_id: UUID,
        parent_id: UUID,
        score: int,
        comment: str | None = None,
    ) -> Rating:
        if score < 1 or score > 5:
            raise ValueError("Score must be between 1 and 5")
        if comment and len(comment) > 500:
            raise ValueError("Comment must be 500 characters or fewer")

        # Check for existing rating
        existing = self.db.scalar(
            select(Rating).where(
                Rating.school_id == school_id,
                Rating.parent_id == parent_id,
                Rating.is_active.is_(True),
            )
        )
        if existing:
            raise ValueError("You have already rated this school")

        # Verify parent has an application at this school
        if not self.can_rate(school_id, parent_id):
            raise ValueError("You must have applied to this school to rate it")

        rating = Rating(
            school_id=school_id,
            parent_id=parent_id,
            score=score,
            comment=comment,
        )
        self.db.add(rating)
        self.db.flush()
        logger.info("Created rating: %s for school %s", rating.id, school_id)
        return rating

    def update(
        self,
        rating_id: UUID,
        parent_id: UUID,
        score: int | None = None,
        comment: str | None = None,
    ) -> Rating:
        """Update a rating — only the owner can update."""
        rating = self.db.get(Rating, rating_id)
        if not rating or not rating.is_active:
            raise ValueError("Rating not found")
        if rating.parent_id != parent_id:
            raise ValueError("You can only update your own rating")
        if score is not None:
            if score < 1 or score > 5:
                raise ValueError("Score must be between 1 and 5")
            rating.score = score
        if comment is not None:
            if len(comment) > 500:
                raise ValueError("Comment must be 500 characters or fewer")
            rating.comment = comment
        self.db.flush()
        logger.info("Updated rating: %s", rating.id)
        return rating

    def can_rate(self, school_id: UUID, parent_id: UUID) -> bool:
        """Check if parent has an application and hasn't already rated."""
        from app.models.school import AdmissionForm

        # Must have an application
        stmt = (
            select(Application.id)
            .join(AdmissionForm, Application.admission_form_id == AdmissionForm.id)
            .where(
                AdmissionForm.school_id == school_id,
                Application.parent_id == parent_id,
                Application.is_active.is_(True),
            )
            .limit(1)
        )
        has_application = self.db.scalar(stmt) is not None
        if not has_application:
            return False

        # Must not already have an active rating
        existing = self.db.scalar(
            select(Rating.id).where(
                Rating.school_id == school_id,
                Rating.parent_id == parent_id,
                Rating.is_active.is_(True),
            )
        )
        return existing is None

    def get_for_school(self, school_id: UUID, limit: int = 20) -> list[Rating]:
        stmt = (
            select(Rating)
            .where(Rating.school_id == school_id, Rating.is_active.is_(True))
            .order_by(Rating.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def get_average(self, school_id: UUID) -> float | None:
        result = self.db.scalar(
            select(func.avg(Rating.score)).where(
                Rating.school_id == school_id,
                Rating.is_active.is_(True),
            )
        )
        return round(float(result), 1) if result else None
