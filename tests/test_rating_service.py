"""Tests for RatingService — create, validation, queries."""

import uuid
from datetime import date

import pytest

from app.models.school import Application, ApplicationStatus, Rating
from app.services.rating import RatingService


class TestRatingCreate:
    def _create_application(self, db_session, parent_person, admission_form_with_price):
        """Helper: create a submitted application so parent can rate."""
        from app.services.application import ApplicationService

        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        return svc.get_by_id(uuid.UUID(app_id))

    def test_create_rating(
        self, db_session, school, parent_person, admission_form_with_price
    ):
        self._create_application(
            db_session, parent_person, admission_form_with_price
        )
        svc = RatingService(db_session)
        rating = svc.create(
            school_id=school.id,
            parent_id=parent_person.id,
            score=4,
            comment="Great school!",
        )
        db_session.commit()

        assert rating.id is not None
        assert rating.score == 4
        assert rating.comment == "Great school!"

    def test_create_rating_invalid_score_low(self, db_session, school, parent_person):
        svc = RatingService(db_session)
        with pytest.raises(ValueError, match="between 1 and 5"):
            svc.create(school_id=school.id, parent_id=parent_person.id, score=0)

    def test_create_rating_invalid_score_high(self, db_session, school, parent_person):
        svc = RatingService(db_session)
        with pytest.raises(ValueError, match="between 1 and 5"):
            svc.create(school_id=school.id, parent_id=parent_person.id, score=6)

    def test_create_rating_duplicate(
        self, db_session, school, parent_person, admission_form_with_price
    ):
        self._create_application(
            db_session, parent_person, admission_form_with_price
        )
        svc = RatingService(db_session)
        svc.create(school_id=school.id, parent_id=parent_person.id, score=5)
        db_session.commit()

        with pytest.raises(ValueError, match="already rated"):
            svc.create(school_id=school.id, parent_id=parent_person.id, score=3)

    def test_create_rating_without_application(self, db_session, school, parent_person):
        svc = RatingService(db_session)
        with pytest.raises(ValueError, match="must have applied"):
            svc.create(school_id=school.id, parent_id=parent_person.id, score=5)


class TestRatingQueries:
    def test_can_rate_with_application(
        self, db_session, school, parent_person, admission_form_with_price
    ):
        from app.services.application import ApplicationService

        app_svc = ApplicationService(db_session)
        app_svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()

        svc = RatingService(db_session)
        assert svc.can_rate(school.id, parent_person.id) is True

    def test_can_rate_without_application(self, db_session, school, parent_person):
        svc = RatingService(db_session)
        assert svc.can_rate(school.id, parent_person.id) is False

    def test_get_for_school(self, db_session, school, parent_person):
        r = Rating(school_id=school.id, parent_id=parent_person.id, score=3)
        db_session.add(r)
        db_session.commit()

        svc = RatingService(db_session)
        ratings = svc.get_for_school(school.id)
        assert len(ratings) >= 1

    def test_get_average(self, db_session, school):
        from tests.conftest import _unique_email
        from app.models.person import Person

        p1 = Person(first_name="A", last_name="B", email=_unique_email())
        p2 = Person(first_name="C", last_name="D", email=_unique_email())
        db_session.add_all([p1, p2])
        db_session.flush()

        r1 = Rating(school_id=school.id, parent_id=p1.id, score=4)
        r2 = Rating(school_id=school.id, parent_id=p2.id, score=2)
        db_session.add_all([r1, r2])
        db_session.commit()

        svc = RatingService(db_session)
        avg = svc.get_average(school.id)
        assert avg is not None
        assert 2.5 <= avg <= 3.5  # avg of 4+2 = 3.0, but there may be prior ratings

    def test_get_average_no_ratings(self, db_session):
        svc = RatingService(db_session)
        avg = svc.get_average(uuid.uuid4())
        assert avg is None
