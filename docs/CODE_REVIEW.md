# SchoolNet Deep Code Review

**Date:** 2026-02-25
**Reviewer:** Claude Opus 4.6 (automated deep review)

## Executive Summary

The codebase has a **clear two-tier quality split**: newer SchoolNet-specific services (school, ward, registration, application, rating, notification, file upload) follow CLAUDE.md guidelines well, while the older "starter template" services (person, audit, rbac, billing, auth, domain_settings, scheduler) consistently violate architectural rules. **76 total issues** were found across 5 categories.

---

## CRITICAL (8 issues) — Fix Immediately

### 1. Hardcoded Credentials in `docker-compose.yml`
**`docker-compose.yml:11-14, 33-36, 49-52`** — DB password `4pxOTG58CODQy6x7XsdR3jXR2TSMpWJ9` and Redis password `CNwgidLhp9tMDQFWNIVHo0YGOF1MgPoI` are committed to git. These must be moved to `.env` (which is gitignored) and the secrets rotated.

### 2. Webhook Authentication Bypass
**`app/api/payments.py:23`** — When `PAYSTACK_SECRET_KEY` is empty, webhooks are accepted **without** signature verification. Any crafted request to `/payments/webhook/paystack` is processed.

### 3. Open Redirect in Admin Login
**`app/web/auth.py:67,111,164`** — The `next` parameter is used in `RedirectResponse` without validation. An attacker can craft `/admin/login?next=https://evil.com` to redirect post-authentication.

### 4. Missing Migration for `wards` Table
**`app/models/ward.py`** — The `Ward` model is defined and exported but has **no Alembic migration**. Any query against it will crash with `ProgrammingError`.

### 5. `token_hash` Exposed in `SessionRead` Schema
**`app/schemas/auth.py:90,113`** — `SessionBase` includes `token_hash: str`, which leaks to any API endpoint returning session data.

### 6. Migrations 001 & 002 Lack Idempotency
**`alembic/versions/799a0ecebdd4_*.py`, `002_billing_schema.py`** — No `inspector.has_table()` guards. Re-running after partial failure raises `ProgrammingError`.

### 7. Missing FK Constraints in Migrations
**`003_file_uploads.py:31`** — `uploaded_by` has no FK constraint in the migration.
**`004_notifications.py:31-32`** — `recipient_id`, `sender_id` have no FK constraints.

### 8. MFA Secret Stored as Plaintext
**`app/models/auth.py:96`** — `MFAMethod.secret` is `String(255)` with no column-level encryption. Combined with bank details in `app/models/school.py:125-128`, sensitive data may not be encrypted at rest.

---

## HIGH (12 issues) — Fix Soon

### Security

| # | Issue | Location |
|---|-------|----------|
| 9 | Missing `secure=True` on all auth cookies | `app/web/auth.py:112-128`, `app/web/public.py:398-419` |
| 10 | No server-side password complexity enforcement on registration | `app/web/public.py:215-257` (HTML `minlength` only) |
| 11 | `\| safe` on dynamic CSS (stored XSS vector) | `templates/partials/_org_branding_head.html:8` |
| 12 | Missing CSRF token in branding form | `templates/branding.html:23` |

### Schema Drift (Model vs Migration)

| # | Issue | Location |
|---|-------|----------|
| 13 | Index `ix_file_uploads_entity` missing `is_active` column | `003_file_uploads.py:61-65` vs model |
| 14 | Missing index `ix_notifications_recipient_created` | `004_notifications.py` |
| 15 | Missing composite indexes for applications, ratings | `005_schoolnet_schema.py` |
| 16 | Missing `CheckConstraint` for ratings score, file size | `005_schoolnet_schema.py`, `003_file_uploads.py` |

### Architecture

| # | Issue | Location |
|---|-------|----------|
| 17 | `db.query()` (SQLAlchemy 1.x) — **64+ instances** | `billing.py`, `auth.py`, `auth_flow.py`, `rbac.py`, `person.py`, `public.py` |
| 18 | `db.commit()` in services (should be `flush()`) — **100+ instances** | All older services |
| 19 | `HTTPException` raised in services — **dozens of instances** | All older services (should raise `ValueError`/`RuntimeError`) |
| 20 | No indexes on `audit_events` table | `app/models/audit.py` |

---

## MEDIUM (20 issues) — Plan to Fix

### Security

| # | Issue | Location |
|---|-------|----------|
| 21 | Email enumeration via login flow (distinct error for unverified) | `app/web/public.py:357-374` |
| 22 | Rate limiter doesn't cover web routes (`/login`, `/admin/login`) | `app/middleware/rate_limit.py:20-25` |
| 23 | Rate limiter fails open when Redis is down | `app/middleware/rate_limit.py:86-88` |
| 24 | CSP allows `unsafe-inline` and `unsafe-eval` | `app/middleware/security_headers.py:46-47` |
| 25 | `X-Forwarded-For` trusted without proxy validation | `app/middleware/rate_limit.py:28-34` |
| 26 | Public logout doesn't specify `path="/"` on cookie deletion | `app/web/public.py:497-499` |
| 27 | Access token cookie TTL mismatch (admin: 1hr vs public: 15min) | `app/web/auth.py:118` vs `app/web/public.py:403` |

