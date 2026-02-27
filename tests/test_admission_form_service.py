"""Tests for AdmissionFormService — form lifecycle management."""

import uuid

import pytest

from app.models.school import AdmissionFormStatus
from app.schemas.school import AdmissionFormCreate, AdmissionFormUpdate
from app.services.admission_form import AdmissionFormService


class TestAdmissionFormCreate:
    def test_create_form(self, db_session, school):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormCreate(
            school_id=school.id,
            title="2026 JSS1 Admission",
            academic_year="2025/2026",
            price_amount=500000,
        )
        form = svc.create(payload)
        db_session.commit()

        assert form.id is not None
        assert form.title == "2026 JSS1 Admission"
        assert form.status == AdmissionFormStatus.draft
        assert form.product_id is not None
        assert form.price_id is not None

    def test_create_form_school_not_found(self, db_session):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormCreate(
            school_id=uuid.uuid4(),
            title="Orphan Form",
            academic_year="2025/2026",
            price_amount=100000,
        )
        with pytest.raises(ValueError, match="School not found"):
            svc.create(payload)


class TestAdmissionFormGet:
    def test_get_by_id(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        result = svc.get_by_id(admission_form_with_price.id)
        assert result is not None
        assert result.id == admission_form_with_price.id

    def test_get_by_id_not_found(self, db_session):
        svc = AdmissionFormService(db_session)
        result = svc.get_by_id(uuid.uuid4())
        assert result is None


class TestAdmissionFormLists:
    def test_list_for_school(self, db_session, school, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        forms = svc.list_for_school(school.id)
        assert len(forms) >= 1
        assert all(f.school_id == school.id for f in forms)

    def test_list_active_for_school(self, db_session, school, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        forms = svc.list_active_for_school(school.id)
        assert len(forms) >= 1
        assert all(f.status == AdmissionFormStatus.active for f in forms)

    def test_list_active_for_school_excludes_drafts(self, db_session, school):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormCreate(
            school_id=school.id,
            title="Draft Form",
            academic_year="2026/2027",
            price_amount=300000,
        )
        draft = svc.create(payload)
        db_session.commit()
        assert draft.status == AdmissionFormStatus.draft

        active_forms = svc.list_active_for_school(school.id)
        assert all(f.id != draft.id for f in active_forms)


class TestAdmissionFormUpdate:
    def test_update_form(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormUpdate(title="Updated Title")
        updated = svc.update(admission_form_with_price, payload)
        db_session.commit()

        assert updated.title == "Updated Title"

    def test_update_price(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormUpdate(price_amount=750000)
        svc.update(admission_form_with_price, payload)
        db_session.commit()

        new_amount = svc.get_price_amount(admission_form_with_price)
        assert new_amount == 750000


class TestAdmissionFormLifecycle:
    def test_activate_form(self, db_session, school):
        svc = AdmissionFormService(db_session)
        payload = AdmissionFormCreate(
            school_id=school.id,
            title="Activation Test",
            academic_year="2025/2026",
            price_amount=400000,
        )
        form = svc.create(payload)
        db_session.flush()
        assert form.status == AdmissionFormStatus.draft

        activated = svc.activate(form)
        db_session.commit()
        assert activated.status == AdmissionFormStatus.active

    def test_close_form(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        closed = svc.close(admission_form_with_price)
        db_session.commit()
        assert closed.status == AdmissionFormStatus.closed

    def test_check_availability_active(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        assert svc.check_availability(admission_form_with_price) is True

    def test_check_availability_closed(self, db_session, admission_form_with_price):
        admission_form_with_price.status = AdmissionFormStatus.closed
        db_session.commit()
        svc = AdmissionFormService(db_session)
        assert svc.check_availability(admission_form_with_price) is False

    def test_check_availability_max_reached(self, db_session, admission_form_with_price):
        admission_form_with_price.max_submissions = 5
        admission_form_with_price.current_submissions = 5
        db_session.commit()
        svc = AdmissionFormService(db_session)
        assert svc.check_availability(admission_form_with_price) is False

    def test_get_price_amount(self, db_session, admission_form_with_price):
        svc = AdmissionFormService(db_session)
        amount = svc.get_price_amount(admission_form_with_price)
        assert amount == 500000
