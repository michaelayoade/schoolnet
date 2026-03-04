#!/usr/bin/env python3
"""Rotate local .env secrets and update dependent connection URLs.

This script is intended for local/self-hosted deployments where secrets are
stored directly in `.env` (not OpenBao references).
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from cryptography.fernet import Fernet


def _parse_env(path: Path) -> tuple[list[str], dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return lines, data


def _render_env(lines: list[str], updates: dict[str, str]) -> str:
    rendered: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            rendered.append(line)
            continue
        key, _value = line.split("=", 1)
        key = key.strip()
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(line)
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")
    return "\n".join(rendered) + "\n"


def _is_secret_ref(value: str) -> bool:
    return value.startswith(("openbao://", "bao://", "vault://"))


def _replace_password_in_url(url: str, password: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname or not parsed.scheme:
        return url
    username = parsed.username or ""
    host = parsed.hostname
    netloc = f"{username}:{password}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def _new_token(length_bytes: int = 32) -> str:
    return secrets.token_urlsafe(length_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate local .env secrets")
    parser.add_argument("--env-file", default=".env", help="Path to env file")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write updates to env file (default prints preview only)",
    )
    parser.add_argument(
        "--force-literal-jwt",
        action="store_true",
        help="Rotate JWT/TOTP keys even if currently set to OpenBao refs",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    lines, data = _parse_env(env_path)

    updates: dict[str, str] = {}
    updates["POSTGRES_PASSWORD"] = _new_token(24)
    updates["REDIS_PASSWORD"] = _new_token(24)
    updates["SECRET_KEY"] = _new_token(48)

    jwt_value = data.get("JWT_SECRET", "")
    totp_value = data.get("TOTP_ENCRYPTION_KEY", "")

    if args.force_literal_jwt or not _is_secret_ref(jwt_value):
        updates["JWT_SECRET"] = _new_token(48)
    if args.force_literal_jwt or not _is_secret_ref(totp_value):
        updates["TOTP_ENCRYPTION_KEY"] = Fernet.generate_key().decode("utf-8")

    for key in ("DATABASE_URL",):
        if key in data:
            updates[key] = _replace_password_in_url(
                data[key], updates["POSTGRES_PASSWORD"]
            )
    for key in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
        if key in data:
            updates[key] = _replace_password_in_url(data[key], updates["REDIS_PASSWORD"])

    rendered = _render_env(lines, updates)

    if args.write:
        env_path.write_text(rendered, encoding="utf-8")
        print(f"Updated {env_path}")
        print("Next steps:")
        print("1) Rotate DB user password in PostgreSQL (ALTER USER ... PASSWORD ...)")
        print("2) Restart application services with new .env values")
        print("3) Revoke old JWT/TOTP/redis credentials from any external stores")
    else:
        print(rendered)
        print("# Preview only. Re-run with --write to apply.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
