"""Resolve and validate the dedicated PostgreSQL integration test database."""

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DEFAULT_TEST_ENV_FILE = Path(__file__).resolve().parents[1] / ".env.test"


class TestDatabaseConfigurationError(ValueError):
    """A test database URL is missing or cannot be used safely."""

    __test__ = False


def resolve_test_database_url(
    *, env: Mapping[str, str] | None = None, env_file: Path | None = None
) -> str:
    """Prefer the process environment, then the ignored local .env.test file."""
    source = os.environ if env is None else env
    database_url = source.get("TEST_DATABASE_URL")
    if not database_url:
        values = dotenv_values(env_file or DEFAULT_TEST_ENV_FILE, interpolate=False)
        database_url = values.get("TEST_DATABASE_URL")
    if not database_url:
        raise TestDatabaseConfigurationError(
            "TEST_DATABASE_URL is required in the process environment or apps/backend/.env.test."
        )

    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise TestDatabaseConfigurationError(
            "TEST_DATABASE_URL is not a valid database URL."
        ) from None

    if url.get_backend_name() != "postgresql":
        raise TestDatabaseConfigurationError("TEST_DATABASE_URL must use PostgreSQL.")
    if "test" not in (url.database or "").lower():
        raise TestDatabaseConfigurationError("TEST_DATABASE_URL database name must contain `test`.")
    return database_url


def resolve_migration_database_url(
    normal_database_url: str,
    *,
    mode: str | None,
    env: Mapping[str, str] | None = None,
    env_file: Path | None = None,
) -> str:
    """Keep normal Alembic behavior; require the guarded URL in test mode."""
    if mode is None or mode == "0":
        return normal_database_url
    if mode != "1":
        raise TestDatabaseConfigurationError("TEST_MIGRATION_MODE must be `1` or unset.")
    return resolve_test_database_url(env=env, env_file=env_file)
