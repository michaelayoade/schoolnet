# Starter Template

Multi-tenant FastAPI starter with auth, RBAC, audit, and scheduler. FastAPI + SQLAlchemy 2.0 + Celery + Jinja2/Alpine.js.

## Quick Commands

```bash
# Quality (or use: make check)
make lint                        # ruff check app/
make format                      # ruff format + fix
make type-check                  # mypy app/

# Testing (or use: make test)
pytest tests/path/test_file.py -v  # Specific test
pytest -x --tb=short               # Stop on first failure
make test-cov                      # With coverage

# Database
make migrate                     # alembic upgrade head
make migrate-new msg="desc"      # New migration

# Development
make dev                         # uvicorn with reload
make docker-up / docker-down     # Docker lifecycle
make docker-shell                # Shell into app container
```

## Architecture

```
app/
├── api/        # REST API routes (thin wrappers → services)
├── web/        # HTML routes (thin wrappers → web services)
├── models/     # SQLAlchemy ORM models
├── schemas/    # Pydantic v2 request/response models
├── services/   # ALL business logic lives here
├── tasks/      # Celery tasks (orchestrate services)
templates/      # Jinja2 + Alpine.js + HTMX
tests/          # Unit and integration tests
scripts/        # CLI scripts (seed, validate, etc.)
static/         # JS, CSS, images
```

## Critical Rules

### 1. Service Layer — Routes are THIN WRAPPERS
Routes MUST NOT contain database queries, business logic, or conditionals.

### 2. SQLAlchemy 2.0 — Use select(), Not db.query()
```python
stmt = select(Model).where(Model.field == value)
results = db.scalars(stmt).all()
```

### 3. Pydantic v2 — Use ConfigDict, Not orm_mode
```python
class MySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

### 4. Model PK Naming — Read the Model First
Each model has unique PK names. ALWAYS read the model file to verify field names.

### 5. Migrations — Must Be Idempotent
Check before creating: `inspector.has_table()`, column existence, enum existence.

### 6. Route Handlers Are Sync
SQLAlchemy sessions are sync. Use `def`, not `async def`. Background work goes to Celery.

### 7. CSRF Protection
Every `<form method="POST">` must include `{{ request.state.csrf_form | safe }}`.
CSRF is auto-injected via JS in `base.html`, but explicit tokens are preferred.

## Code Style

- Type hints on ALL functions (mypy must pass)
- Every service file: `logger = logging.getLogger(__name__)`
- Imports: stdlib → third-party → local (absolute imports)
- Line length: 88 chars (ruff)
- Use `flush()` not `commit()` in services — caller controls transaction

## Testing Requirements

- SQLite in-memory (conftest patches PostgreSQL UUID)
- Every new service needs: happy path + error cases + edge cases

## Verification Workflow

Before declaring any task complete:
```bash
make lint                                            # Must pass
poetry run mypy app/path/to/changed/files.py --ignore-missing-imports  # Must pass
pytest tests/path/to/relevant/tests.py -v            # Must pass
```

## Common Mistakes to Avoid

- Using `db.query()` instead of `select()` (SQLAlchemy 1.x vs 2.0)
- Using bare `except:` (catch specific exceptions)
- Putting business logic in routes (must be in services)
- Using `async def` for route handlers (sessions are sync)
- Assuming `model.id` exists (each model has unique PK naming)
- Using `| safe` on user content in templates (XSS vulnerability)

## Environment Variables

Required: `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET`, `TOTP_ENCRYPTION_KEY`, `REDIS_URL`
Optional: `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

## Docker

- Container names: `schoolnet_app`, `schoolnet_worker`, `schoolnet_beat`, `schoolnet_db`, `schoolnet_redis`
- App port: 8006 (external) → 8001 (internal)
- DB port: 127.0.0.1:5435 (external) → 5432 (internal)
- Redis port: 127.0.0.1:6380 (external) → 6379 (internal)
