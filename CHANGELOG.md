# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- [Security] Upgrade `python-jose` to `PyJWT>=2.8.0` — resolves CVE-2024-33663 and CVE-2024-33664 (JWT algorithm confusion allowing signature bypass); `jwt.encode()` / `jwt.decode()` updated to PyJWT 2.x API; `JWTError` replaced with `jwt.exceptions.InvalidTokenError` (`app/services/auth_flow.py`, `pyproject.toml`) (PR #46)
- [Security] SVG sanitizer extended to block additional XSS vectors — `<use>`, `<animate>`, `<animateTransform>`, `<animateMotion>`, `<set>`, `<foreignObject>`, `<script>`, and `<iframe>` elements now blocked; `href` and `xlink:href` attributes stripped from all elements (SVG use-href XSS); CSS `url()` expressions stripped from `style` attributes (`app/services/branding_assets.py`) (PR #45)
- [Security] Payment callback endpoint now verifies transaction with Paystack before marking as paid — `/payments/callback` calls `gateway.verify_transaction(reference)` before `handle_payment_success()`; non-success or unverified transactions rejected with HTTP 400, preventing payment bypass without paying (`app/api/payments.py`) (PR #43)
- [Security] Form purchase endpoint restricted to `parent` role — `require_role('parent')` dependency added to the purchase route in `app/api/applications.py`; other authenticated roles can no longer initiate purchases (PR #41)
- [Security] CSRF cookie `httponly` flag corrected to `False` — the double-submit CSRF pattern requires the cookie to be JS-readable; the previous `httponly=True` silently broke the auto-injection mechanism in `base.html` (`app/middleware/csrf.py`) (PR #41)
- [Security] `ward_gender` parameter now validated against `Literal['male', 'female', 'other']` — invalid values return HTTP 400 instead of being passed through unchecked (`app/web/parent/applications.py`) (PR #41)
- [Security] Hardcoded `postgresql://postgres:postgres@localhost/starter` default removed from `DATABASE_URL` — application now raises `ValueError` at startup if the environment variable is absent, preventing accidental use of development credentials in production (`app/config.py`) (PR #41)
- [Security] `SchoolPublicRead` schema introduced — bank account number, bank code, Paystack subaccount code, and commission rate excluded from public school API responses (`GET /schools`, `GET /schools/{id}`); admin-only endpoints retain full `SchoolRead` (`app/schemas/school.py`) (PR #33)
- [Security] School admin cross-school IDOR on applications fixed — detail and review handlers in `app/web/school/applications.py` now verify the application's `school_id` matches the authenticated admin's school; mismatched school returns 403 (PR #34)
- [Security] `password_hash` field removed from `UserCredentialCreate` and `UserCredentialUpdate` schemas — replaced with a plaintext `password` field hashed in the service layer before storage, preventing a compromised admin from injecting a known hash directly (`app/schemas/auth.py`) (PR #35)
- [Security] Audit log poisoning via `X-Actor-Id`/`X-Actor-Type` headers fixed — `log_request()` in `app/services/audit.py` now reads actor identity from `request.state` (set by auth middleware) rather than client-supplied headers; header values only accepted from IPs in the configured `INTERNAL_SERVICE_IPS` allow-list (PR #36)
- [Security] Raw exception messages no longer leaked in redirect URL query strings — generic `?error=An+unexpected+error+occurred` replaces f-string exception interpolation in `app/web/file_uploads.py`, `app/web/parent/applications.py`, and `app/web/school/applications.py`; full exception detail logged server-side via `logger.exception()` (PR #37)
- [Security] WebSocket auth now validates session revocation — `_authenticate_ws()` in `app/api/ws.py` performs a database session lookup after JWT decode, matching the session-validity check in `require_user_auth`; revoked sessions are rejected immediately rather than at token expiry (PR #38)
- [Security] Mass assignment risk in `PATCH /auth/me` eliminated — generic `setattr` loop over request payload replaced with explicit field assignments for `first_name`, `last_name`, and `phone_number` only; any other fields in the payload are ignored (`app/api/auth_flow.py`) (PR #39)
- [Security] School forms IDOR regression fixed — `edit_form_submit`, `activate_form`, and `close_form` POST handlers in `app/web/school/forms.py` now verify `form.school_id` matches the authenticated admin's school before applying mutations; previously only GET handlers had the ownership check (PR #40)
- [Security] Billing API router now requires `admin` role — previously any authenticated user could create, modify, and delete billing records; `billing_router` dependency changed from `require_user_auth` to `require_role('admin')` in `app/main.py` (PR #28)
- [Security] RBAC API router now requires `admin` role — previously any authenticated user could assign roles (including `platform_admin`) to themselves; `rbac_router` dependency changed from `require_user_auth` to `require_role('admin')` in `app/main.py` (PR #28)
- [Security] Scheduler API now requires `admin` role and validates task names against an explicit allowlist — `scheduler_router` changed to `require_role('admin')`; `enqueue_task()` in `app/services/scheduler.py` now raises `ValueError` for task names outside `ALLOWED_TASK_NAMES`, preventing arbitrary Celery task injection by authenticated users (PR #29)
- [Security] `GET /logout` route now requires authentication — unauthenticated CSRF-style forced-logout via `<img src="/logout">` is no longer possible; `require_web_auth` added as a dependency to the logout handler in `app/web/public.py` (PR #30)
- [Security] Web logout now revokes the server-side session — the `refresh_token` cookie is read and `AuthFlow.logout()` is called before cookies are deleted, so captured tokens cannot be reused after logout (`app/web/public.py`) (PR #30)
- [Security] Payment `callback_url` parameter now validated before being passed to Paystack — only relative paths starting with `/` or absolute URLs matching the configured `APP_URL` host are accepted; external URLs raise `ValueError`, preventing payment redirect hijacking (`app/services/application.py`) (PR #31)
- [Security] File upload and delete operations now enforce entity ownership — `delete()` verifies `uploaded_by` matches the current user (or caller has admin role); `create()`/`upload()` validates `entity_type` against an allowlist and checks caller owns `entity_id`; unauthorised access raises `PermissionError` (`app/services/file_uploads.py`) (PR #32)
- [Security] TOTP replay attack prevented — after successful TOTP verification, the code is stored in Redis with a 30-second TTL (keyed by `person_id:code`); reuse of the same code within the same window is rejected, preventing session takeover via intercepted OTPs (`app/services/auth_flow.py`) (PR #24)
- [Security] IDOR in parent application detail fixed — `application_detail` endpoint (`app/web/parent/applications.py`) now verifies `application.parent_id` matches the logged-in parent before returning data; IDOR attempts logged at WARNING level (PR #15)
- [Security] Purchase page now validates form is published — `purchase_page` and `purchase_submit` in `app/web/parent/applications.py` redirect to `/schools?error=Form+not+available` (303) when `form.status != AdmissionFormStatus.active`, preventing access to draft or closed forms (PR #15)
- [Security] HTML injection in password reset email fixed — `html.escape()` applied to `person_name` and `reset_link` before interpolation into the HTML body, preventing XSS via a malicious first name (PR #14)
- [Security] Rate limiter now validates `X-Forwarded-For` against a `TRUSTED_PROXIES` env var (comma-separated IP/CIDR list; default empty = no proxy headers trusted) — prevents header spoofing to bypass rate limits (`app/middleware/rate_limit.py`) (PR #11)
- [Security] `/metrics` endpoint now requires a `Bearer` token matching `METRICS_TOKEN` env var; returns 403 if absent or incorrect (PR #12)
- [Security] `/health/ready` endpoint no longer leaks raw exception messages — catches errors and returns a generic "Service unavailable" response (PR #12)
- [Security] Login failure handler no longer logs the user's email address (PII removed from `app/web/public.py`) (PR #12)
- [Security] `/register/parent` and `/register/school` paths added to the rate-limited route list alongside existing `/auth/` paths (PR #12)
- [Security] `change_password` endpoint now enforces minimum password strength via `_validate_password_strength()` — prevents weak passwords being set through the API (`app/api/auth_flow.py`) (PR #10)
- [Security] Login cookie `secure` flag now driven by `REFRESH_COOKIE_SECURE` env var — `_refresh_cookie_secure()` in `app/services/auth_flow.py` reads the variable and returns `True` for values `true`/`1`/`yes` (case-insensitive); both web login handlers (`app/web/auth.py`, `app/web/public.py`) now pass `secure=_refresh_cookie_secure(db)` to every `set_cookie()` call for `access_token` and `refresh_token` (PR #9)
- [Security] Password minimum length of 8 characters now enforced in `register_parent`, `register_school_admin`, and password-change service methods via `_validate_password_strength()` helper; raises `ValueError` on violation (PR #5)
- [Security] Rate limiter now fails **closed** on Redis outage — an in-memory sliding-window fallback (5 req / 60 s per IP, using `collections.deque`) enforces brute-force limits on login, MFA, and registration even when Redis is unavailable (PR #7)
- [Security] WebSocket JWT access token moved from URL query parameter to `Sec-WebSocket-Protocol` subprotocol header — prevents token leakage in server access logs, browser history, and `Referer` headers (PR #6)
- [Security] Fix open redirect in admin login — `next` URL parameter now validated to require a leading `/` and no `://`; defaults to `/admin` if invalid (PR #4)
- [Security] Paystack webhook endpoint now returns HTTP 503 when `PAYSTACK_SECRET_KEY` is unset instead of processing unsigned events (PR #3)
- [Security] Upgrade `cryptography` to `>=44.0.1` — resolves CVE-2024-12797 (TLS client certificate validation bypass) and several CVEs in the 42–43 range (PR #2)
- [Security] Upgrade `jinja2` to `>=3.1.6` — resolves CVE-2024-56201 (sandbox escape via crafted filenames) and CVE-2024-56326 (sandbox bypass via `__init__` override) (PR #1)

### Fixed
- [Fixed] N+1 queries eliminated in all 3 list views — `AdmissionFormService.list_for_school()` now eager-loads `Price` records via `selectinload`; `ApplicationService.list_for_parent()` eager-loads `admission_form → school`; `ApplicationService.list_for_school()` eager-loads `admission_form` and `parent`; reduces per-request query count from O(n) to O(1) for paginated lists (`app/services/`) (PR #48)
- [Fixed] Raw exception messages removed from `app/web/file_uploads.py` template error responses — generic `'An unexpected error occurred. Please try again.'` shown to users; full exception detail preserved in `logger.exception()` calls (PR #49)
- [Fixed] Application number generation now retries on unique key collision — `_generate_application_number()` in `app/services/application.py` attempts up to 5 new tokens on `IntegrityError`; raises `RuntimeError` after 5 consecutive failures, preventing silent data corruption under high load (PR #42)
- [Fixed] `boto3` declared as optional dependency under `[tool.poetry.extras] s3 = ["boto3"]` — deployments with `STORAGE_BACKEND=s3` no longer crash with `ImportError` on startup; install with `pip install .[s3]` or `poetry install -E s3` (`pyproject.toml`) (PR #25)
- [Fixed] `app/api/__init__.py` and `app/schemas/__init__.py` added — both subdirectories were missing `__init__.py` unlike all other `app/` sub-packages, causing inconsistent namespace package behaviour (PR #26)
- [Fixed] `S3Storage.exists()` now catches `botocore.ClientError` specifically — 404/NoSuchKey returns `False`; all other `ClientError` variants log a warning and re-raise so misconfigurations and permission errors surface (`app/services/storage.py`) (PR #20)
- [Fixed] `send_email()` SMTP connection now wrapped in `try/finally` — `server.quit()` is always called even when the send fails, preventing connection leaks (`app/services/email.py`) (PR #20)

### Removed
- [Removed] Dead `ListResponseMixin` class removed — it was never referenced outside its own definition and provided an unimplemented abstract method; removed from `app/services/auth_flow.py` along with its import (PR #22)

### Added
- [Added] Pagination added to `GET /applications/my` and `GET /applications/school/{id}` — `limit` and `offset` query parameters prevent unbounded result sets; defaults: `my_applications` limit=50 (max 500), `school_applications` limit=100 (max 1000) (`app/api/applications.py`) (PR #47)
- [Added] Unit tests for `PaystackGateway` service — covers `create_subaccount`, `update_subaccount`, `initialize_transaction`, `verify_transaction`, `validate_webhook_signature`, and `is_configured` guard path (`tests/test_payment_gateway_service.py`) (PR #19)
- [Added] Unit tests for `settings_seed` and `scheduler_config` modules (`tests/test_settings_seed.py`, `tests/test_scheduler_config.py`) — happy path, error cases, and mocked DB fixtures (PR #21)
- Security headers middleware (CSP, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy)
- CORS middleware with configurable origins via `CORS_ORIGINS` env var
- Redis-backed sliding window rate limiting on auth endpoints (login, password-reset, MFA, register)
- Readiness health check at `/health/ready` (verifies DB + Redis connectivity)
- Gunicorn production config (`gunicorn.conf.py`) with worker tuning
- Centralized Jinja2 templates with custom filters (sanitize_html, nl2br, format_date, format_currency, timeago)
- Structured error responses with `request_id` correlation in every error payload
- Reusable `paginate()` helper for standardized paginated responses
- Startup configuration validation with warnings for missing secrets
- `TimestampMixin` for DRY `created_at`/`updated_at` columns
- CSRF auto-injection (meta tag + JS for forms, HTMX, and fetch)
- Token refresh manager (auto-refreshes JWT every 10 minutes)
- Form double-submit protection
- Query-parameter toast consumer (?success=, ?error=, etc.)
- `window.showToast()` global helper
- CLAUDE.md project reference with architecture and rules
- `.claude/rules/` with security, services, and templates patterns
- Makefile with 20 targets (lint, format, type-check, test, migrate, docker)
- Ruff, mypy, and coverage configuration in pyproject.toml
- Pre-commit hooks (ruff, detect-secrets, trailing whitespace)
- GitHub Actions CI pipeline (lint, type-check, test, security, pre-commit, docker build)
- `.dockerignore` for optimized Docker builds

### Changed
- [Changed] `get_school_for_admin()` shared helper extracted into `app/web/schoolnet_deps.py` — duplicate `_get_school_for_admin()` in `app/web/school/forms.py` and `_get_school_id()` in `app/web/school/applications.py` replaced with a single utility calling `SchoolService(db).get_schools_for_owner()`; callers that previously received a bare UUID now extract `.school_id` from the returned `School` object (PR #54)
- [Changed] `app/services/billing.py` (1073 lines, 13 classes) split into domain sub-modules under `app/services/billing/` — 7 new files: `products.py`, `prices.py`, `customers.py`, `invoices.py`, `subscriptions.py`, `payments.py`, `webhooks.py`; `__init__.py` re-exports all public classes and singletons so existing `from app.services.billing import X` imports continue to work unchanged (PR #53)
- [Changed] Migrated remaining 54 `db.query()` legacy calls to SQLAlchemy 2.0 `select()` + `db.scalars()`/`db.scalar()` across 12 files — `auth_flow.py`, `billing.py`, `auth.py`, `rbac.py`, `domain_settings.py`, `api/auth_flow.py`, `branding.py`, `person.py`, `scheduler.py`, `scheduler_config.py`, `audit.py`, `web_home.py` (`app/services/` + `app/api/`) (PR #52)
- [Changed] All 87 `db.commit()` calls in service files replaced with `db.flush()` — `billing.py` (×37), `auth.py` (×13), `rbac.py` (×12), `auth_flow.py` (×11), `domain_settings.py` (×4), `person.py` (×3), `audit.py` (×3), `scheduler.py` (×3), `branding.py` (×1); routes and Celery tasks now own transaction commit boundaries (PR #51)
- [Changed] `type: ignore[assignment]` suppressions removed from `app/schemas/billing.py` — `use_enum_values=True` added to `model_config` of `PriceRead`, `SubscriptionRead`, `InvoiceRead`, `PaymentIntentRead`, `WebhookEventRead` so enum fields type-check cleanly (PR #50)
- [Changed] Inline imports moved to module top-level in `app/api/applications.py` (3 function-body `from app.models.school import ...`) and `app/api/payments.py` (`import json` inside handler) (PR #49)
- [Changed] Replaced abandoned `passlib` with direct `bcrypt>=4.0.0` — `passlib` is unmaintained and incompatible with `bcrypt 5.0.0`; password hashing now uses `bcrypt.hashpw()` / `bcrypt.checkpw()` directly; `_hash_password()` and `_verify_password()` updated accordingly (`app/services/auth_flow.py`, `pyproject.toml`) (PR #44)
- [Changed] Global `ignore_missing_imports = true` in `[tool.mypy]` replaced with per-module `[[tool.mypy.overrides]]` sections for stub-less packages (`boto3`, `botocore`, `cachetools`, `redis`, `jose`) — narrows suppression scope so type errors in unrelated packages are no longer silently hidden (`pyproject.toml`) (PR #27)
- [Changed] `types-cachetools` and `types-redis` added to dev dependencies — enables mypy to type-check `cachetools.TTLCache` (rate limiter) and Redis client calls without `ignore_missing_imports` workarounds (`pyproject.toml`) (PR #26)
- [Changed] OpenTelemetry instrumentation packages (`opentelemetry-instrumentation-fastapi`, `-sqlalchemy`, `-celery`) upgraded from pre-release `0.47b0` to stable release (`pyproject.toml`) (PR #26)
- [Changed] Refactored `seed_auth_settings()` in `app/services/settings_seed.py` — extracted 2–3 private setting-group builder helpers to reduce function body below 80 lines (PR #21)
- [Changed] Applied `ruff format` cleanup across `app/` — eliminates remaining E501 line-length violations in `app/schemas/billing.py` and `app/services/application.py` (PR #22)
- [Changed] Added `logger.debug()` call in `WebSocketManager.send_to_person()` on failed sends — outbound message failures are now traceable (`app/services/websocket_manager.py`) (PR #22)
- [Changed] Migrated all `db.query()` calls (SQLAlchemy 1.x style) to `select()` + `db.scalars()` / `db.scalar()` (SQLAlchemy 2.0) across 10 service files — `billing.py`, `auth_flow.py`, `auth.py`, `rbac.py`, `domain_settings.py` and 5 others (49 total occurrences) (PR #18)
- [Changed] Deleted stale `app/services/query_utils.py` — migrated 8 service files (`audit.py`, `auth.py`, `billing.py`, `domain_settings.py`, `person.py`, `rbac.py`, `scheduler.py`, `scheduler_config.py`) to import `apply_ordering`, `apply_pagination`, and `validate_enum` from `app.services.common` (PR #16)
- [Changed] Refactored `app/services/application.py` `initiate_purchase()` — extracted `_create_billing_records()` and `_init_paystack_or_dev()` as private helpers, reducing function body from ~125 lines to ~40 lines (PR #17)
- SQLAlchemy 2.0 pattern in `main.py`: `db.query()` → `select()` + `db.scalars()`
- Error responses now include `request_id` field for debugging

## [0.1.0] - 2026-02-12

### Added
- Initial starter template with authentication, RBAC, audit, and scheduler
- JWT-based auth with MFA (TOTP, SMS, Email)
- Celery workers with database-backed Beat scheduler
- Prometheus metrics and OpenTelemetry tracing
- JSON structured logging
