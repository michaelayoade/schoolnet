# UI Capture (Authenticated)

Use Playwright script to capture SchoolNet pages with an authenticated admin session.

## Prerequisites
- Target app is running
- RBAC seeded and at least one admin user exists
- Node + Playwright available

## Seed/auth bootstrap (if needed)
Inside the app runtime environment:

```bash
PYTHONPATH=/app python scripts/seed_admin.py \
  --email admin@schoolnet.local \
  --first-name School --last-name Admin \
  --username admin --password Demo1234

PYTHONPATH=/app python scripts/seed_rbac.py --admin-email admin@schoolnet.local
```

## Run capture

```bash
SCHOOLNET_BASE_URL=http://localhost:8006 \
SCHOOLNET_USER=admin \
SCHOOLNET_PASS=Demo1234 \
node scripts/capture_schoolnet_auth.mjs
```

Optional output override:

```bash
SCHOOLNET_CAPTURE_DIR=reports/schoolnet-ui-custom-auth node scripts/capture_schoolnet_auth.mjs
```

## Behavior
- Captures public pages first
- Logs in via `/admin/login` form (`username` + `password`)
- Captures confirmed admin routes
- Exits non-zero on auth failure or capture failures
- Prints per-route status and final summary
