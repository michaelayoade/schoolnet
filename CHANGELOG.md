# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
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

### Added
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