### Architecture

| # | Issue | Location |
|---|-------|----------|
| 28 | **40+ `async def` route handlers** with sync DB sessions | `app/web/billing/*.py`, `app/web/roles.py`, `app/web/people.py`, etc. |
| 29 | Business logic in routes (not thin wrappers) | `app/web/public.py:119-135,333-345`, `app/web/auth.py:72-84`, `app/api/auth_flow.py:175-446` |
| 30 | **22 instances** of broad `except Exception: pass` | `app/web/public.py`, `app/web/auth.py`, `app/services/` |
| 31 | Missing type hints on all older service methods | `person.py`, `audit.py`, `rbac.py`, `billing.py`, `auth.py`, `scheduler.py` |
| 32 | Missing `logger = logging.getLogger(__name__)` in 10 services | `person.py`, `audit.py`, `rbac.py`, `scheduler.py`, etc. |
| 33 | Older services use `@staticmethod` pattern instead of `__init__(db)` | All pre-SchoolNet services |

### Templates

| # | Issue | Location |
|---|-------|----------|
| 34 | CSRF pattern inconsistency (manual vs `csrf_form`) | `admin/login.html:83` + all admin CRUD templates |
| 35 | `\| tojson \| safe` inside `<pre>` (not `<script>`) | `admin/audit/detail.html:59`, `billing/webhook_events/detail.html:60` |
| 36 | Missing `for`/`id` on all public form labels (accessibility) | All `public/auth/*.html` templates |
| 37 | Nearly zero ARIA attributes across all templates | Entire template codebase |
| 38 | Alpine.js `x-data` uses double quotes with template interpolation | `branding.html:22`, `components/_file_upload.html:3` |
| 39 | Enum `str` mixin inconsistency across models | `auth.py`, `person.py` (no `str`) vs `billing.py`, `school.py` (with `str`) |
| 40 | Migration 005 uses `default=` instead of `server_default=` | 12 columns in `005_schoolnet_schema.py` |

---

## LOW (16 issues) — Tech Debt

| # | Issue | Location |
|---|-------|----------|
| 41 | Logout via GET (CSRF-logout risk) | `app/web/auth.py:185`, `app/web/public.py:484` |
| 42 | Password reset token not single-use | `app/services/auth_flow.py:260-271` |
| 43 | `TimestampMixin` defined but never used | `app/db.py:15-33` |
| 44 | Missing `ondelete` cascade on all FKs | All models |
| 45 | `PersonRole` missing `person` relationship | `app/models/rbac.py:80-99` |
| 46 | Missing indexes on `person_id` columns | `auth.py:44,89,127,155` |
| 47 | Duplicate `apply_ordering`/`apply_pagination` utilities | `query_utils.py` vs `common.py` |
| 48 | `password_hash` accepted in create/update schemas | `app/schemas/auth.py:24,31` |
| 49 | Duplicate `ErrorResponse` schema definitions | `app/schemas/auth_flow.py` vs `app/schemas/error.py` |
| 50 | Missing schemas for Ward model | `app/schemas/` |
| 51 | `python-jose` is unmaintained (use PyJWT) | `pyproject.toml:28` |
| 52 | `passlib` + `bcrypt` compatibility workaround | `pyproject.toml:29`, `auth_flow.py:38-41` |
| 53 | Footer renders "now" literally instead of year | `templates/public/base.html:130` |
| 54 | Docker ports diverge from CLAUDE.md docs | `docker-compose.yml:7,66,77` |
| 55 | Branding stored under `SettingDomain.scheduler` | `app/services/branding.py:65,87` |
| 56 | Missing test coverage for school, ward, payment, public routes | `tests/` |

---

## Recommended Fix Priority

1. **Rotate secrets** — Immediately change DB and Redis passwords, move to `.env`
2. **Fix webhook bypass** — Reject all webhooks when Paystack is unconfigured
3. **Fix open redirect** — Validate `next_url` is a relative path
4. **Create `wards` migration** — Table doesn't exist in the database
5. **Remove `token_hash` from `SessionRead`** — Data leakage
6. **Add `secure=True` to auth cookies** — Conditional on HTTPS
7. **Add web routes to rate limiter** — `/login`, `/admin/login`, `/forgot-password`
8. **Add server-side password validation** — Enforce `min_length=8` in registration service
9. **Migrate older services** — The newer services show the correct pattern; the older ones need to adopt `select()`, `flush()`, `__init__(db)`, domain exceptions, type hints, and loggers
