"""Run prototype tests outside pytest's production Base.metadata process."""

import json
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def source_artifact_sqlite_probe():
    result = subprocess.run(
        [sys.executable, "-m", "tests.integration._source_artifact_probe", "sqlite"],
        capture_output=True,
        check=False,
        text=True,
        timeout=90,
    )
    # Child reports safe categories only; never echo raw DB exception/stderr.
    assert result.returncode == 0, result.stdout
    assert len(result.stdout.splitlines()) == 1, "Expected exactly one JSON payload"
    from app.database.base import Base

    assert "source_artifacts" not in Base.metadata.tables
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "case",
    ["definition", "creation", "checks", "locator", "unique", "fk", "rollback"],
)
def test_source_artifact_sqlite_prototype(source_artifact_sqlite_probe, case):
    assert source_artifact_sqlite_probe[case] == "PASS"
