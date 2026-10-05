import uuid
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

from test_support.database import (
    TestDatabaseConfigurationError,
    resolve_migration_database_url,
    resolve_test_database_url,
)


def test_process_environment_takes_priority_over_env_file() -> None:
    with patch("test_support.database.dotenv_values") as file_values:
        actual = resolve_test_database_url(
            env={"TEST_DATABASE_URL": "postgresql+psycopg://ci/test_from_process"},
            env_file=Path(".env.test"),
        )

    assert actual.endswith("/test_from_process")
    file_values.assert_not_called()


def test_local_env_file_can_supply_test_database_url() -> None:
    parsed_values = dotenv_values(
        stream=StringIO("TEST_DATABASE_URL=postgresql+psycopg://local/test_from_file\n"),
        interpolate=False,
    )
    env_file = Path(".env.test")

    with patch("test_support.database.dotenv_values", return_value=parsed_values) as file_values:
        assert resolve_test_database_url(env={}, env_file=env_file).endswith("/test_from_file")
    file_values.assert_called_once_with(env_file, interpolate=False)


def test_missing_test_url_fails_without_using_database_url() -> None:
    with (
        patch("test_support.database.dotenv_values", return_value={}),
        pytest.raises(TestDatabaseConfigurationError, match="TEST_DATABASE_URL is required"),
    ):
        resolve_migration_database_url(
            "postgresql+psycopg://localhost/ai_life_memoir",
            mode="1",
            env={"DATABASE_URL": "postgresql+psycopg://localhost/ai_life_memoir"},
            env_file=Path(".env.test"),
        )


def test_non_test_database_is_rejected_before_connection() -> None:
    with pytest.raises(TestDatabaseConfigurationError, match="must contain `test`"):
        resolve_test_database_url(
            env={"TEST_DATABASE_URL": "postgresql+psycopg://localhost/ai_life_memoir"},
        )


def test_configuration_error_never_contains_password() -> None:
    probe = uuid.uuid4().hex
    with pytest.raises(TestDatabaseConfigurationError) as error:
        resolve_test_database_url(
            env={
                "TEST_DATABASE_URL": f"postgresql+psycopg://user:{probe}@localhost/ai_life_memoir"
            },
        )

    assert probe not in str(error.value)


def test_invalid_test_migration_mode_cannot_fall_back() -> None:
    with pytest.raises(TestDatabaseConfigurationError, match="TEST_MIGRATION_MODE"):
        resolve_migration_database_url(
            "postgresql+psycopg://localhost/ai_life_memoir",
            mode="yes",
            env={},
        )


def test_normal_alembic_mode_keeps_development_url() -> None:
    normal_url = "postgresql+psycopg://localhost/ai_life_memoir"

    assert (
        resolve_migration_database_url(
            normal_url,
            mode=None,
            env={"TEST_DATABASE_URL": "postgresql+psycopg://localhost/ai_life_memoir_test"},
        )
        == normal_url
    )


def test_non_postgresql_test_url_is_rejected() -> None:
    with pytest.raises(TestDatabaseConfigurationError, match="must use PostgreSQL"):
        resolve_test_database_url(
            env={"TEST_DATABASE_URL": "sqlite:///local_test.db"},
        )
