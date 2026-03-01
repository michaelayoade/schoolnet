"""Tests for SchoolService — school CRUD, search, ratings, dashboard."""

import uuid

from app.models.school import (
    Application,
    ApplicationStatus,
    Rating,
    SchoolStatus,
)
from app.schemas.school import SchoolCreate, SchoolUpdate
from app.services.school import SchoolService


class TestSchoolServiceCreate:
    def test_create_school(self, db_session, school_owner):
        svc = SchoolService(db_session)
        payload = SchoolCreate(
            name="Bright Future Academy",
            school_type="primary",
            category="private",
        )
        school = svc.create(payload, owner_id=school_owner.id)
        db_session.commit()

        assert school.id is not None
        assert school.name == "Bright Future Academy"
        assert school.slug == "bright-future-academy"
        assert school.owner_id == school_owner.id
        assert school.status == SchoolStatus.pending
        assert school.commission_rate == 1000

    def test_create_school_generates_unique_slug(self, db_session, school_owner):
        svc = SchoolService(db_session)
        payload = SchoolCreate(
            name="Same Name School", school_type="primary", category="private"
        )
        s1 = svc.create(payload, owner_id=school_owner.id)
        db_session.flush()

        s2 = svc.create(payload, owner_id=school_owner.id)
        db_session.commit()

        assert s1.slug == "same-name-school"
        assert s2.slug == "same-name-school-1"
        assert s1.id != s2.id


class TestSchoolServiceGet:
    def test_get_by_id(self, db_session, school):
        svc = SchoolService(db_session)
        result = svc.get_by_id(school.id)
        assert result is not None
        assert result.id == school.id

    def test_get_by_id_not_found(self, db_session):
        svc = SchoolService(db_session)
        result = svc.get_by_id(uuid.uuid4())
        assert result is None

    def test_get_by_slug(self, db_session, school):
        svc = SchoolService(db_session)
        result = svc.get_by_slug(school.slug)
        assert result is not None
        assert result.id == school.id

    def test_get_by_slug_not_found(self, db_session):
        svc = SchoolService(db_session)
        result = svc.get_by_slug("nonexistent-slug")
        assert result is None

    def test_get_schools_for_owner(self, db_session, school, school_owner):
        svc = SchoolService(db_session)
        results = svc.get_schools_for_owner(school_owner.id)
        assert len(results) >= 1
        assert any(s.id == school.id for s in results)


class TestSchoolServiceSearch:
    def test_search_returns_active_schools(self, db_session, school):
        svc = SchoolService(db_session)
        results, total = svc.search()
        assert total >= 1
        assert all(s.status == SchoolStatus.active for s in results)

    def test_search_by_name(self, db_session, school):
        svc = SchoolService(db_session)
        results, total = svc.search(query="Test Academy")
        assert total >= 1

    def test_search_by_state(self, db_session, school):
        svc = SchoolService(db_session)
        results, total = svc.search(state="Lagos")
        assert total >= 1

    def test_search_no_results(self, db_session):
        svc = SchoolService(db_session)
        results, total = svc.search(query="ZZZ_NONEXISTENT_SCHOOL")
        assert total == 0
        assert results == []

    def test_search_pagination(self, db_session, school):
        svc = SchoolService(db_session)
        results, total = svc.search(limit=1, offset=0)
        assert len(results) <= 1


class TestSchoolServiceUpdate:
    def test_update_school(self, db_session, school):
        svc = SchoolService(db_session)
        payload = SchoolUpdate(description="Updated description")
        updated = svc.update(school, payload)
        db_session.commit()

        assert updated.description == "Updated description"

    def test_approve_school(self, db_session, school_owner):
        svc = SchoolService(db_session)
        payload = SchoolCreate(
            name="Pending School", school_type="secondary", category="public"
        )
        school = svc.create(payload, owner_id=school_owner.id)
        db_session.flush()

        approver_id = uuid.uuid4()
        approved = svc.approve(school, approver_id)
        db_session.commit()

        assert approved.status == SchoolStatus.active
        assert approved.verified_at is not None
        assert approved.verified_by == approver_id

    def test_suspend_school(self, db_session, school):
        svc = SchoolService(db_session)
        suspended = svc.suspend(school)
        db_session.commit()

        assert suspended.status == SchoolStatus.suspended


class TestSchoolServiceRatings:
    def test_get_average_rating_no_ratings(self, db_session, school):
        svc = SchoolService(db_session)
        avg = svc.get_average_rating(school.id)
        assert avg is None

    def test_get_average_rating(self, db_session, school, parent_person):
        r1 = Rating(school_id=school.id, parent_id=parent_person.id, score=4)
        db_session.add(r1)
        db_session.commit()

        svc = SchoolService(db_session)
        avg = svc.get_average_rating(school.id)
        assert avg == 4.0

    def test_get_ratings(self, db_session, school, parent_person):
        r = Rating(
            school_id=school.id, parent_id=parent_person.id, score=5, comment="Great!"
        )
        db_session.add(r)
        db_session.commit()

        svc = SchoolService(db_session)
        ratings = svc.get_ratings(school.id)
        assert len(ratings) >= 1


class TestSchoolServiceDashboard:
    def test_get_dashboard_stats(
        self, db_session, school, admission_form_with_price, parent_person
    ):
        # Create an application
        app = Application(
            admission_form_id=admission_form_with_price.id,
            parent_id=parent_person.id,
            application_number=f"SCH-TEST-{uuid.uuid4().hex[:5].upper()}",
            status=ApplicationStatus.submitted,
        )
        db_session.add(app)
        db_session.commit()

        svc = SchoolService(db_session)
        stats = svc.get_dashboard_stats(school.id)

        assert stats.total_forms >= 1
        assert stats.active_forms >= 1
        assert stats.total_applications >= 1
        assert stats.pending_applications >= 1
