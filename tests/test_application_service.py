"""Tests for ApplicationService — purchase flow, submission, review, state machine."""

import uuid
from datetime import date

import pytest

from app.models.school import ApplicationStatus
from app.services.application import ApplicationService


class TestApplicationPurchaseFlow:
    def test_initiate_purchase_dev_mode(
        self, db_session, parent_person, admission_form_with_price
    ):
        """In dev mode (Paystack unconfigured), purchase creates app directly."""
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/parent/applications",
        )
        db_session.commit()

        assert "reference" in result
        assert "invoice_id" in result
        assert result["authorization_url"].startswith("/parent/applications/fill/")

    def test_initiate_purchase_creates_customer(
        self, db_session, parent_person, admission_form_with_price
    ):
        svc = ApplicationService(db_session)
        svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/parent/applications",
        )
        db_session.commit()

        from sqlalchemy import select

        from app.models.billing import Customer

        stmt = select(Customer).where(Customer.person_id == parent_person.id)
        customer = db_session.scalar(stmt)
        assert customer is not None

    def test_initiate_purchase_form_not_found(self, db_session, parent_person):
        svc = ApplicationService(db_session)
        with pytest.raises(ValueError, match="Admission form not found"):
            svc.initiate_purchase(
                parent_id=parent_person.id,
                admission_form_id=uuid.uuid4(),
                callback_url="/callback",
            )

    def test_initiate_purchase_parent_not_found(
        self, db_session, admission_form_with_price
    ):
        svc = ApplicationService(db_session)
        with pytest.raises(ValueError, match="Parent not found"):
            svc.initiate_purchase(
                parent_id=uuid.uuid4(),
                admission_form_id=admission_form_with_price.id,
                callback_url="/callback",
            )

    def test_initiate_purchase_closed_form(
        self, db_session, parent_person, admission_form_with_price
    ):
        from app.models.school import AdmissionFormStatus

        admission_form_with_price.status = AdmissionFormStatus.closed
        db_session.commit()

        svc = ApplicationService(db_session)
        with pytest.raises(ValueError, match="not currently accepting"):
            svc.initiate_purchase(
                parent_id=parent_person.id,
                admission_form_id=admission_form_with_price.id,
                callback_url="/callback",
            )

    def test_initiate_purchase_max_submissions_reached(
        self, db_session, parent_person, admission_form_with_price
    ):
        admission_form_with_price.max_submissions = 1
        admission_form_with_price.current_submissions = 1
        db_session.commit()

        svc = ApplicationService(db_session)
        with pytest.raises(ValueError, match="maximum submissions"):
            svc.initiate_purchase(
                parent_id=parent_person.id,
                admission_form_id=admission_form_with_price.id,
                callback_url="/callback",
            )


class TestApplicationSubmission:
    def _create_draft_app(self, db_session, parent_person, admission_form_with_price):
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        # Extract app id from redirect URL
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        return svc.get_by_id(uuid.UUID(app_id))

    def test_submit_application(
        self, db_session, parent_person, admission_form_with_price
    ):
        app = self._create_draft_app(
            db_session, parent_person, admission_form_with_price
        )
        assert app is not None
        assert app.status == ApplicationStatus.draft

        svc = ApplicationService(db_session)
        submitted = svc.submit(
            app,
            ward_first_name="John",
            ward_last_name="Doe",
            ward_date_of_birth=date(2018, 5, 15),
            ward_gender="male",
        )
        db_session.commit()

        assert submitted.status == ApplicationStatus.submitted
        assert submitted.ward_first_name == "John"
        assert submitted.submitted_at is not None

    def test_submit_already_submitted_fails(
        self, db_session, parent_person, admission_form_with_price
    ):
        app = self._create_draft_app(
            db_session, parent_person, admission_form_with_price
        )
        svc = ApplicationService(db_session)
        svc.submit(
            app,
            ward_first_name="John",
            ward_last_name="Doe",
            ward_date_of_birth=date(2018, 5, 15),
            ward_gender="male",
        )
        db_session.commit()

        with pytest.raises(ValueError, match="Cannot transition"):
            svc.submit(
                app,
                ward_first_name="Jane",
                ward_last_name="Doe",
                ward_date_of_birth=date(2019, 1, 1),
                ward_gender="female",
            )


class TestApplicationReview:
    def _create_submitted_app(self, db_session, parent_person, admission_form_with_price):
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        app = svc.get_by_id(uuid.UUID(app_id))
        svc.submit(
            app,
            ward_first_name="John",
            ward_last_name="Doe",
            ward_date_of_birth=date(2018, 5, 15),
            ward_gender="male",
        )
        db_session.commit()
        return app

    def test_accept_application(
        self, db_session, parent_person, admission_form_with_price, school_owner
    ):
        app = self._create_submitted_app(
            db_session, parent_person, admission_form_with_price
        )
        svc = ApplicationService(db_session)
        reviewed = svc.review(app, "accepted", school_owner.id, "Excellent candidate")
        db_session.commit()

        assert reviewed.status == ApplicationStatus.accepted
        assert reviewed.reviewed_by == school_owner.id
        assert reviewed.review_notes == "Excellent candidate"

    def test_reject_application(
        self, db_session, parent_person, admission_form_with_price, school_owner
    ):
        app = self._create_submitted_app(
            db_session, parent_person, admission_form_with_price
        )
        svc = ApplicationService(db_session)
        reviewed = svc.review(app, "rejected", school_owner.id, "Does not meet criteria")
        db_session.commit()

        assert reviewed.status == ApplicationStatus.rejected

    def test_cannot_review_draft(
        self, db_session, parent_person, admission_form_with_price, school_owner
    ):
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        app = svc.get_by_id(uuid.UUID(app_id))

        with pytest.raises(ValueError, match="Cannot transition"):
            svc.review(app, "accepted", school_owner.id)


class TestApplicationWithdraw:
    def test_withdraw_submitted(
        self, db_session, parent_person, admission_form_with_price
    ):
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        app = svc.get_by_id(uuid.UUID(app_id))
        svc.submit(
            app,
            ward_first_name="John",
            ward_last_name="Doe",
            ward_date_of_birth=date(2018, 5, 15),
            ward_gender="male",
        )
        db_session.commit()

        withdrawn = svc.withdraw(app)
        db_session.commit()
        assert withdrawn.status == ApplicationStatus.withdrawn

    def test_cannot_withdraw_draft(
        self, db_session, parent_person, admission_form_with_price
    ):
        svc = ApplicationService(db_session)
        result = svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()
        url = result["authorization_url"]
        app_id = url.split("/")[-1].split("?")[0]
        app = svc.get_by_id(uuid.UUID(app_id))

        with pytest.raises(ValueError, match="Cannot transition"):
            svc.withdraw(app)


class TestApplicationQueries:
    def test_list_for_parent(
        self, db_session, parent_person, admission_form_with_price
    ):
        svc = ApplicationService(db_session)
        svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()

        apps = svc.list_for_parent(parent_person.id)
        assert len(apps) >= 1

    def test_list_for_school(
        self, db_session, parent_person, admission_form_with_price, school
    ):
        svc = ApplicationService(db_session)
        svc.initiate_purchase(
            parent_id=parent_person.id,
            admission_form_id=admission_form_with_price.id,
            callback_url="/callback",
        )
        db_session.commit()

        apps = svc.list_for_school(school.id)
        assert len(apps) >= 1
