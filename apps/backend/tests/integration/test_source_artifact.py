"""PostgreSQL DDL probe must not import the dormant model in pytest."""

import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def source_artifact_postgres_probe():
    result = subprocess.run(
        [sys.executable, "-m", "tests.integration._source_artifact_probe", "postgresql"],
        capture_output=True,
        check=False,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout
    # Protocol regression: informational output must not precede/follow JSON.
    assert len(result.stdout.splitlines()) == 1, "Expected exactly one JSON payload"
    from app.database.base import Base

    assert "source_artifacts" not in Base.metadata.tables
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "case",
    ["definition", "creation", "checks", "locator", "unique", "fk", "rollback", "baseline"],
)
def test_source_artifact_postgres_prototype(source_artifact_postgres_probe, case):
    assert source_artifact_postgres_probe[case] == "PASS"
