"""Tests for person service."""

import uuid

import pytest  # noqa: F401

from app.schemas.person import PersonCreate, PersonUpdate
from app.services import person as person_service


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


def test_create_person(db_session):
    """Test creating a person."""
    email = _unique_email()
    person = person_service.People(db_session).create(
        PersonCreate(
            first_name="John",
            last_name="Doe",
            email=email,
        ),
    )
    assert person.first_name == "John"
    assert person.last_name == "Doe"
    assert person.email == email
    assert person.is_active is True


def test_get_person_by_id(db_session):
    """Test getting a person by ID."""
    svc = person_service.People(db_session)
    person = svc.create(
        PersonCreate(
            first_name="Jane",
            last_name="Smith",
            email=_unique_email(),
        ),
    )
    fetched = svc.get(str(person.id))
    assert fetched is not None
    assert fetched.id == person.id
    assert fetched.first_name == "Jane"


def test_list_people_filter_by_email(db_session):
    """Test listing people filtered by email."""
    svc = person_service.People(db_session)
    email = _unique_email()
    svc.create(
        PersonCreate(first_name="Alice", last_name="Test", email=email),
    )
    svc.create(
        PersonCreate(first_name="Bob", last_name="Other", email=_unique_email()),
    )

    results, total = svc.list(
        email=email,
        status=None,
        is_active=None,
        order_by="created_at",
        order_dir="asc",
        limit=10,
        offset=0,
    )
    assert total == 1
    assert len(results) == 1
    assert results[0].first_name == "Alice"


def test_list_people_filter_by_status(db_session):
    """Test listing people filtered by status."""
    svc = person_service.People(db_session)
    email1 = _unique_email()
    person1 = svc.create(
        PersonCreate(first_name="Active", last_name="User", email=email1),
    )
    email2 = _unique_email()
    person2 = svc.create(
        PersonCreate(first_name="Inactive", last_name="User", email=email2),
    )
    # Update second person to inactive
    svc.update(
        str(person2.id),
        PersonUpdate(status="inactive"),
    )

    # Query for person1 specifically with active status filter
    active_results, active_total = svc.list(
        email=email1,
        status="active",
        is_active=None,
        order_by="created_at",
        order_dir="asc",
        limit=100,
        offset=0,
    )
    assert active_total == 1
    assert len(active_results) == 1
    assert active_results[0].id == person1.id

    # Verify person2 is not returned when filtering for active
    inactive_as_active, inactive_total = svc.list(
        email=email2,
        status="active",
        is_active=None,
        order_by="created_at",
        order_dir="asc",
        limit=100,
        offset=0,
    )
    assert inactive_total == 0
    assert len(inactive_as_active) == 0


def test_list_people_active_only(db_session):
    """Test listing only active people."""
    svc = person_service.People(db_session)
    person = svc.create(
        PersonCreate(first_name="ToDelete", last_name="User", email=_unique_email()),
    )
    svc.delete(str(person.id))

    results, _ = svc.list(
        email=None,
        status=None,
        is_active=True,
        order_by="created_at",
        order_dir="asc",
        limit=100,
        offset=0,
    )
    ids = {p.id for p in results}
    assert person.id not in ids


def test_update_person(db_session):
    """Test updating a person."""
    svc = person_service.People(db_session)
    person = svc.create(
        PersonCreate(first_name="Original", last_name="Name", email=_unique_email()),
    )
    updated = svc.update(
        str(person.id),
        PersonUpdate(first_name="Updated", last_name="Person"),
    )
    assert updated.first_name == "Updated"
    assert updated.last_name == "Person"


def test_delete_person(db_session):
    """Test deleting a person."""
    svc = person_service.People(db_session)
    person = svc.create(
        PersonCreate(first_name="ToDelete", last_name="User", email=_unique_email()),
    )
    person_id = person.id
    svc.delete(str(person_id))

    # Verify person is deleted
    import pytest

    with pytest.raises(person_service.PersonNotFoundError) as exc_info:
        svc.get(str(person_id))
    assert "Person not found" in str(exc_info.value)


def test_list_people_pagination(db_session):
    """Test pagination of people list."""
    svc = person_service.People(db_session)
    # Create multiple people
    for i in range(5):
        svc.create(
            PersonCreate(
                first_name=f"Person{i}",
                last_name="Test",
                email=_unique_email(),
            ),
        )

    page1, page1_total = svc.list(
        email=None,
        status=None,
        is_active=None,
        order_by="created_at",
        order_dir="asc",
        limit=2,
        offset=0,
    )
    page2, page2_total = svc.list(
        email=None,
        status=None,
        is_active=None,
        order_by="created_at",
        order_dir="asc",
        limit=2,
        offset=2,
    )

    assert page1_total >= 5
    assert page2_total >= 5
    assert len(page1) == 2
    assert len(page2) == 2
    # Pages should have different people
    page1_ids = {p.id for p in page1}
    page2_ids = {p.id for p in page2}
    assert page1_ids.isdisjoint(page2_ids)
