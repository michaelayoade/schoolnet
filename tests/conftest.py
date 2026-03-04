import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from types import ModuleType

import pytest
import asyncio
import httpx
from jose import jwt
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

# In this execution environment, AnyIO thread utilities hang. Starlette/FastAPI
# runs sync endpoints via `run_in_threadpool()`, so patch it to execute inline.
# This is acceptable for tests where handlers are fast and deterministic.
import starlette.concurrency
import fastapi.concurrency
import starlette.routing
import fastapi.routing
import fastapi.dependencies.utils as fastapi_deps_utils
import anyio.to_thread


async def _run_in_threadpool(func, *args, **kwargs):
    return func(*args, **kwargs)


starlette.concurrency.run_in_threadpool = _run_in_threadpool  # type: ignore[assignment]
fastapi.concurrency.run_in_threadpool = _run_in_threadpool  # type: ignore[assignment]
starlette.routing.run_in_threadpool = _run_in_threadpool  # type: ignore[assignment]
fastapi.routing.run_in_threadpool = _run_in_threadpool  # type: ignore[assignment]
fastapi_deps_utils.run_in_threadpool = _run_in_threadpool  # type: ignore[assignment]


async def _run_sync_inline(func, *args, **kwargs):
    # anyio.to_thread.run_sync(..., limiter=...) is used by FastAPI to wrap sync
    # context managers. We execute inline and ignore limiter.
    kwargs.pop("limiter", None)
    return func(*args, **kwargs)


anyio.to_thread.run_sync = _run_sync_inline  # type: ignore[assignment]


# Create a test engine BEFORE any app imports
_test_engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


# Create a mock for the app.db module that uses our test engine
class TestBase(DeclarativeBase):
    pass


_TestSessionLocal = sessionmaker(bind=_test_engine, autoflush=False, autocommit=False)


