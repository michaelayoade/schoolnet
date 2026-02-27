# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
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
- SQLAlchemy 2.0 pattern in `main.py`: `db.query()` → `select()` + `db.scalars()`
- Error responses now include `request_id` field for debugging

## [0.1.0] - 2026-02-12

### Added
- Initial starter template with authentication, RBAC, audit, and scheduler
- JWT-based auth with MFA (TOTP, SMS, Email)
- Celery workers with database-backed Beat scheduler
- Prometheus metrics and OpenTelemetry tracing
- JSON structured logging
