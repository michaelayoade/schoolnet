# SchoolNet

School admissions platform — manage applications, track payments, and connect parents with schools.

Built with FastAPI + SQLAlchemy 2.0 + Jinja2/HTMX/Alpine.js + PostgreSQL.

## Features

- **School Admissions**
  - Dynamic admission forms per school
  - Application submission and tracking
  - Document uploads and verification
  - Multi-ward support for parents

- **Payments**
  - Paystack integration for application fees
  - Commission tracking and settlement
  - Invoice generation

- **Authentication & Security**
  - JWT-based auth with refresh token rotation
  - Multi-factor authentication (TOTP)
  - API key management with Redis-backed rate limiting
  - Role-based access control (RBAC)

- **Multi-Portal UI**
  - Parent portal — apply, track, manage wards
  - School portal — review applications, manage forms, verify documents
  - Admin portal — manage schools, users, system settings

- **Background Jobs**
  - Celery workers with Redis broker
  - Database-backed Beat scheduler

- **Observability**
  - Prometheus metrics, OpenTelemetry tracing, structured logging

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.111.0 |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Cache/Broker | Redis 7 |
| Task Queue | Celery 5.4 |
| Frontend | Jinja2 + HTMX + Alpine.js + Tailwind CSS |
| Payments | Paystack |

## Getting Started

### Docker (Recommended)

```bash
cp .env.example .env
# Edit .env with your secrets

docker compose up -d

# Run migrations
docker exec schoolnet_app alembic upgrade head

# Create admin user
docker exec schoolnet_app python scripts/seed_admin.py --username admin --password <password>
```

Services:
- **App**: http://localhost:8006
- **PostgreSQL**: localhost:5436
- **Redis**: localhost:6381

### Local Development

```bash
poetry install
docker compose up -d db redis   # databases only
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

## Configuration

Key environment variables (see `.env.example` for full list):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+psycopg://...schoolnet` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET` | JWT signing secret | Required |
| `TOTP_ISSUER` | TOTP issuer name | `schoolnet` |
| `TOTP_ENCRYPTION_KEY` | TOTP encryption key | Required |
| `BRAND_NAME` | Platform display name | `SchoolNet` |
| `PAYSTACK_SECRET_KEY` | Paystack secret key | - |
| `OTEL_SERVICE_NAME` | Tracing service name | `schoolnet` |

### OpenBao Integration

Secrets can be resolved from OpenBao:
```bash
JWT_SECRET=openbao://secret/data/schoolnet#jwt_secret
```

## Testing

Tests run inside Docker (requires Python 3.11+):

```bash
docker exec schoolnet_app poetry run pytest tests/ -x -q
```

## Project Structure

```
├── app/
│   ├── api/              # API route handlers
│   ├── web/              # Web UI routes (HTMX)
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic validation schemas
│   ├── services/         # Business logic layer
│   ├── tasks/            # Celery background tasks
│   └── main.py           # FastAPI app + middleware
├── templates/            # Jinja2 HTML templates
│   ├── parent/           # Parent portal
│   ├── school/           # School portal
│   └── admin/            # Admin portal
├── static/               # Static assets
├── alembic/              # Database migrations
└── tests/                # Test suite
```

## License

[Add your license here]