# Create TimestampMixin for test models
class TimestampMixin:
    """Mixin that adds created_at / updated_at columns to any model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# Create a mock db module
mock_db_module = ModuleType('app.db')
mock_db_module.Base = TestBase
mock_db_module.TimestampMixin = TimestampMixin
mock_db_module.SessionLocal = _TestSessionLocal
mock_db_module.get_engine = lambda: _test_engine

# Also mock app.config to prevent .env loading
mock_config_module = ModuleType('app.config')


class MockSettings:
    database_url = "sqlite+pysqlite:///:memory:"
    redis_url = "redis://localhost:6379/0"
    secret_key = "test-secret-key"
    db_pool_size = 5
    db_max_overflow = 10
    db_pool_timeout = 30
    db_pool_recycle = 1800
    avatar_upload_dir = "static/avatars"
    avatar_max_size_bytes = 2 * 1024 * 1024
    avatar_allowed_types = "image/jpeg,image/png,image/gif,image/webp"
    avatar_url_prefix = "/static/avatars"
    brand_name = "Starter Template"
    brand_tagline = "FastAPI starter"
    brand_logo_url = None
    cors_origins = ""
    storage_backend = "local"
    storage_local_dir = "/tmp/test_uploads"
    storage_url_prefix = "/static/uploads"
    s3_bucket = ""
    s3_region = ""
    s3_access_key = ""
    s3_secret_key = ""
    s3_endpoint_url = ""
    upload_max_size_bytes = 10 * 1024 * 1024
    upload_allowed_types = "image/jpeg,image/png,image/gif,image/webp,application/pdf,text/plain,text/csv"
    branding_upload_dir = "static/branding"
    branding_max_size_bytes = 5 * 1024 * 1024
    branding_allowed_types = "image/jpeg,image/png"
    branding_url_prefix = "/static/branding"
    paystack_secret_key = ""
    paystack_public_key = ""
    schoolnet_commission_rate = 1000
    schoolnet_currency = "NGN"


mock_config_module.settings = MockSettings()
mock_config_module.Settings = MockSettings
mock_config_module.validate_settings = lambda s: []

# Insert mocks before any app imports
sys.modules['app.config'] = mock_config_module
sys.modules['app.db'] = mock_db_module

# Set environment variables
os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["TOTP_ENCRYPTION_KEY"] = "QLUJktsTSfZEbST4R-37XmQ0tCkiVCBXZN2Zt053w8g="
os.environ["TOTP_ISSUER"] = "StarterTemplate"
os.environ["SEED_SETTINGS_ON_STARTUP"] = "false"

# Now import the models - they'll use our mocked db module
from app.models.person import Person
from app.models.auth import UserCredential, Session as AuthSession, SessionStatus
from app.models.rbac import Role, Permission, RolePermission, PersonRole
from app.models.audit import AuditEvent, AuditActorType
from app.models.domain_settings import DomainSetting, SettingDomain
from app.models.scheduler import ScheduledTask, ScheduleType
from app.models.file_upload import FileUpload, FileUploadStatus
from app.models.notification import Notification, NotificationType
from app.models.ward import Ward  # noqa: F401 — imported for table creation
from app.models.billing import (
    Product,
    Price,
    PriceType,
    BillingScheme,
    RecurringInterval,
    Customer,
    Subscription,
    SubscriptionStatus,
    SubscriptionItem,
    Invoice,
    InvoiceStatus,
    InvoiceItem,
    PaymentMethod,
    PaymentMethodType,
    PaymentIntent,
    PaymentIntentStatus,
    UsageRecord,
    UsageAction,
    Coupon,
    CouponDuration,
    Discount,
    Entitlement,
    EntitlementValueType,
    WebhookEvent,
    WebhookEventStatus,
)
from app.models.school import (
    School,
    SchoolStatus,
    SchoolType,
    SchoolCategory,
    SchoolGender,
    AdmissionForm,
    AdmissionFormStatus,
    Application,
    ApplicationStatus,
    Rating,
)

# Create all tables
TestBase.metadata.create_all(_test_engine)

# Re-export Base for compatibility
Base = TestBase


@pytest.fixture(scope="session")
def engine():
    return _test_engine


@pytest.fixture()
def db_session(engine):
    """Create a database session for testing.

    Uses the same connection as the StaticPool engine to ensure
    all operations see the same data.
    """
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex}@example.com"


@pytest.fixture()
def person(db_session):
    person = Person(
        first_name="Test",
        last_name="User",
        email=_unique_email(),
    )
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)
    return person


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    # Environment variables are set at module level above
    # This fixture ensures they're available for each test and keeps Celery
    # task dispatch as a no-op in the test environment.
    from app.tasks import notifications as notification_tasks

    monkeypatch.setattr(
        notification_tasks.send_notification_email_task,
        "delay",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        notification_tasks.send_application_status_email_task,
        "delay",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        notification_tasks.send_payment_receipt_email_task,
        "delay",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        notification_tasks.send_new_application_email_task,
        "delay",
        lambda *args, **kwargs: None,
    )


# ============ FastAPI Test Client Fixtures ============


@pytest.fixture()
def client(db_session):
    """Create a test client with database dependency override."""
    from app.main import app
    from app.api.deps import get_db as api_get_db
    from app.services.auth_dependencies import _get_db as auth_deps_get_db
    from app.services.settings_seed import (
        seed_audit_settings,
        seed_auth_settings,
        seed_billing_settings,
        seed_scheduler_settings,
    )

    class SyncASGIClient:
        def __init__(self, loop: asyncio.AbstractEventLoop, async_client: httpx.AsyncClient):
            self._loop = loop
            self._client = async_client

        @property
        def cookies(self):
            return self._client.cookies

        def request(self, method: str, url: str, **kwargs):
            return self._loop.run_until_complete(
                self._client.request(method, url, **kwargs)
            )

        def get(self, url: str, **kwargs):
            return self.request("GET", url, **kwargs)

        def post(self, url: str, **kwargs):
            return self.request("POST", url, **kwargs)

        def put(self, url: str, **kwargs):
            return self.request("PUT", url, **kwargs)

        def patch(self, url: str, **kwargs):
            return self.request("PATCH", url, **kwargs)

        def delete(self, url: str, **kwargs):
            return self.request("DELETE", url, **kwargs)

    def override_get_db():
        # Starlette's TestClient runs the app in a different thread; sharing a single
        # SQLAlchemy Session object across threads can hang. Use a per-request session
        # bound to the same StaticPool engine so data remains shared.
        Session = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
        session = Session()
        try:
            yield session
        finally:
            session.close()

    # Override shared db dependencies
    app.dependency_overrides[api_get_db] = override_get_db
    app.dependency_overrides[auth_deps_get_db] = override_get_db
    app.state.disable_rate_limit = True

    # Ensure default settings exist for routes that expect them.
    seed_auth_settings(db_session)
    seed_audit_settings(db_session)
    seed_scheduler_settings(db_session)
    seed_billing_settings(db_session)

    # Avoid Starlette TestClient: `anyio.from_thread.start_blocking_portal()` hangs in
    # this execution environment. Use httpx.AsyncClient + a dedicated event loop instead.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    lifespan_cm = app.router.lifespan_context(app)
    loop.run_until_complete(lifespan_cm.__aenter__())
    async_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )
    try:
        yield SyncASGIClient(loop, async_client)
    finally:
        loop.run_until_complete(async_client.aclose())
        loop.run_until_complete(lifespan_cm.__aexit__(None, None, None))
        loop.close()
        asyncio.set_event_loop(None)

    app.dependency_overrides.clear()
    app.state.disable_rate_limit = False


def _create_access_token(person_id: str, session_id: str, roles: list[str] = None, scopes: list[str] = None) -> str:
    """Create a JWT access token for testing."""
    secret = os.getenv("JWT_SECRET", "test-secret")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=15)
    payload = {
        "sub": person_id,
        "session_id": session_id,
        "roles": roles or [],
        "scopes": scopes or [],
        "typ": "access",
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture()
def auth_session(db_session, person):
    """Create an authenticated session for a person."""
    session = AuthSession(
        person_id=person.id,
        token_hash="test-token-hash",
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture()
def auth_token(person, auth_session):
    """Create a valid JWT token for authenticated requests."""
    # Default authenticated user (non-admin, no special scopes).
    return _create_access_token(str(person.id), str(auth_session.id), roles=["user"])


@pytest.fixture()
def auth_headers(auth_token):
    """Return authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture()
