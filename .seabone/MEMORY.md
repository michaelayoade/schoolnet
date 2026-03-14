# Seabone Memory — schoolnet

## Project Facts

### From CLAUDE.md
> # Starter Template
>
> Multi-tenant FastAPI starter with auth, RBAC, audit, and scheduler. FastAPI + SQLAlchemy 2.0 + Celery + Jinja2/Alpine.js.
>
> ## Quick Commands
>
> ```bash
> # Quality (or use: make check)
> make lint                        # ruff check app/
> make format                      # ruff format + fix
> make type-check                  # mypy app/
>
> # Testing (or use: make test)
> pytest tests/path/test_file.py -v  # Specific test
> pytest -x --tb=short               # Stop on first failure
> make test-cov                      # With coverage
>
> # Database
> make migrate                     # alembic upgrade head
> make migrate-new msg="desc"      # New migration

### From README
> # Starter Template
>
> A production-ready FastAPI starter template with enterprise-grade features including authentication, RBAC, audit logging, background jobs, and full observability.
>
> ## Features
>
> - **Authentication & Security**
>   - JWT-based authentication with refresh token rotation
>   - Multi-factor authentication (TOTP, SMS, Email)
>   - API key management with rate limiting

### Stack Detection
- Build: pyproject.toml detected

## Known Patterns

### Security Architecture
- Auth: JWT access token (15 min) + httponly refresh cookie (30 days); session validated against DB on every request
- Password hashing: `CryptContext(schemes=["pbkdf2_sha256","bcrypt"])` via passlib
- API keys: hashed with SHA-256 (not bcrypt), stored in `ApiKey.key_hash`
- TOTP: secrets encrypted with Fernet using `TOTP_ENCRYPTION_KEY`; `valid_window=0` (no drift allowed)
- CSRF: double-submit cookie (`httponly=True`, `samesite=lax`); validated on all form POSTs
- Rate limiting: Redis sliding window on `/auth/login`, `/auth/mfa/verify`, `/auth/register`, `/auth/password-reset`; in-memory TTLCache fallback when Redis is down (fails closed); web paths `/register/parent` + `/register/school` still not rate-limited
- Webhook: Paystack HMAC-SHA512 signature check — returns 503 when `PAYSTACK_SECRET_KEY` is unset
- Password strength: `_validate_password_strength()` in `app/services/registration.py` enforces 8-char min; called from `register_parent`, `register_school_admin`, `reset_password` — NOT from `change_password`
- WebSocket auth: token read from `Sec-WebSocket-Protocol` subprotocol header (fixed); `/ws/notifications`
- Cookie security: web login handlers (`app/web/auth.py:85`, `app/web/public.py:243`) set cookies without `secure` kwarg; `_refresh_cookie_secure()` in `auth_flow.py` defaults to `False` and is not used by web routes

### Security Status (after Wave 2 fixes, rescan 2026-02-27)
**FIXED (c1-1 through c1-5):**
- Open redirect in admin login — `sanitize_next_url()` in `app/web/deps.py`
- Webhook sig bypass when Paystack unconfigured — returns 503 now
- Rate limiter fail-open on Redis outage — in-memory `TTLCache` fallback
- No password minimum length — `_validate_password_strength()` added to registration + reset
- JWT in WebSocket URL — reads from `Sec-WebSocket-Protocol` subprotocol

**STILL OPEN (priority order):**
- `change_password` endpoint skips `_validate_password_strength` — `app/api/auth_flow.py:436` (HIGH, trivial, c1-16)
- Web login routes set cookies without `secure` kwarg — `app/web/auth.py:85`, `app/web/public.py:243` (MEDIUM, trivial, c1-17)
- Refresh cookie defaults to `secure=False` — `app/services/auth_flow.py:154` (MEDIUM, trivial, c1-6)
- Email HTML injection via unescaped `person_name` — `app/services/email.py:99` (MEDIUM, trivial, c1-7)
- X-Forwarded-For trusted unconditionally — `app/middleware/rate_limit.py:33` (MEDIUM, small, c1-8) [POSSIBLE REGRESSION]
- TOTP replay within same 30s window — `app/services/auth_flow.py:568` (MEDIUM, medium, c1-9)
- SVG sanitizer misses `<use>`, `<animate>`, CSS url() — `app/services/branding_assets.py:87` (MEDIUM, medium, c1-10)
- `/metrics` endpoint unauthenticated — `app/main.py:391` (LOW, trivial, c1-11)
- `/health/ready` leaks raw exceptions — `app/main.py:370` (LOW, trivial, c1-12)
- Login failures log user email PII — `app/web/public.py:215` (LOW, trivial, c1-13)
- `/register/parent` + `/register/school` not rate-limited — `app/middleware/rate_limit.py:21` (LOW, trivial, c1-14)
- CSP `unsafe-inline`/`unsafe-eval` — `app/middleware/security_headers.py:43` (LOW, large, c1-15)

### Security Status (cycle 5 new findings, 2026-02-27)
**NEW CRITICAL:**
- Billing API only `require_user_auth` — any user can manipulate products/invoices/customers — `app/main.py:293` (CRITICAL, trivial, c5-1)
- RBAC API only `require_user_auth` — any user can assign platform_admin role to themselves — `app/main.py:288` (CRITICAL, trivial, c5-2)
- Scheduler API allows arbitrary Celery task injection — `app/api/scheduler.py:30`, `app/main.py:292` (CRITICAL, small, c5-3)

**NEW HIGH:**
- Unvalidated `callback_url` in purchase endpoint — payment redirect hijacking — `app/api/applications.py:33` (HIGH, small, c5-4)
- Web `GET /logout` deletes cookies only, no server-side session revocation — `app/web/public.py:262` (HIGH, small, c5-5)
- File upload/delete has no entity ownership check — `app/api/file_uploads.py` (HIGH, small, c5-6)
- School admin IDOR on applications (cross-school) — `app/web/school/applications.py:58` (HIGH, small, c5-7)
- Bank account number + Paystack subaccount exposed in public SchoolRead schema — `app/schemas/school.py:59` (HIGH, small, c5-8)
- Admin API accepts raw `password_hash` field — backdoor risk — `app/schemas/auth.py:24` (HIGH, small, c5-9)
- `GET /logout` unauthenticated, CSRF logout attack possible — `app/web/public.py:262` (HIGH, trivial, c5-10)

**NEW MEDIUM:**
- Audit log poisoning via spoofed `X-Actor-Type`/`X-Actor-Id` headers — `app/services/audit.py:93` (MEDIUM, small, c5-11)
- Raw exception messages in redirect URLs — `app/web/file_uploads.py:177` + others (MEDIUM, small, c5-12)
- WebSocket auth skips session revocation check — `app/api/ws.py:30` (MEDIUM, small, c5-13)
- Mass assignment risk in `PATCH /auth/me` — `app/api/auth_flow.py:215` (MEDIUM, small, c5-14)
- Non-parent roles can initiate form purchases — `app/api/applications.py:23` (MEDIUM, trivial, c5-15)
- School forms IDOR POST handlers still missing ownership check (regression) — `app/web/school/forms.py:117` (MEDIUM, small, c5-16)
- CSRF cookie `httponly=True` breaks JS auto-injection — `app/middleware/csrf.py:80` (MEDIUM, trivial, c5-17)

### Dependency Architecture Notes (cycle 4)
- `boto3` is a hidden optional dep used by `S3Storage._get_client()` (`app/services/storage.py:102`) but NOT in pyproject.toml; deploying with `STORAGE_BACKEND=s3` crashes silently.
- `bcrypt 5.0.0` is in poetry.lock but passlib 1.7.4 only supports bcrypt <4 — covered by deps-004.
- `app/api/` and `app/schemas/` are missing `__init__.py` (namespace packages); all other sub-packages have one.
- No type stubs in dev dependencies; `ignore_missing_imports = true` globally in mypy hides all untyped packages.
- Three `opentelemetry-instrumentation-*` packages pinned at pre-release `0.47b0`.
- mypy should use `[[tool.mypy.overrides]]` per-module rather than global `ignore_missing_imports = true`.

### Dependency Architecture Notes (cycle 8)
- `python-multipart` (required by FastAPI file uploads / Form()) is NOT in pyproject.toml; currently only an implicit transitive dep; should be declared explicitly (deps-c8-2).
- batch-deps-c4-config (PR #26) reported as complete in pm-state but its changes (__init__.py files, OTel stable pins, type stubs) are absent from `main` — PRs were created but not merged or were reverted; re-fix needed via deps-c8-1/3/4.
- `import json` inline inside `paystack_webhook()` in `app/api/payments.py:28` survived both cycle-6 quality fixes and cycle-7 regression fixes (deps-c8-5).

### Coordinator / Spawn Schema Note
- The coordinator/sentinel writes tasks with field `task_id`; spawn-agent.sh expects `id`. Schema mismatch causes tasks to get stuck in "active" with no agents running.
- Fix: when tasks are stuck in "active" with no tmux sessions, wipe active-tasks.json and respawn via spawn-agent.sh (which writes correct `id` field with status "running").
- RUNNING_COUNT check uses `select(.status == "running")` — tasks with status "active" are invisible to concurrency limiter.

### File Map (key security files)
- `app/middleware/csrf.py` — CSRF double-submit
- `app/middleware/rate_limit.py` — Redis sliding window rate limiter
- `app/middleware/security_headers.py` — OWASP headers + CSP
- `app/services/auth_flow.py` — login, MFA, token issuance, refresh rotation
- `app/services/auth_dependencies.py` — `require_user_auth`, `require_role`, `require_permission`
- `app/services/branding_assets.py` — SVG content sniffing + sanitization
- `app/services/payment_gateway.py` — Paystack HMAC webhook validation
- `app/api/payments.py` — webhook receiver (open when unconfigured)
- `app/services/secrets.py` — OpenBao/Vault reference resolver
- `app/web/public.py` — public login/register routes; login logs PII (email); cookies missing `secure`
- `app/web/auth.py` — admin login route; open redirect fixed; cookies still missing `secure`
- `app/api/auth_flow.py` — `change_password` endpoint (line 436) missing password strength check
- `app/web/deps.py` — `sanitize_next_url()` utility (fixed redirect); `require_web_auth` cookie-JWT auth

### Quality Architecture Debt (cycle 6 findings, 2026-02-27)
- **`db.query()` legacy pattern**: 54 occurrences in 12 files violate CLAUDE.md SQLAlchemy 2.0 rule; top offenders: `auth_flow.py` (×14), `billing.py` (×14), `auth.py` (×7). Works at runtime but breaks type checking and will fail in strict SQLAlchemy 2.x mode.
- **`db.commit()` in service layer**: 87 occurrences in 9 service files violate CLAUDE.md flush-not-commit rule; top offenders: `billing.py` (×37), `auth.py` (×13), `rbac.py` (×12), `auth_flow.py` (×11).
- **N+1 queries in list views**: All 3 web-layer list views trigger N+1 queries — `web/school/forms.py:44` (price lookup per form), `web/parent/applications.py:32` (admission_form + school per app), `web/school/applications.py:43` (admission_form + parent per app). Fix: `selectinload()` in service query methods.
- **Missing pagination**: `GET /applications/my` (line 39) and `GET /applications/school/{id}` (line 112) in `app/api/applications.py` return unbounded lists.
- **`billing.py` is 1073 lines / 13 classes**: Largest file in codebase; candidate for splitting into `app/services/billing/` sub-package.
- **Duplicate school admin helpers**: `_get_school_for_admin()` in `web/school/forms.py:21` and `_get_school_id()` in `web/school/applications.py:20` are near-identical; should be unified in `schoolnet_deps.py`.
- **Inline imports in `app/api/applications.py`**: Lines 60, 118, 143 do `from app.models.school import ...` inside function bodies.

### API Architecture Notes (cycle 7 findings, 2026-02-27)
- **Router-level auth (main.py)**: `notifications_router`, `file_uploads_router`, `settings_router`, `scheduler_router`, `billing_router`, `people_router` all get `require_user_auth` via `_include_api_router()`. SchoolNet routes (`schools`, `admission_forms`, `applications`, `payments`) have NO router-level auth — each endpoint manages its own auth dependency.
- **Missing `response_model` gaps**: `purchase_form()` (applications.py:23), `refresh_schedule()` (scheduler.py:58), `enqueue_scheduled_task()` (scheduler.py:63), `mark_all_read()` (notifications.py:77) all return untyped dicts with no response_model.
- **Business logic in IDOR-fix routes**: IDOR security fixes introduced inline `db.get()` calls in `get_application()` (line 62), `review_application()` (line 145), and all three admission_form mutation handlers — CLAUDE.md Rule #1 violations that should be moved into service `assert_*_access()` methods.
- **Possible regressions from batch-quality-c6 fixes**: Code inspection shows `db.query()` still in `app/api/auth_flow.py` (lines 306, 349, 386, 419), inline imports still in `applications.py` (lines 60, 143) and `payments.py` (import json at line 28), and no pagination params in `my_applications`/`school_applications`. These were listed as fixed but may not have been committed.
- **Pagination gaps**: `list_school_forms()` (admission_forms.py:30) and `my_schools()` (schools.py:88) have no limit/offset; `search_schools()` limit is missing `ge=1` (schools.py:33).

### Security Status (cycle 9 new findings, 2026-02-27)
**NEW CRITICAL:**
- Unauthenticated POST `/settings/branding` → stored XSS via CSS injection — `app/web_home.py:80` (CRITICAL, trivial, c9-1); `web_home_router` has NO auth dependency; attacker can inject `</style><script>...</script>` via `custom_css` field, rendered on all pages as `{{ org_branding.css | safe }}`

**NEW HIGH:**
- File upload ownership check regression — `app/api/file_uploads.py:14, 74` (HIGH, small, c9-2); `uploaded_by` is never populated from auth context, `delete_file_upload` has no ownership check — any authenticated user can delete any file (regression of fix-security-c5-6)

**NEW MEDIUM:**
- `delete_avatar()` missing `.resolve()` path traversal check — `app/services/avatar.py:46` (MEDIUM, trivial, c9-3); uses string replacement not safe_path pattern unlike `branding_assets.py`
- CSS injection via font family string interpolation in `generate_css()` — `app/services/branding.py:128` (MEDIUM, trivial, c9-4); font name embedded in double-quoted CSS value without sanitization

**NEW LOW:**
- SMTP_PASSWORD not passed through `resolve_secret()` — `app/services/email.py:42` (LOW, trivial, c9-5); bypasses vault unlike JWT/TOTP secrets
- Bare `except Exception:` in `FileUploadService.delete()` — `app/services/file_upload.py:122` (LOW, trivial, c9-6)

### Branding Architecture Note (cycle 9)
- `app/web_home.py` registers `GET/POST /settings/branding` without ANY auth dependency — confirmed unauthenticated in main.py as `app.include_router(web_home_router)`
- `org_branding.css` = output of `generate_css(branding)` where `custom_css` field is appended verbatim → rendered via `{{ org_branding.css | safe }}` in `templates/partials/_org_branding_head.html`
- Safe path pattern for asset deletion exists in `branding_assets.py:116` (`_safe_asset_path` with `.resolve()`) — should be adopted by `avatar.py:delete_avatar()`

### Security Status (cycle 10 new findings, 2026-02-28)
**REGRESSIONS (listed-fixed but code unchanged):**
- rbac_router still uses `require_user_auth` not `require_role("admin")` — `app/main.py:288` (CRITICAL, trivial, c10-2); batch-security-c5-auth-routers was marked done but code unchanged
- billing_router still uses `require_user_auth` not `require_role("admin")` — `app/main.py:293` (CRITICAL, trivial, c10-3); same regression pattern

**NEW CRITICAL:**
- Unauthenticated `GET /` homepage lists all Person records (PII) to anyone — `app/web_home.py:19` (CRITICAL, trivial, c10-1)

**NEW HIGH:**
- people_router at `require_user_auth` only — any authenticated user can update/delete any Person record incl. email_verified, is_active — `app/main.py:289` + `app/api/persons.py` (HIGH, trivial, c10-4)

**NEW MEDIUM:**
- Rate limiter path mismatch: protects `/auth/password-reset` (non-existent) not `/auth/forgot-password` (actual); forgot-password unrate-limited — `app/middleware/rate_limit.py:22` (MEDIUM, trivial, c10-5)
- Password reset JWT token not single-use; can be replayed within 60-min TTL — `app/services/auth_flow.py:738` (MEDIUM, small, c10-6)
- Avatar upload trusts client Content-Type without magic byte sniffing — `app/services/avatar.py:14` (MEDIUM, small, c10-7)

**NEW LOW:**
- S3 credentials (access_key, secret_key) and Paystack secret bypass `resolve_secret()` — `app/config.py:51` (LOW, trivial, c10-8)

### Fix Regression Pattern (confirmed cycles 10–13)
- Multiple "fixed" PRs were created but never merged to main, OR merged and reverted
- Pattern spans: c5-1/c5-2 (auth routers), c6 quality fixes (db.query/pagination), c7 API fixes, c8 inline imports, deps fixes (python-jose, passlib, boto3, python-multipart, __init__.py)
- Quality cycle 11 (2026-02-28): confirmed 3 regressions — `api/auth_flow.py` db.query (lines 306/349/386/420), `api/applications.py` inline imports (lines 60/118/143), `api/payments.py` inline `import json` (line 28)
- Deps cycle 13 (2026-02-28): 7 regressions confirmed — fix-deps-001 (python-jose CVE still present), fix-deps-002 (passlib still present), fix-deps-003 (boto3 still undeclared), fix-deps-004 (python-multipart still undeclared), batch-deps-c4-config (__init__.py files still absent), batch-security-c9-low c9-5 (SMTP_PASSWORD still via _env_value not resolve_secret), batch-deps-c8-medium c8-5 (import json still inline in payments.py)
- Health score trend: 26 (c11) → 22 (c12) → 20 (c13) → 16 (c14) — degrading each cycle
- Health score: 16/100 (was 20; trend: degrading)
- Recommendation: CI gate to enforce invariants (e.g., ban `db.query()` in services, ban `db.commit()` in services, ban inline imports in routes)

### Security Status (cycle 14 new findings, 2026-02-28)
**REGRESSIONS (listed-fixed but code unchanged, cycle 14 confirmed):**
- fix-security-c9-1 (branding POST XSS auth): `web_home.py:80` still has no auth dependency — REGRESSION
- fix-security-c9-2 (file upload ownership): `file_uploads.py:14` never passes `uploaded_by`; delete has no ownership check — REGRESSION
- fix-security-c5-1/c5-2/c10-2/c10-3 (billing/rbac routers): both still `require_user_auth` not `require_role("admin")` — REGRESSION (5th cycle)
- deps-c13-8/c9-5 (SMTP_PASSWORD not via resolve_secret): `email.py:42` unchanged — REGRESSION
- deps-c13-9/deps-c8-5 (inline import json in payments.py): `payments.py:28` unchanged — REGRESSION

**CONFIRMED FIXED (cycle 14 verification):**
- c1-7 (email HTML injection via person_name): `html.escape()` now applied in `send_password_reset_email()` — CONFIRMED FIXED
- Password reset strength: `reset_password()` now calls `_validate_password_strength()` — CONFIRMED FIXED

**NEW FINDINGS (cycle 14):**
- File upload reads full content to RAM before size check — `app/api/file_uploads.py:22` (MEDIUM, trivial, c14-9)
- create_notification allows any auth user to target any recipient_id — `app/api/notifications.py:18` (MEDIUM, small, c14-10)
- CORS `allow_methods=['*']` overly permissive — `app/main.py:95` (MEDIUM, trivial, c14-14)
- GET /settings/branding also unauthenticated (expansion of c9-1) — `app/web_home.py:65` (HIGH, trivial, c14-8)

### Quality Debt Snapshot (cycle 11, 2026-02-28)
- `db.query()` in service layer: 40+ calls across auth_flow(14), auth(7), rbac(4), billing(13+), branding(2)
- `db.commit()` in service layer: 87+ calls across billing(37+), auth(13), rbac(12), auth_flow(11), others
- Missing logger: auth_flow, auth, rbac, branding, audit, domain_settings, person, scheduler, avatar, secrets
- Duplicate helpers: `_env_value`/`_env_int` defined independently in auth_flow.py AND email.py with divergent signatures
- `app/services/billing.py`: 1073 lines, 14 classes — highest priority refactor candidate

### API Layer Debt Snapshot (cycle 12, 2026-02-28)
- **auth_flow.py route violations**: 7 routes (GET/PATCH /me, POST/DELETE avatar, revoke_session, revoke_all_sessions, change_password) do direct ORM mutations + db.get() in route handlers — worst thin-wrapper violations in the API layer (api-c12-1)
- **admission_forms.py**: 3 write routes do db.get(School) + ownership checks inline (api-c12-2)
- **Regression pattern confirmed**: batch-api-c7-response-models (4 endpoints) and batch-api-c7-pagination (4 endpoints) marked fixed but both absent from main; 4th consecutive cycle with regression
- **Unvalidated order_by**: scheduler.py L19 and persons.py L27 accept arbitrary column names → 500 on bad input
- **Inline imports in new files**: schools.py (4 sites), admission_forms.py (3 sites), file_uploads.py (1), notifications.py (1)
- **ws.py bare except**: _authenticate_ws() L38 silently absorbs all failures
- **Sessions endpoint unbounded**: GET /auth/me/sessions has no pagination
- **Notification create RBAC gap**: POST /notifications allows any auth'd user to target any recipient_id
