# Schoolnet — Claude Agent Guide

FastAPI + SQLAlchemy 2.0 + Jinja2/HTMX/Alpine.js + PostgreSQL. School management platform.
Port 8006 external → 8001 internal. Docker containers prefixed `schoolnet_`.
Plugin: `frontend-design`.

## Non-Negotiable Rules
- SQLAlchemy 2.0: `select()` + `scalars()`, never `db.query()`
- `db.flush()` in services, NOT `db.commit()` — routes commit
- Routes are thin wrappers — no business logic
- Commands: always `poetry run ruff`, `poetry run mypy`, `poetry run pytest`
- Tests run inside Docker: `docker exec schoolnet_app poetry run pytest`

## Rate Limiter — Test Isolation Critical
The rate limiter uses in-memory fallback when Redis is not available in CI.
State LEAKS between tests — always reset in setUp or use a fixture:
```python
def setUp(self):
    from app.middleware.rate_limit import reset_rate_limiters
    reset_rate_limiters()   # or equivalent — read the implementation
```
Or mock the rate limiter for tests that don't test rate limiting itself.

## Template Rules (same as ERP)
- Single quotes on `x-data` with `tojson`
- `{{ var if var else '' }}` not `{{ var | default('') }}`
- Dict lookup for dynamic Tailwind classes
- `status_badge()`, `empty_state()`, `live_search()` macros — never inline
- CSRF mandatory on every POST form
- `<div id="results-container">` on list pages
- Dark mode: always pair light + dark variants
- `scope="col"` on all `<th>`

## Python Version
Requires Python 3.11+. Host may have 3.10 — always run via Docker or pyenv.