def admin_role(db_session):
    """Create an admin role."""
    role = db_session.query(Role).filter(Role.name == "admin").first()
    if role:
        return role
    role = Role(name="admin", description="Administrator role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture()
def admin_person(db_session, admin_role):
    """Create a person with admin role."""
    person = Person(
        first_name="Admin",
        last_name="User",
        email=_unique_email(),
    )
    db_session.add(person)
    db_session.commit()
    db_session.refresh(person)

    # Assign admin role
    person_role = PersonRole(person_id=person.id, role_id=admin_role.id)
    db_session.add(person_role)
    db_session.commit()

    return person


@pytest.fixture()
def admin_session(db_session, admin_person):
    """Create an authenticated session for admin."""
    session = AuthSession(
        person_id=admin_person.id,
        token_hash="admin-token-hash",
        status=SessionStatus.active,
        ip_address="127.0.0.1",
        user_agent="pytest",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture()
def admin_token(admin_person, admin_session):
    """Create a valid JWT token for admin requests."""
    return _create_access_token(
        str(admin_person.id),
        str(admin_session.id),
        roles=["admin"],
        scopes=["audit:read", "audit:*"],
    )


@pytest.fixture()
def admin_headers(admin_token):
    """Return authorization headers for admin requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture()
def user_credential(db_session, person):
    """Create a user credential for testing."""
    from app.services.auth_flow import hash_password

    credential = UserCredential(
        person_id=person.id,
        username=f"testuser_{uuid.uuid4().hex[:8]}",
        password_hash=hash_password("testpassword123"),
        is_active=True,
    )
    db_session.add(credential)
    db_session.commit()
    db_session.refresh(credential)
    return credential


@pytest.fixture()
def role(db_session):
    """Create a test role."""
    role = Role(name=f"test_role_{uuid.uuid4().hex[:8]}", description="Test role")
    db_session.add(role)
    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture()
def permission(db_session):
    """Create a test permission."""
    perm = Permission(
        key=f"test:permission:{uuid.uuid4().hex[:8]}",
        description="Test permission",
    )
    db_session.add(perm)
    db_session.commit()
    db_session.refresh(perm)
    return perm


@pytest.fixture()
def audit_event(db_session, person):
    """Create a test audit event."""
    event = AuditEvent(
        actor_id=str(person.id),
        actor_type=AuditActorType.user,
        action="test_action",
        entity_type="test_entity",
        entity_id=str(uuid.uuid4()),
        is_success=True,
        status_code=200,
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)
    return event


@pytest.fixture()
def domain_setting(db_session):
    """Create a test domain setting."""
    setting = DomainSetting(
        domain=SettingDomain.auth,
        key=f"test_setting_{uuid.uuid4().hex[:8]}",
        value_text="test_value",
    )
    db_session.add(setting)
    db_session.commit()
    db_session.refresh(setting)
    return setting


@pytest.fixture()
def scheduled_task(db_session):
    """Create a test scheduled task."""
    task = ScheduledTask(
        name=f"test_task_{uuid.uuid4().hex[:8]}",
        task_name="app.tasks.test_task",
        schedule_type=ScheduleType.interval,
        interval_seconds=300,
        enabled=True,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


# ============ Billing Fixtures ============


@pytest.fixture()
def billing_product(db_session):
    """Create a test billing product."""
    product = Product(name=f"Product {uuid.uuid4().hex[:8]}", description="Test product")
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return product


@pytest.fixture()
def billing_price(db_session, billing_product):
    """Create a test billing price."""
    price = Price(
        product_id=billing_product.id,
        currency="usd",
        unit_amount=1999,
        type=PriceType.recurring,
        billing_scheme=BillingScheme.per_unit,
        recurring_interval=RecurringInterval.month,
        recurring_interval_count=1,
        lookup_key=f"price_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(price)
    db_session.commit()
    db_session.refresh(price)
    return price


@pytest.fixture()
def billing_customer(db_session):
    """Create a test billing customer."""
    customer = Customer(
        name="Test Customer",
        email=f"customer-{uuid.uuid4().hex[:8]}@example.com",
        currency="usd",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return customer


@pytest.fixture()
def billing_subscription(db_session, billing_customer):
    """Create a test billing subscription."""
    sub = Subscription(
        customer_id=billing_customer.id,
        status=SubscriptionStatus.active,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


@pytest.fixture()
def billing_subscription_item(db_session, billing_subscription, billing_price):
    """Create a test subscription item."""
    si = SubscriptionItem(
        subscription_id=billing_subscription.id,
        price_id=billing_price.id,
        quantity=1,
    )
    db_session.add(si)
    db_session.commit()
    db_session.refresh(si)
    return si


@pytest.fixture()
def billing_coupon(db_session):
    """Create a test coupon."""
    coupon = Coupon(
        name="Test Coupon",
        code=f"SAVE{uuid.uuid4().hex[:6].upper()}",
        percent_off=20,
        duration=CouponDuration.once,
    )
    db_session.add(coupon)
    db_session.commit()
    db_session.refresh(coupon)
    return coupon


# ============ SchoolNet Fixtures ============


@pytest.fixture()
def school_owner(db_session):
    """Create a person who owns a school."""
    p = Person(
        first_name="School",
        last_name="Owner",
        email=_unique_email(),
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def school(db_session, school_owner):
    """Create a test school."""
    s = School(
        owner_id=school_owner.id,
        name="Test Academy",
        slug=f"test-academy-{uuid.uuid4().hex[:6]}",
        school_type=SchoolType.primary,
        category=SchoolCategory.private,
        gender=SchoolGender.mixed,
        state="Lagos",
        city="Ikeja",
        status=SchoolStatus.active,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def parent_person(db_session):
    """Create a parent person for testing."""
    p = Person(
        first_name="Parent",
        last_name="User",
        email=_unique_email(),
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def admission_form_with_price(db_session, school):
    """Create an admission form with associated product and price."""
    product = Product(
        name=f"{school.name} - Test Form",
        description="Test admission form",
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    price = Price(
        product_id=product.id,
        currency="NGN",
        unit_amount=500000,
        type=PriceType.one_time,
        is_active=True,
    )
    db_session.add(price)
    db_session.flush()

    form = AdmissionForm(
        school_id=school.id,
        product_id=product.id,
        price_id=price.id,
        title="2026 Admission",
        academic_year="2025/2026",
        status=AdmissionFormStatus.active,
        max_submissions=100,
        current_submissions=0,
    )
    db_session.add(form)
    db_session.commit()
    db_session.refresh(form)
    return form
