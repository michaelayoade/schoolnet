"""Tests for admissions management: shortlist, calendar, tracking, reminders."""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from tests.conftest import _create_access_token


def _get_csrf(client):
    resp = client.get("/login")
    return resp.cookies.get("csrf_token", "")


def _setup_admissions_scenario(db_session):
    """Create parent with 2 wards, 2 schools with admission forms."""
    from app.models.auth import Session as AuthSession
    from app.models.auth import SessionStatus
    from app.models.billing import Price, PriceType, Product
    from app.models.person import Person
    from app.models.rbac import PersonRole, Role
    from app.models.school import (
        AdmissionForm,
        AdmissionFormStatus,
        School,
        SchoolCategory,
        SchoolGender,
        SchoolStatus,
        SchoolType,
    )

    # Parent with location
    parent = Person(
        first_name="Admissions",
        last_name="Parent",
        email=f"admissions-{uuid.uuid4().hex[:8]}@example.com",
        latitude=6.5244,
        longitude=3.3792,  # Lagos
    )
    db_session.add(parent)
    db_session.flush()

    role = db_session.scalar(select(Role).where(Role.name == "parent"))
    if not role:
        role = Role(name="parent", description="Parent role")
        db_session.add(role)
        db_session.flush()
    db_session.add(PersonRole(person_id=parent.id, role_id=role.id))

    auth_sess = AuthSession(
        person_id=parent.id,
        token_hash="adm-hash-" + uuid.uuid4().hex[:8],
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(auth_sess)
    db_session.flush()

    token = _create_access_token(str(parent.id), str(auth_sess.id), roles=["parent"])

    # Wards
    from app.models.ward import Ward

    ward1 = Ward(
        parent_id=parent.id,
        first_name="Alice",
        last_name="Test",
        religion="christianity",
    )
    ward2 = Ward(
        parent_id=parent.id,
        first_name="Bob",
        last_name="Test",
        has_special_needs=True,
        special_needs_details="Dyslexia support needed",
    )
    db_session.add_all([ward1, ward2])
    db_session.flush()

    # School owner
    owner = Person(
        first_name="School",
        last_name="Owner",
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(owner)
    db_session.flush()

    # Schools with location
    school1 = School(
        owner_id=owner.id,
        name="St. Mary's Academy",
        slug=f"st-marys-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.active,
        religious_affiliation="catholic",
        curriculum_type="british",
        special_needs_support=True,
        latitude=6.4541,
        longitude=3.3947,  # ~8km from parent
    )
    school2 = School(
        owner_id=owner.id,
        name="Green Valley School",
        slug=f"green-valley-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.secondary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        status=SchoolStatus.active,
        latitude=6.6018,
        longitude=3.3515,  # ~9km from parent
    )
    db_session.add_all([school1, school2])
    db_session.flush()

    # Products and prices for admission forms
    prod1 = Product(name="Admission Form 1", is_active=True)
    prod2 = Product(name="Admission Form 2", is_active=True)
    db_session.add_all([prod1, prod2])
    db_session.flush()

    price1 = Price(
        product_id=prod1.id,
        unit_amount=500000,
        currency="NGN",
        type=PriceType.one_time,
        is_active=True,
    )
    price2 = Price(
        product_id=prod2.id,
        unit_amount=300000,
        currency="NGN",
        type=PriceType.one_time,
        is_active=True,
    )
    db_session.add_all([price1, price2])
    db_session.flush()

    # Admission forms with exam details
    form1 = AdmissionForm(
        school_id=school1.id,
        product_id=prod1.id,
        price_id=price1.id,
        title="JSS1 Admission 2026/2027",
        academic_year="2026/2027",
        status=AdmissionFormStatus.active,
        closes_at=datetime.now(timezone.utc) + timedelta(days=30),
        has_entrance_exam=True,
        exam_date=datetime.now(timezone.utc) + timedelta(days=20),
        exam_time="9:00 AM - 12:00 PM",
        exam_venue="Main Hall",
        exam_requirements=["2B pencils", "Calculator", "Birth certificate"],
        interview_date=datetime.now(timezone.utc) + timedelta(days=25),
        interview_time="2:00 PM",
        interview_venue="Admin Block",
    )
    form2 = AdmissionForm(
        school_id=school2.id,
        product_id=prod2.id,
        price_id=price2.id,
        title="SS1 Admission 2026/2027",
        academic_year="2026/2027",
        status=AdmissionFormStatus.active,
        closes_at=datetime.now(timezone.utc) + timedelta(days=28),
    )
    db_session.add_all([form1, form2])
    db_session.flush()

    db_session.commit()

    return {
        "parent": parent,
        "token": token,
        "ward1": ward1,
        "ward2": ward2,
        "school1": school1,
        "school2": school2,
        "form1": form1,
        "form2": form2,
    }


# ── Shortlist Tests ─────────────────────────────────────


class TestShortlistService:
    def test_create_shortlist(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        sl = svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        assert sl.id is not None
        assert sl.parent_id == data["parent"].id
        status_val = sl.status.value if hasattr(sl.status, "value") else str(sl.status)
        assert status_val == "researching"
        # Exam prep checklist auto-populated from form1's exam_requirements
        assert sl.exam_prep_checklist is not None
        assert len(sl.exam_prep_checklist) == 3
        assert sl.exam_prep_checklist[0]["item"] == "2B pencils"
        assert sl.exam_prep_checklist[0]["done"] is False

    def test_update_criteria_and_checklist(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        sl = svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        updated_checklist = [
            {"item": "2B pencils", "done": True},
            {"item": "Calculator", "done": False},
            {"item": "Birth certificate", "done": True},
        ]
        svc.update(
            sl,
            religious_fit=4,
            curriculum_fit=5,
            overall_fit=4,
            exam_registration_status="registered",
            exam_prep_checklist=updated_checklist,
        )
        db_session.flush()

        assert sl.religious_fit == 4
        assert sl.overall_fit == 4
        reg_val = (
            sl.exam_registration_status.value
            if hasattr(sl.exam_registration_status, "value")
            else str(sl.exam_registration_status)
        )
        assert reg_val == "registered"
        assert sl.exam_prep_checklist[0]["done"] is True
        assert sl.exam_prep_checklist[1]["done"] is False

    def test_tracking_table_with_distance(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        rows = svc.get_tracking_table(data["parent"].id)
        assert len(rows) == 1
        row = rows[0]
        assert row.school_name == "St. Mary's Academy"
        assert row.ward_name == "Alice Test"
        assert row.distance_km is not None
        assert row.distance_km > 0
        assert row.exam_registration_status == "not_required"

    def test_remove_shortlist(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        sl = svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        svc.remove(sl)
        db_session.flush()

        assert sl.is_active is False
        rows = svc.get_tracking_table(data["parent"].id)
        assert len(rows) == 0


# ── Calendar Tests ──────────────────────────────────────


class TestCalendarService:
    def test_create_event(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        event = svc.create_event(
            parent_id=data["parent"].id,
            title="Test Exam",
            event_date=date.today() + timedelta(days=10),
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        db_session.flush()

        assert event.id is not None
        assert event.title == "Test Exam"
        assert event.is_reminder_set is True

    def test_same_ward_conflict_detection(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        exam_date = date.today() + timedelta(days=10)
        svc.create_event(
            parent_id=data["parent"].id,
            title="School A Exam",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        svc.create_event(
            parent_id=data["parent"].id,
            title="School B Exam",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        db_session.flush()

        conflicts = svc.detect_conflicts(data["parent"].id)
        assert len(conflicts) >= 1
        _, _, ctype = conflicts[0]
        assert ctype == "same_ward"

    def test_cross_ward_conflict_detection(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        exam_date = date.today() + timedelta(days=10)
        svc.create_event(
            parent_id=data["parent"].id,
            title="Ward1 Exam",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        svc.create_event(
            parent_id=data["parent"].id,
            title="Ward2 Interview",
            event_date=exam_date,
            event_type="interview",
            ward_id=data["ward2"].id,
        )
        db_session.flush()

        conflicts = svc.detect_conflicts(data["parent"].id)
        assert len(conflicts) >= 1
        _, _, ctype = conflicts[0]
        assert ctype == "cross_ward"

    def test_flag_conflicts(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        exam_date = date.today() + timedelta(days=10)
        e1 = svc.create_event(
            parent_id=data["parent"].id,
            title="Exam A",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        e2 = svc.create_event(
            parent_id=data["parent"].id,
            title="Exam B",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        db_session.flush()

        count = svc.flag_conflicts(data["parent"].id)
        db_session.flush()

        assert count >= 1
        assert e1.has_conflict is True
        assert e2.has_conflict is True
        assert "Exam B" in (e1.conflict_notes or "")

    def test_auto_create_from_admission_form(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService
        from app.services.shortlist import ShortlistService

        sl_svc = ShortlistService(db_session)
        shortlist = sl_svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        cal_svc = AdmissionsCalendarService(db_session)
        events = cal_svc.auto_create_from_admission_form(
            data["parent"].id, shortlist, data["form1"]
        )
        db_session.flush()

        # form1 has closes_at, exam_date, interview_date → 3 events
        assert len(events) == 3
        types = {e.event_type.value for e in events}
        assert "application_deadline" in types
        assert "exam" in types
        assert "interview" in types

    def test_list_upcoming(self, db_session):
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        svc.create_event(
            parent_id=data["parent"].id,
            title="Upcoming Event",
            event_date=date.today() + timedelta(days=5),
            event_type="custom",
        )
        # Past event — should not appear
        svc.create_event(
            parent_id=data["parent"].id,
            title="Past Event",
            event_date=date.today() - timedelta(days=5),
            event_type="custom",
        )
        db_session.flush()

        upcoming = svc.list_upcoming(data["parent"].id, days=30)
        titles = [e.title for e in upcoming]
        assert "Upcoming Event" in titles
        assert "Past Event" not in titles


# ── Haversine Tests ─────────────────────────────────────


class TestHaversine:
    def test_haversine_distance(self):
        from app.services.shortlist import _haversine_km

        # Lagos to Lekki ≈ ~8km
        dist = _haversine_km(6.5244, 3.3792, 6.4541, 3.3947)
        assert 7 < dist < 10

    def test_same_point_zero(self):
        from app.services.shortlist import _haversine_km

        assert _haversine_km(6.5, 3.3, 6.5, 3.3) == 0.0


# ── Web Route Tests ─────────────────────────────────────


class TestShortlistRoutes:
    def test_shortlist_list_page(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        resp = client.get(
            "/parent/shortlist",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert b"School Shortlist" in resp.content

    def test_add_shortlist_page(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        resp = client.get(
            f"/parent/shortlist/add/{data['school1'].id}",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert b"Add to Shortlist" in resp.content

    def test_add_shortlist_submit(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        csrf = _get_csrf(client)
        resp = client.post(
            f"/parent/shortlist/add/{data['school1'].id}",
            data={
                "ward_id": str(data["ward1"].id),
                "notes_general": "Good school",
                "csrf_token": csrf,
            },
            cookies={"access_token": data["token"], "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers.get("location", "")

    def test_add_shortlist_wrong_ward(self, client, db_session):
        """Submitting with a ward that doesn't belong to the parent should fail."""
        data = _setup_admissions_scenario(db_session)
        csrf = _get_csrf(client)
        fake_ward_id = str(uuid.uuid4())
        resp = client.post(
            f"/parent/shortlist/add/{data['school1'].id}",
            data={
                "ward_id": fake_ward_id,
                "csrf_token": csrf,
            },
            cookies={"access_token": data["token"], "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "error" in resp.headers.get("location", "")


class TestCalendarRoutes:
    def test_calendar_page(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        resp = client.get(
            "/parent/calendar",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert b"Admissions Calendar" in resp.content

    def test_add_event(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        csrf = _get_csrf(client)
        event_date = (date.today() + timedelta(days=10)).isoformat()
        resp = client.post(
            "/parent/calendar/add",
            data={
                "title": "Test Event",
                "event_date": event_date,
                "event_type": "custom",
                "csrf_token": csrf,
            },
            cookies={"access_token": data["token"], "csrf_token": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "success" in resp.headers.get("location", "")


class TestTrackingRoutes:
    def test_tracking_page(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        resp = client.get(
            "/parent/tracking",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert b"Admissions Tracking" in resp.content

    def test_csv_export_empty(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        resp = client.get(
            "/parent/tracking/export",
            cookies={"access_token": data["token"]},
            follow_redirects=False,
        )
        # No shortlists → redirect with error
        assert resp.status_code == 303

    def test_csv_export_with_data(self, client, db_session):
        data = _setup_admissions_scenario(db_session)
        # Create a shortlist first
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.commit()

        resp = client.get(
            "/parent/tracking/export",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/csv")
        assert b"St. Mary" in resp.content


# ── Reminder Task Tests ─────────────────────────────────


class TestConflictDetectionEdgeCases:
    def test_no_false_positive_non_overlapping_buffers(self, db_session):
        """Events with buffer days that don't overlap should not conflict."""
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        # Event 1: day 10, buffer_after=0
        svc.create_event(
            parent_id=data["parent"].id,
            title="Exam A",
            event_date=date.today() + timedelta(days=10),
            event_type="exam",
            ward_id=data["ward1"].id,
            buffer_days_after=0,
        )
        # Event 2: day 12, buffer_before=0 — gap of 1 day
        svc.create_event(
            parent_id=data["parent"].id,
            title="Exam B",
            event_date=date.today() + timedelta(days=12),
            event_type="exam",
            ward_id=data["ward1"].id,
            buffer_days_before=0,
        )
        db_session.flush()

        conflicts = svc.detect_conflicts(data["parent"].id)
        # Should have zero same-ward conflicts (day 10 and day 12 don't overlap)
        same_ward = [c for c in conflicts if c[2] == "same_ward"]
        assert len(same_ward) == 0

    def test_no_cross_ward_for_deadlines(self, db_session):
        """Deadline events across wards should not trigger cross-ward conflict."""
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        same_day = date.today() + timedelta(days=10)
        svc.create_event(
            parent_id=data["parent"].id,
            title="Deadline School A",
            event_date=same_day,
            event_type="application_deadline",
            ward_id=data["ward1"].id,
        )
        svc.create_event(
            parent_id=data["parent"].id,
            title="Deadline School B",
            event_date=same_day,
            event_type="application_deadline",
            ward_id=data["ward2"].id,
        )
        db_session.flush()

        conflicts = svc.detect_conflicts(data["parent"].id)
        # Deadlines don't require parent attendance — no cross-ward conflict
        cross = [c for c in conflicts if c[2] == "cross_ward"]
        assert len(cross) == 0


class TestApplicationShortlistAutoLink:
    def test_submit_links_to_shortlist(self, db_session):
        """Submitting an application should auto-link to existing shortlist."""
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        sl_svc = ShortlistService(db_session)
        sl = sl_svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.flush()

        # Create and submit an application
        from app.models.school import Application, ApplicationStatus

        app = Application(
            admission_form_id=data["form1"].id,
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            application_number=f"SCH-TEST-{uuid.uuid4().hex[:6].upper()}",
            status=ApplicationStatus.draft,
        )
        db_session.add(app)
        db_session.flush()

        from app.services.application import ApplicationService

        app_svc = ApplicationService(db_session)
        app_svc.submit(
            app,
            ward_first_name="Alice",
            ward_last_name="Test",
            ward_date_of_birth=date(2015, 3, 1),
            ward_gender="female",
            ward_id=data["ward1"].id,
        )
        db_session.flush()

        # Shortlist should now be linked
        db_session.refresh(sl)
        assert sl.application_id == app.id
        status_val = sl.status.value if hasattr(sl.status, "value") else str(sl.status)
        assert status_val == "applied"


class TestCSVExportColumns:
    def test_csv_has_distance_and_exam_reg(self, client, db_session):
        """CSV export should include distance and exam registration columns."""
        data = _setup_admissions_scenario(db_session)
        from app.services.shortlist import ShortlistService

        svc = ShortlistService(db_session)
        svc.create(
            parent_id=data["parent"].id,
            ward_id=data["ward1"].id,
            school_id=data["school1"].id,
        )
        db_session.commit()

        resp = client.get(
            "/parent/tracking/export",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        # Check header row
        assert "Distance (km)" in content
        assert "Exam Registration" in content
        # Should have a distance value since both parent and school have lat/lng
        lines = content.strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 row


class TestReminderTask:
    def test_task_runs_without_error(self, db_session):
        """Task should run even with no events."""
        _setup_admissions_scenario(db_session)
        from app.tasks.admissions_reminders import (
            send_daily_admissions_reminders_task,
        )

        # Call synchronously (not via Celery)
        result = send_daily_admissions_reminders_task()
        assert result["sent"] >= 0
        assert result["scanned"] >= 0

    def test_reminder_creates_notification(self, db_session):
        """Task should create notification for event with reminder due today."""
        data = _setup_admissions_scenario(db_session)
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        # Create event with reminder_days_before=3, event in 3 days → reminder today
        svc.create_event(
            parent_id=data["parent"].id,
            title="Upcoming Exam",
            event_date=date.today() + timedelta(days=3),
            event_type="exam",
            is_reminder_set=True,
            reminder_days_before=3,
        )
        db_session.commit()

        from app.tasks.admissions_reminders import (
            send_daily_admissions_reminders_task,
        )

        result = send_daily_admissions_reminders_task()
        assert result["sent"] >= 1

        # Check notification was created
        from sqlalchemy import select

        from app.models.notification import Notification

        notifs = list(
            db_session.scalars(
                select(Notification).where(
                    Notification.recipient_id == data["parent"].id,
                    Notification.entity_type == "admissions_calendar_event",
                )
            ).all()
        )
        assert len(notifs) >= 1
        assert "Upcoming Exam" in notifs[0].title


# ── Auth & Registration Tests ───────────────────────────


class TestAuthRegistrationLogin:
    def test_unverified_email_login_shows_verify_message(self, client, db_session):
        """Login with correct password but unverified email shows verify message."""
        from app.models.auth import AuthProvider, UserCredential
        from app.models.person import Person
        from app.services.auth_flow import hash_password

        person = Person(
            first_name="Unverified",
            last_name="User",
            email=f"unverified-{uuid.uuid4().hex[:8]}@test.com",
            email_verified=False,
        )
        db_session.add(person)
        db_session.flush()

        cred = UserCredential(
            person_id=person.id,
            provider=AuthProvider.local,
            username=person.email,
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(cred)
        db_session.commit()

        resp = client.get("/admin/login")
        csrf = resp.cookies.get("csrf_token", "")

        response = client.post(
            "/admin/login",
            data={
                "email": person.email,
                "password": "TestPass123",
                "next": "/admin",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"verify your email" in response.content.lower()

    def test_verified_email_login_succeeds(self, client, db_session):
        """Login with verified email + correct password redirects successfully."""
        from app.models.auth import AuthProvider, UserCredential
        from app.models.person import Person
        from app.services.auth_flow import hash_password

        person = Person(
            first_name="Verified",
            last_name="User",
            email=f"verified-{uuid.uuid4().hex[:8]}@test.com",
            email_verified=True,
        )
        db_session.add(person)
        db_session.flush()

        cred = UserCredential(
            person_id=person.id,
            provider=AuthProvider.local,
            username=person.email,
            password_hash=hash_password("TestPass123"),
        )
        db_session.add(cred)
        db_session.commit()

        resp = client.get("/admin/login")
        csrf = resp.cookies.get("csrf_token", "")

        response = client.post(
            "/admin/login",
            data={
                "email": person.email,
                "password": "TestPass123",
                "next": "/admin",
                "csrf_token": csrf,
            },
            cookies={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_registration_sets_username(self, db_session):
        """Registration should set UserCredential.username = email."""
        from app.services.registration import RegistrationService

        svc = RegistrationService(db_session)
        person = svc.register_parent(
            first_name="RegTest",
            last_name="User",
            email=f"regtest-{uuid.uuid4().hex[:8]}@test.com",
            password="StrongPass123!",
        )
        db_session.flush()

        from app.models.auth import AuthProvider, UserCredential

        cred = db_session.scalar(
            select(UserCredential).where(
                UserCredential.person_id == person.id,
                UserCredential.provider == AuthProvider.local,
            )
        )
        assert cred is not None
        assert cred.username == person.email


# ── Calendar Conflict-Check Endpoint Test ───────────────


class TestCalendarConflictEndpoint:
    def test_check_conflicts_returns_fragment(self, client, db_session):
        """POST /parent/calendar/check-conflicts returns HTML fragment."""
        data = _setup_admissions_scenario(db_session)
        csrf = _get_csrf(client)

        # Create overlapping events first
        from app.services.admissions_calendar import AdmissionsCalendarService

        svc = AdmissionsCalendarService(db_session)
        exam_date = date.today() + timedelta(days=10)
        svc.create_event(
            parent_id=data["parent"].id,
            title="Exam A",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        svc.create_event(
            parent_id=data["parent"].id,
            title="Exam B",
            event_date=exam_date,
            event_type="exam",
            ward_id=data["ward1"].id,
        )
        db_session.commit()

        response = client.post(
            "/parent/calendar/check-conflicts",
            data={"csrf_token": csrf},
            cookies={"access_token": data["token"], "csrf_token": csrf},
        )
        assert response.status_code == 200
        # Should contain conflict info
        assert b"conflict" in response.content.lower()

    def test_check_conflicts_no_conflicts(self, client, db_session):
        """POST /parent/calendar/check-conflicts with no events shows all clear."""
        data = _setup_admissions_scenario(db_session)
        csrf = _get_csrf(client)

        response = client.post(
            "/parent/calendar/check-conflicts",
            data={"csrf_token": csrf},
            cookies={"access_token": data["token"], "csrf_token": csrf},
        )
        assert response.status_code == 200
        assert b"No scheduling conflicts" in response.content


# ── School Forms Render Tests ───────────────────────────


class TestSchoolFormsRender:
    def _setup_school_admin(self, db_session):
        from app.models.auth import Session as AuthSession
        from app.models.auth import SessionStatus
        from app.models.person import Person
        from app.models.rbac import PersonRole, Role
        from app.models.school import (
            School,
            SchoolCategory,
            SchoolGender,
            SchoolStatus,
            SchoolType,
        )

        admin = Person(
            first_name="SchoolAdmin",
            last_name="Test",
            email=f"schooladmin-{uuid.uuid4().hex[:8]}@test.com",
            email_verified=True,
        )
        db_session.add(admin)
        db_session.flush()

        role = db_session.scalar(select(Role).where(Role.name == "school_admin"))
        if not role:
            role = Role(name="school_admin", description="School admin")
            db_session.add(role)
            db_session.flush()
        db_session.add(PersonRole(person_id=admin.id, role_id=role.id))

        auth_sess = AuthSession(
            person_id=admin.id,
            token_hash="sa-hash-" + uuid.uuid4().hex[:8],
            status=SessionStatus.active,
            ip_address="127.0.0.1",
            user_agent="pytest",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db_session.add(auth_sess)
        db_session.flush()

        token = _create_access_token(
            str(admin.id), str(auth_sess.id), roles=["school_admin"]
        )

        school = School(
            owner_id=admin.id,
            name="Admin Test School",
            slug=f"admin-test-{uuid.uuid4().hex[:6]}",
            school_type=SchoolType.primary,
            category=SchoolCategory.private,
            gender=SchoolGender.mixed,
            status=SchoolStatus.active,
            religious_affiliation="catholic",
            curriculum_type="british",
            special_needs_support=True,
        )
        db_session.add(school)
        db_session.commit()

        return {"admin": admin, "school": school, "token": token}

    def test_create_form_page_has_exam_fields(self, client, db_session):
        """School form create page should include exam/interview fields."""
        data = self._setup_school_admin(db_session)
        resp = client.get(
            "/school/forms/create",
            cookies={"access_token": data["token"]},
        )
        assert resp.status_code == 200
        assert b"Entrance Exam" in resp.content
        assert b"has_entrance_exam" in resp.content
        assert b"exam_venue" in resp.content
        assert b"interview_date" in resp.content
