"""One-job B PostgreSQL CI lifecycle. No local provisioning or business imports.

Bootstrap stays in the trusted Manager. Child processes receive only the assigned
Owner/Runner URL. --self-check uses stdlib fakes and never opens Docker/PG.
This is SQL privilege isolation, not an OS sandbox for malicious Python.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "apps/backend"
B_FILE = "tests/integration/test_memory_workflow.py"
HEAD = "b196f0d47a21"
PARENT = "a196e4c72b08"
BOOTSTRAP = "ci_b_bootstrap"
JOB = "memory-workflow-postgres"
DOCKER = "/usr/bin/docker"
EXPECTED = (
    "test_postgres_schema_constraints_match_workflow_metadata",
    *(
        f"test_delta_b34_postgres_reference_constraints[{violation}]"
        for violation in (
            "current_missing_revision",
            "current_missing_proof",
            "current_cross_memory",
            "result_missing_memory",
            "result_missing_revision",
            "result_cross_memory",
            "section_missing_revision",
            "section_missing_proof",
            "section_cross_revision",
            "section_cross_proof",
        )
    ),
    *(
        f"test_postgres_zero_candidate_batch_restricts_parent_delete[{target}-{state}]"
        for target in ("interview", "member", "family")
        for state in ("pending", "completed", "failed", "discarded", "cancelled")
    ),
    "test_postgres_batch_subject_composite_fk_rejects_wrong_source",
    "test_postgres_revision_target_xor_check[none]",
    "test_postgres_revision_target_xor_check[both]",
    "test_postgres_revision_subject_fk_rejects_cross_member",
    "test_postgres_proposal_input_must_belong_to_target",
    "test_postgres_service_promotion_builds_exact_current_proof",
    "test_postgres_section_has_exact_same_memory_proof",
    "test_postgres_two_candidate_approvals_real_runner_connections",
    *(
        f"test_postgres_memoir_vs_synthetic_clear_two_commit_orders[{target}-{first}]"
        for target in ("proof", "body")
        for first in ("create", "clear")
    ),
    "test_postgres_provider_call_releases_parent_locks",
    "test_postgres_two_memory_approvals_real_runner_connections",
    "test_postgres_revision_ordinals_real_runner_connections[candidate]",
    "test_postgres_revision_ordinals_real_runner_connections[memory]",
    *(
        f"test_postgres_parent_delete_vs_new_reference_real_runner_connections[{target}]"
        for target in ("interview", "member", "family")
    ),
)
CONCURRENT = frozenset(
    name for name in EXPECTED if "real_runner_connections" in name or "two_commit_orders" in name
)


class GateError(RuntimeError):
    """Fixed categories only: do not stringify private driver/subprocess errors."""


def require(condition: bool, category: str) -> None:
    if not condition:
        raise GateError(category)


def context_gate(env: dict[str, str], platform: str) -> None:
    require(platform == "linux" and env.get("GITHUB_ACTIONS") == "true", "CIOnly")
    require(env.get("RUNNER_ENVIRONMENT") == "github-hosted", "HostedRunnerRequired")
    require(env.get("GITHUB_JOB") == JOB, "DedicatedJobRequired")
    require(env.get("GITHUB_WORKFLOW") == "Backend CI", "WorkflowMismatch")
    require(env.get("GITHUB_EVENT_NAME") in {"push", "pull_request"}, "EventRejected")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(bool(re.fullmatch(r"[1-9][0-9]*", env.get(key, ""))), "RunIdentityMissing")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", env.get("GITHUB_SHA", ""))), "CommitMissing")
    require(Path(env.get("GITHUB_WORKSPACE", "")).resolve() == ROOT, "WorkspaceMismatch")
    require(
        bool(re.fullmatch(r"[0-9a-f]{64}", env.get("CI_B_SERVICE_ID", ""))),
        "ServiceMissing",
    )
    port = env.get("CI_B_PORT", "")
    require(port.isdigit() and 0 < int(port) < 65536 and port != "55432", "PortRejected")
    require(bool(env.get("CI_B_BOOTSTRAP_PASSWORD")), "BootstrapMissing")
    require(bool(env.get("RUNNER_TEMP")), "TemporaryRootMissing")


def private_json(path: Path, data: dict) -> None:
    """Atomic receipt, private even when its eventual contents are public."""
    require(not path.is_symlink(), "EvidenceSymlink")
    pending = path.with_suffix(".pending")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pending, path)
    finally:
        if pending.exists():
            pending.unlink()


def group_empty(group: int) -> bool:
    """The child has its own session/group; no PID kill or prefix cleanup."""
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group:
                return False
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError):
            return False
    return True


def sanitized_junit(raw: bytes) -> tuple[bytes, dict]:
    require(0 < len(raw) <= 4_000_000, "JUnitSizeInvalid")
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "JUnitDTD")
    try:
        document = ET.fromstring(raw)
    except ET.ParseError:
        raise GateError("JUnitMalformed") from None
    cases = list(document.iter("testcase"))
    names = Counter(case.get("name") for case in cases)
    suites = list(document.iter("testsuite"))
    require(bool(suites), "JUnitSuiteMissing")
    require(names == Counter(EXPECTED), "JUnitSelectionMismatch")
    require(
        all(case.get("classname") == "tests.integration.test_memory_workflow" for case in cases),
        "JUnitNamespaceMismatch",
    )
    failures = sum(len(case.findall("failure")) + len(case.findall("error")) for case in cases)
    skipped = sum(len(case.findall("skipped")) for case in cases)
    require(
        sum(int(suite.get("tests", "-1")) for suite in suites) == 45,
        "JUnitCountMismatch",
    )
    clean = ET.Element("testsuites")
    suite = ET.SubElement(
        clean,
        "testsuite",
        name="B PostgreSQL",
        tests="45",
        failures=str(failures),
        errors="0",
        skipped=str(skipped),
    )
    for case in cases:
        output = ET.SubElement(
            suite,
            "testcase",
            classname="tests.integration.test_memory_workflow",
            name=case.get("name", ""),
        )
        for kind in ("failure", "error", "skipped"):
            if case.find(kind) is not None:
                ET.SubElement(output, kind, message="Details omitted from public evidence")
    summary = {"tests": 45, "failures": failures, "skipped": skipped, "concurrent": 11}
    return ET.tostring(clean, encoding="utf-8", xml_declaration=True), summary


def rejection_evidence(error: Exception, acl_denied: bool, positive_control: bool) -> dict:
    actual = getattr(error, "sqlstate", None)
    permission_category = "permission denied for database" in str(error).lower()
    require(acl_denied and positive_control, "ConnectionACLNotProven")
    require(actual in (None, "42501") and permission_category, "ConnectionDenialUnproven")
    return {
        "sqlstate": actual,  # never infer a fake SQLSTATE from text
        "category": "database_connect_permission_denied",
        "acl_connect": False,
        "same_credentials_positive_control": True,
    }


def child_environment(url: str, run: dict, temporary: Path) -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TMPDIR": str(temporary),
        "JWT_SECRET_KEY": "ci-b-synthetic-jwt-at-least-thirty-two-bytes",
        "JWT_ALGORITHM": "HS256",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
        "DEBUG": "False",
        "TEST_MIGRATION_MODE": "1",
        "TEST_DATABASE_URL": url,
        "DATABASE_URL": url,
        "MEMORY_B_ALLOCATION_RUN_ID": run["run"],
        "MEMORY_B_ALLOCATED_DATABASE": run["database"],
        "MEMORY_B_RUNNER_ROLE": run["runner"],
        "MEMORY_B_MULTI_CONNECTION_RUN_ID": run["run"],
    }


def child_main(mode: str, evidence: Path) -> int:
    """No bootstrap configuration reaches this exec'ed process."""
    require(sys.platform == "linux", "ChildLinuxRequired")
    require(mode in {"upgrade", "current", "check", "tests"}, "ChildModeRejected")
    sys.path.insert(0, str(BACKEND))
    # All configuration comes from Manager's allowlisted environment.
    for name in ("CI_B_BOOTSTRAP_PASSWORD", "GITHUB_TOKEN", "ACTIONS_RUNTIME_TOKEN"):
        require(name not in os.environ, "AdministrativeEnvironmentLeak")
    from sqlalchemy.engine import make_url

    url = make_url(os.environ["TEST_DATABASE_URL"])
    run = uuid.UUID(os.environ["MEMORY_B_ALLOCATION_RUN_ID"])
    database = "ai_memoir_b_ci_test_" + run.hex
    identity = (
        url.host == "127.0.0.1"
        and url.database == database
        and url.port is not None
        and url.username in {"b_ci_owner_" + run.hex, "b_ci_runner_" + run.hex}
    )
    require(identity, "ChildTargetMismatch")
    require(not (BACKEND / ".env").exists(), "ProjectDotenvRejected")
    if mode == "tests":
        require(url.username == "b_ci_runner_" + run.hex, "RunnerRequired")
        import pytest

        class Selection:
            def pytest_collection_modifyitems(self, items):
                require(
                    Counter(item.name for item in items) == Counter(EXPECTED),
                    "CollectionMismatch",
                )

        code = pytest.main(
            [
                "-m",
                "integration",
                B_FILE,
                "-q",
                "-p",
                "no:cacheprovider",
                "--junitxml=" + str(evidence / "private-junit.xml"),
            ],
            plugins=[Selection()],
        )
    else:
        from alembic import command
        from alembic.config import Config

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        if mode == "upgrade":
            require(url.username == "b_ci_owner_" + run.hex, "OwnerRequired")
            command.upgrade(config, HEAD)
        elif mode == "current":
            command.current(config)
        else:
            command.check(config)
        code = 0
    threads = [thread for thread in threading.enumerate() if thread is not threading.main_thread()]
    private_json(
        evidence / "child-receipt.json",
        {"mode": mode, "code": code, "threads": len(threads)},
    )
    require(not threads, "ChildThreadsRemain")
    return code


class Manager:
    def __init__(self):
        context_gate(dict(os.environ), sys.platform)  # before Docker or SQL
        base = Path(os.environ["RUNNER_TEMP"]).resolve()
        require(base.is_dir() and ROOT not in base.parents, "TemporaryRootRejected")
        self.evidence = (
            base / f"b-postgres-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
        )
        self.evidence.mkdir(mode=0o700)
        self.work = Path(tempfile.mkdtemp(prefix="private-", dir=base))
        os.chmod(self.work, 0o700)
        nonce = uuid.uuid4()
        self.record = {
            "run": str(nonce),
            "database": "ai_memoir_b_ci_test_" + nonce.hex,
            "owner": "b_ci_owner_" + nonce.hex,
            "runner": "b_ci_runner_" + nonce.hex,
            "commit": os.environ["GITHUB_SHA"],
            "github_run": os.environ["GITHUB_RUN_ID"],
            "github_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
            "job": JOB,
            "service": os.environ["CI_B_SERVICE_ID"],
            "port": int(os.environ["CI_B_PORT"]),
            "state": "PLANNED",
            "test_result": "not_run",
            "migration_result": "not_run",
            "post_check_result": "not_run",
            "cleanup": "not_attempted",
            "processes": [],
            "steps": [],
        }
        self.safe = True
        self.handles = []
        self.deadline = None
        self.control = None
        self.roles = False
        self.allocated = False
        self.roles_started = False
        self.create_started = False
        self.owner_password = uuid.uuid4().hex + uuid.uuid4().hex
        self.runner_password = uuid.uuid4().hex + uuid.uuid4().hex
        self.save()

    def save(self):
        private_json(self.evidence / "manifest.json", self.record)

    def begin_stage(self, name: str, seconds: int):
        self.deadline = time.monotonic() + seconds
        self.record["phase"] = name
        self.record["phase_budget_seconds"] = seconds
        self.save()

    def remaining(self, maximum: float) -> float:
        left = maximum if self.deadline is None else self.deadline - time.monotonic()
        require(left > 0, "StageDeadlineExceeded")
        return min(maximum, left)

    def connect_budget(self) -> int:
        seconds = int(self.remaining(5))
        require(seconds >= 1, "StageConnectBudgetExhausted")
        return seconds

    def sql_budget(self, connection):
        milliseconds = int(self.remaining(15) * 1000)
        require(milliseconds >= 1, "StageSQLBudgetExhausted")
        try:
            connection.execute(
                "SELECT set_config('statement_timeout',%s,false)",
                (f"{milliseconds}ms",),
            )
        except Exception:  # noqa: BLE001 -- timeout configuration outcome is unknown.
            self.safe = False
            raise GateError("SQLBudgetOutcomeUnknown") from None

    def process(self, args: list[str], env: dict[str, str], timeout: int, mode: str) -> bytes:
        budget = self.remaining(timeout)
        previously_safe = self.safe
        self.safe = False  # before launch: no exception may authorize cleanup
        before = datetime.now(UTC).isoformat()
        process = subprocess.Popen(
            args,
            cwd=BACKEND,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            start_new_session=True,
        )
        receipt = {"mode": mode, "pid": process.pid, "started_at": before, "exit": None}
        self.handles.append((process, receipt))  # retain the original object before I/O
        self.record["processes"].append(receipt)
        self.save()
        try:
            output, _private_errors = process.communicate(
                timeout=min(budget, self.remaining(timeout))
            )
        except subprocess.TimeoutExpired:
            self.safe = False
            raise GateError("ProcessExitUnknown") from None
        receipt.update(exit=process.returncode, pipe_eof=True)
        if not group_empty(process.pid):
            self.safe = False
            raise GateError("ProcessGroupRemains")
        self.save()
        self.safe = previously_safe  # only after native exit, EOF, group and receipt confirmation
        require(process.returncode == 0, "ProcessFailed")
        return output

    def inspect_service(self) -> dict:
        args = [
            DOCKER,
            "--host",
            "unix:///var/run/docker.sock",
            "inspect",
            "--format",
            (
                '{"id":{{json .Id}},"image":{{json .Config.Image}},"image_id":{{json .Image}},'
                '"running":{{json .State.Running}},"ports":{{json .NetworkSettings.Ports}}}'
            ),
            self.record["service"],
        ]
        raw = self.process(
            args, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}, 60, "service_inspect"
        )
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            raise GateError("ServiceMetadataInvalid") from None
        require(value["id"] == self.record["service"], "ServiceIDMismatch")
        require(
            value["image"] == "postgres:16.15" and value["running"] is True,
            "ServiceRejected",
        )
        ports = value["ports"].get("5432/tcp") or []
        require(
            any(int(row["HostPort"]) == self.record["port"] for row in ports),
            "ServicePortMismatch",
        )
        return value

    def rows(self, statement, parameters=()):
        self.sql_budget(self.control)
        try:
            return self.control.execute(statement, parameters).fetchall()
        except Exception:  # noqa: BLE001 -- lost SQL outcome forbids resource cleanup.
            self.safe = False  # uncertain SQL/DDL result => no automatic cleanup
            raise GateError("ManagementSQLUncertain") from None

    def execute(self, statement, parameters=()):
        self.sql_budget(self.control)
        try:
            self.control.execute(statement, parameters)
        except Exception:  # noqa: BLE001 -- no private driver errors leave Manager.
            self.safe = False
            raise GateError("ManagementSQLUncertain") from None

    def allocate(self):
        from psycopg import connect, sql

        self.sql = sql
        self.service = self.inspect_service()
        self.control = connect(
            host="127.0.0.1",
            port=self.record["port"],
            dbname="postgres",
            user=BOOTSTRAP,
            password=os.environ["CI_B_BOOTSTRAP_PASSWORD"],
            passfile="/dev/null",
            connect_timeout=self.connect_budget(),
            autocommit=True,
            options=f"-c statement_timeout={int(self.remaining(15) * 1000)} -c lock_timeout=3000",
        )
        require(
            self.rows("SELECT current_database(),session_user,current_user")[0]
            == ("postgres", BOOTSTRAP, BOOTSTRAP),
            "BootstrapMismatch",
        )
        require(self.rows("SHOW server_version_num")[0][0] == "160015", "VersionMismatch")
        require(
            self.rows("SELECT version()")[0][0].startswith("PostgreSQL 16.15"),
            "VersionMismatch",
        )
        self.record["version"] = "16.15"
        self.record["system_identifier"] = self.rows(
            "SELECT system_identifier::text FROM pg_control_system()"
        )[0][0]
        require(
            self.rows("SELECT pg_try_advisory_lock(196160015)")[0][0] is True,
            "ManagerBusy",
        )
        databases = {row[0] for row in self.rows("SELECT datname FROM pg_database")}
        require(
            databases == {"postgres", "template0", "template1"},
            "NotFreshDedicatedService",
        )
        require(
            not self.rows(
                "SELECT oid FROM pg_roles WHERE rolname IN (%s,%s)",
                (self.record["owner"], self.record["runner"]),
            ),
            "RoleCollision",
        )
        for name in ("postgres", "template0", "template1"):
            self.execute(
                sql.SQL("REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(name)
                )
            )
        self.roles_started = True
        # Role batch transaction commits atomically; a lost outcome remains retained.
        try:
            with self.control.transaction():
                for name in (self.record["owner"], self.record["runner"]):
                    self.sql_budget(self.control)
                    self.control.execute(
                        sql.SQL(
                            "CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "NOREPLICATION NOBYPASSRLS NOINHERIT"
                        ).format(sql.Identifier(name))
                    )
        except Exception:  # noqa: BLE001 -- uncertain role transaction retains resources.
            self.safe = False
            raise GateError("RoleCreationUncertain") from None
        self.roles = True
        for key in ("owner", "runner"):
            self.record[key + "_oid"] = self.rows(
                "SELECT oid FROM pg_roles WHERE rolname=%s", (self.record[key],)
            )[0][0]
        self.save()
        self.create_started = True
        self.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0").format(
                sql.Identifier(self.record["database"]),
                sql.Identifier(self.record["owner"]),
            )
        )
        self.allocated = True
        self.record["database_identity"] = list(
            self.rows(
                "SELECT oid,datdba FROM pg_database WHERE datname=%s",
                (self.record["database"],),
            )[0]
        )
        self.execute(
            sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                sql.Identifier(self.record["database"]), sql.Literal(self.record["run"])
            )
        )
        self.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(self.record["database"])
            )
        )
        self.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(self.record["database"]),
                sql.Identifier(self.record["runner"]),
            )
        )
        self.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(self.record["owner"]), sql.Literal(self.owner_password)
            )
        )
        self.record.update(state="ALLOCATED", image_id=self.service["image_id"])
        self.save()

    def url(self, identity: str) -> str:
        from sqlalchemy.engine import URL

        return URL.create(
            "postgresql+psycopg",
            username=self.record[identity],
            password=self.owner_password if identity == "owner" else self.runner_password,
            host="127.0.0.1",
            port=self.record["port"],
            database=self.record["database"],
            query={
                "connect_timeout": "5",
                "passfile": "/dev/null",
                "options": "-c statement_timeout=15000",
            },
        ).render_as_string(hide_password=False)

    def step(self, mode: str, identity: str):
        receipt = self.work / "child-receipt.json"
        receipt.unlink(missing_ok=True)
        raw_xml = self.work / "private-junit.xml"
        raw_xml.unlink(missing_ok=True)
        environment = child_environment(self.url(identity), self.record, self.work)
        try:
            self.process(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(Path(__file__).resolve()),
                    "--child",
                    mode,
                    "--evidence",
                    str(self.work),
                ],
                environment,
                180,
                mode,
            )
        except GateError:
            try:
                require(
                    receipt.is_file() and not receipt.is_symlink(),
                    "ChildReceiptMissing",
                )
                result = json.loads(receipt.read_text())
                expected_code = self.record["processes"][-1]["exit"]
                require(
                    result == {"mode": mode, "code": expected_code, "threads": 0},
                    "ChildFailureReceiptUnconfirmed",
                )
            except (GateError, OSError, ValueError, KeyError, IndexError):
                self.safe = False
            if mode == "tests" and self.safe and raw_xml.is_file() and not raw_xml.is_symlink():
                try:
                    public, summary = sanitized_junit(raw_xml.read_bytes())
                    (self.evidence / "b-postgres.xml").write_bytes(public)
                    os.chmod(self.evidence / "b-postgres.xml", 0o600)
                    self.record["junit"] = summary
                    self.save()
                except (GateError, ValueError):
                    self.record["junit_failure"] = "JUnitNotVerified"
            raise
        previously_safe = self.safe
        self.safe = False
        require(receipt.is_file() and not receipt.is_symlink(), "ChildReceiptMissing")
        result = json.loads(receipt.read_text())
        require(result == {"mode": mode, "code": 0, "threads": 0}, "ChildResultMismatch")
        self.safe = previously_safe
        self.record["steps"].append({"mode": mode, "identity": identity, "exit": 0})
        if mode == "tests":
            require(raw_xml.is_file() and not raw_xml.is_symlink(), "JUnitMissing")
            public, summary = sanitized_junit(raw_xml.read_bytes())
            (self.evidence / "b-postgres.xml").write_bytes(public)
            os.chmod(self.evidence / "b-postgres.xml", 0o600)
            require(not summary["failures"] and not summary["skipped"], "TestsIncomplete")
            self.record["test_result"] = "passed"
            self.record["junit"] = summary
        self.save()

    def ready_runner(self):
        try:
            self._ready_runner()
        except Exception:  # noqa: BLE001 -- any unconfirmed preparation SQL retains resources.
            self.safe = False
            raise GateError("RunnerPreparationUncertain") from None

    def _ready_runner(self):
        from psycopg import OperationalError, connect

        sql = self.sql
        self.execute(
            sql.SQL("ALTER ROLE {} NOLOGIN PASSWORD NULL").format(
                sql.Identifier(self.record["owner"])
            )
        )
        require(
            self.rows(
                "SELECT count(*) FROM pg_stat_activity WHERE usename=%s",
                (self.record["owner"],),
            )[0][0]
            == 0,
            "OwnerSessionsRemain",
        )
        self.execute(
            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(self.record["runner"]), sql.Literal(self.runner_password)
            )
        )
        # Bootstrap manages this exact target only; no bootstrap URL reaches children.
        with connect(
            host="127.0.0.1",
            port=self.record["port"],
            dbname=self.record["database"],
            user=BOOTSTRAP,
            password=os.environ["CI_B_BOOTSTRAP_PASSWORD"],
            passfile="/dev/null",
            connect_timeout=self.connect_budget(),
            autocommit=True,
            options=f"-c statement_timeout={int(self.remaining(15) * 1000)}",
        ) as target:
            self.sql_budget(target)
            target.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            self.sql_budget(target)
            target.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(self.record["runner"])
                )
            )
            self.sql_budget(target)
            target.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}"
                ).format(sql.Identifier(self.record["runner"]))
            )
            self.sql_budget(target)
            target.execute(
                sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                    sql.Identifier(self.record["runner"])
                )
            )
        parameters = {
            "host": "127.0.0.1",
            "port": self.record["port"],
            "dbname": self.record["database"],
            "user": self.record["runner"],
            "password": self.runner_password,
            "passfile": "/dev/null",
            "connect_timeout": self.connect_budget(),
            "options": f"-c statement_timeout={int(self.remaining(15) * 1000)}",
            "autocommit": True,
        }
        with connect(**parameters) as runner:
            self.sql_budget(runner)
            require(
                runner.execute("SELECT current_database(),current_user").fetchone()
                == (self.record["database"], self.record["runner"]),
                "RunnerIdentityMismatch",
            )
            self.sql_budget(runner)
            require(
                not any(
                    runner.execute(
                        "SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls,rolreplication "
                        "FROM pg_roles WHERE rolname=current_user"
                    ).fetchone()
                ),
                "RunnerAdminPrivileges",
            )
            self.sql_budget(runner)
            require(
                not runner.execute(
                    "SELECT has_database_privilege(current_user,current_database(),'CREATE') "
                    "OR has_database_privilege(current_user,current_database(),'TEMP') "
                    "OR has_schema_privilege(current_user,'public','CREATE')"
                ).fetchone()[0],
                "RunnerDDLPrivileges",
            )
            self.sql_budget(runner)
            require(
                runner.execute("SELECT version_num FROM alembic_version").fetchall() == [(HEAD,)],
                "SchemaHeadMismatch",
            )
        require(
            not self.rows(
                "SELECT 1 FROM pg_auth_members WHERE member=%s",
                (self.record["runner_oid"],),
            ),
            "RunnerMembershipUnexpected",
        )
        require(
            self.record["database_identity"][1] == self.record["owner_oid"],
            "OwnerMismatch",
        )
        denials = {}
        for database in ("postgres", "template1"):
            acl = self.rows(
                "SELECT has_database_privilege(%s,%s,'CONNECT')",
                (self.record["runner"], database),
            )[0][0]
            require(acl is False, "ControlConnectGranted")
            try:
                parameters["connect_timeout"] = self.connect_budget()
                with connect(**(parameters | {"dbname": database})):
                    raise GateError("ControlConnectionAllowed")
            except OperationalError as error:
                denials[database] = rejection_evidence(error, not acl, True)
        self.record.update(state="MIGRATED", connection_denials=denials)
        self.save()

    def cleanup(self):
        require(self.safe, "ExitOrDDLUnknownRetain")
        for process, receipt in self.handles:
            require(
                process.returncode is not None
                and receipt.get("exit") == process.returncode
                and receipt.get("pipe_eof") is True
                and group_empty(process.pid),
                "TrackedProcessNotQuiescent",
            )
        if self.control is None:
            return
        if self.roles_started and not self.roles:
            raise GateError("RoleOutcomeUnknownRetain")
        if self.create_started and not self.allocated:
            raise GateError("CreateOutcomeUnknownRetain")
        if self.roles:
            for key in ("owner", "runner"):
                expected = self.record.get(key + "_oid")
                require(
                    isinstance(expected, int)
                    and self.rows("SELECT oid FROM pg_roles WHERE rolname=%s", (self.record[key],))
                    == [(expected,)],
                    "RoleIdentityUnconfirmed",
                )
        if self.allocated:
            require(self.inspect_service() == self.service, "ServiceChanged")
            require(
                self.rows("SELECT system_identifier::text FROM pg_control_system()")[0][0]
                == self.record["system_identifier"],
                "ClusterChanged",
            )
            actual = self.rows(
                "SELECT oid,datdba,shobj_description(oid,'pg_database') FROM pg_database "
                "WHERE datname=%s",
                (self.record["database"],),
            )
            require(
                actual == [(*self.record["database_identity"], self.record["run"])],
                "DatabaseChanged",
            )
            for key in ("owner", "runner"):
                require(
                    self.rows("SELECT oid FROM pg_roles WHERE rolname=%s", (self.record[key],))
                    == [(self.record[key + "_oid"],)],
                    "RoleChanged",
                )
            require(
                self.rows(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=%s",
                    (self.record["database"],),
                )[0][0]
                == 0,
                "SessionsRemain",
            )
            self.record["state"] = "CLEANING"
            self.save()
            self.execute(
                self.sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(
                    self.sql.Identifier(self.record["database"])
                )
            )
            require(
                self.rows(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname=%s",
                    (self.record["database"],),
                )[0][0]
                == 0,
                "LateSessionRetain",
            )
            self.execute(
                self.sql.SQL("DROP DATABASE {}").format(
                    self.sql.Identifier(self.record["database"])
                )
            )
            require(
                not self.rows(
                    "SELECT oid FROM pg_database WHERE datname=%s",
                    (self.record["database"],),
                ),
                "DatabaseNotAbsent",
            )
            self.record["database_absent"] = True
        if self.roles:
            for key in ("runner", "owner"):
                self.execute(
                    self.sql.SQL("DROP ROLE {}").format(self.sql.Identifier(self.record[key]))
                )
            require(
                not self.rows(
                    "SELECT oid FROM pg_roles WHERE rolname IN (%s,%s)",
                    (self.record["owner"], self.record["runner"]),
                ),
                "RolesNotAbsent",
            )
            self.record["roles_absent"] = True
        self.record.update(state="CLEANED", cleanup="verified")
        self.save()

    def note_failure(self, error: Exception):
        self.record["failure"] = (
            str(error) if isinstance(error, GateError) else type(error).__name__
        )
        if self.record.get("migration_result") == "running":
            self.record["migration_result"] = "failed"
        if self.record["test_result"] != "passed":
            self.record["test_result"] = (
                "failed" if self.record["state"] == "RUNNING" else "not_run"
            )
        elif self.record["state"] == "TESTED":
            self.record["post_check_result"] = "failed"

    def run(self) -> int:
        def interrupted(_signum, _frame):
            self.safe = False
            raise GateError("JobInterruptedRetain")

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        success = False
        try:
            self.begin_stage("preflight", 60)
            require(not (BACKEND / ".env").exists(), "ProjectDotenvRejected")
            current = (
                self.process(
                    ["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"],
                    {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                    60,
                    "commit_identity",
                )
                .decode()
                .strip()
            )
            require(current == self.record["commit"], "CheckoutMismatch")
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            config = Config()
            config.set_main_option("script_location", str(BACKEND / "alembic"))
            scripts = ScriptDirectory.from_config(config)
            require(scripts.get_heads() == [HEAD], "MigrationHeadMismatch")
            require(
                scripts.get_revision(HEAD).down_revision == PARENT,
                "MigrationParentMismatch",
            )
            self.record["source_hashes"] = {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (
                    Path(__file__).resolve(),
                    ROOT / ".github/workflows/backend-ci.yml",
                    BACKEND / B_FILE,
                    BACKEND / "alembic/versions/b196f0d47a21_memory_candidate_revision_review.py",
                )
            }
            self.begin_stage("allocation", 60)
            self.allocate()
            self.record["migration_result"] = "running"
            for mode in ("upgrade", "current", "check"):
                self.begin_stage("pre-" + mode, 180)
                self.step(mode, "owner")
            self.record["migration_result"] = "passed"
            self.begin_stage("runner_permissions", 60)
            self.ready_runner()
            self.record["state"] = "RUNNING"
            self.save()
            self.begin_stage("tests", 180)
            self.step("tests", "runner")
            self.record["state"] = "TESTED"
            for mode in ("current", "check"):
                self.begin_stage("post-" + mode, 180)
                self.step(mode, "runner")
            self.record["state"] = "POST_CHECKED"
            self.record["post_check_result"] = "passed"
            self.save()
            success = True
        except Exception as error:  # noqa: BLE001 -- sanitized top-level lifecycle failure.
            self.note_failure(error)
        finally:
            try:
                self.begin_stage("cleanup", 60)
                self.cleanup()
            except Exception as error:  # noqa: BLE001 -- cleanup must fail closed.
                self.record.update(
                    state="RETAINED",
                    cleanup="unknown" if not self.safe else "failed",
                    cleanup_failure=str(error)
                    if isinstance(error, GateError)
                    else type(error).__name__,
                )
            if self.control is not None:
                try:
                    self.control.execute("SELECT pg_advisory_unlock(196160015)")
                    self.control.close()
                except Exception:  # noqa: BLE001 -- do not mask an unknown Manager exit.
                    self.record["management_exit"] = "unknown"
                    success = False
            if self.safe and self.record["cleanup"] == "verified":
                try:
                    for name in ("child-receipt.json", "private-junit.xml"):
                        (self.work / name).unlink(missing_ok=True)
                    self.work.rmdir()
                    self.record["private_files_removed"] = True
                except OSError:
                    self.record["private_files_removed"] = False
                    success = False
            self.record["overall"] = (
                "PASS" if success and self.record["cleanup"] == "verified" else "FAIL"
            )
            self.save()
            # Only approved, sanitized evidence is published. Private stdout/XML
            # and credentials are never recursively uploaded.
            private_json(
                self.evidence / "summary.json",
                {
                    key: self.record.get(key)
                    for key in (
                        "overall",
                        "test_result",
                        "migration_result",
                        "post_check_result",
                        "cleanup",
                        "failure",
                        "cleanup_failure",
                        "junit",
                    )
                },
            )
        print(json.dumps({"overall": self.record["overall"], "cleanup": self.record["cleanup"]}))
        return 0 if self.record["overall"] == "PASS" else 1


def self_check() -> int:
    """Pure contract checks, not real PostgreSQL/CI evidence."""
    require(len(EXPECTED) == 45 and len(set(EXPECTED)) == 45, "ExpectedCaseCount")
    require(len(CONCURRENT) == 11, "ConcurrencyCount")
    checks = 2
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests="45")
    for name in EXPECTED:
        ET.SubElement(
            suite,
            "testcase",
            name=name,
            classname="tests.integration.test_memory_workflow",
        )
    original = ET.tostring(root)
    public, result = sanitized_junit(original)
    require(
        result == {"tests": 45, "failures": 0, "skipped": 0, "concurrent": 11},
        "SummaryMismatch",
    )
    require(b"testsuites" in public, "PublicEvidenceMissing")
    checks += 1
    for mutation in ("skip", "duplicate", "missing", "namespace", "dtd", "malformed"):
        tree = ET.fromstring(original)
        case = tree.find("./testsuite/testcase")
        if mutation == "skip":
            ET.SubElement(case, "skipped", message="private")
        elif mutation == "duplicate":
            tree.find("testsuite").append(ET.Element("testcase", name=EXPECTED[0]))
        elif mutation == "missing":
            tree.find("testsuite").remove(case)
        elif mutation == "namespace":
            case.set("classname", "other.module")
        payload = ET.tostring(tree)
        if mutation == "dtd":
            payload = b"<!DOCTYPE evil>" + payload
        if mutation == "malformed":
            payload = b"not-xml"
        if mutation == "skip":
            _, summary = sanitized_junit(payload)
            require(summary["skipped"] == 1, "SkipNotDetected")
        else:
            try:
                sanitized_junit(payload)
            except (GateError, ValueError):
                pass
            else:
                raise GateError("InvalidJUnitAccepted")
        checks += 1

    class Failure(Exception):
        sqlstate = None

    evidence = rejection_evidence(Failure("permission denied for database"), True, True)
    require(evidence["sqlstate"] is None, "FakeSQLState")
    checks += 1
    for message in ("password authentication failed", "connection timeout"):
        try:
            rejection_evidence(Failure(message), True, True)
        except GateError:
            checks += 1
        else:
            raise GateError("FalseDenialEvidence")
    env = child_environment(
        "synthetic-runner-url",
        {
            "run": str(uuid.uuid4()),
            "database": "synthetic_test",
            "runner": "synthetic_runner",
        },
        Path("/tmp/synthetic"),
    )
    require(
        "CI_B_BOOTSTRAP_PASSWORD" not in env and "GITHUB_TOKEN" not in env,
        "EnvironmentLeak",
    )
    require(env["TEST_DATABASE_URL"] == env["DATABASE_URL"], "TargetMismatch")
    checks += 1
    try:
        context_gate({}, "win32")
    except GateError:
        checks += 1
    else:
        raise GateError("LocalDefaultAccepted")
    context = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "GITHUB_JOB": JOB,
        "GITHUB_WORKFLOW": "Backend CI",
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKSPACE": str(ROOT),
        "CI_B_SERVICE_ID": "b" * 64,
        "CI_B_PORT": "5432",
        "CI_B_BOOTSTRAP_PASSWORD": "synthetic-context-only",
        "RUNNER_TEMP": "/tmp/synthetic",
    }
    context_gate(context, "linux")
    checks += 1
    for key in context:
        incomplete = dict(context)
        incomplete.pop(key)
        try:
            context_gate(incomplete, "linux")
        except GateError:
            checks += 1
        else:
            raise GateError("IncompleteContextAccepted")
    for category in ("exit", "role", "create"):
        manager = object.__new__(Manager)
        manager.safe = category != "exit"
        manager.handles = []
        manager.control = object()
        manager.roles_started = category == "role"
        manager.roles = False
        manager.create_started = category == "create"
        manager.allocated = False
        try:
            manager.cleanup()
        except GateError:
            checks += 1
        else:
            raise GateError("UnknownOutcomeCleanupAccepted")
    tree = ET.fromstring(original)
    ET.SubElement(tree.find("./testsuite/testcase"), "failure").text = "PRIVATE SQL AND TOKEN"
    sanitized, failed = sanitized_junit(ET.tostring(tree))
    require(failed["failures"] == 1 and b"PRIVATE SQL" not in sanitized, "ErrorDetailsLeak")
    checks += 1
    original_popen, original_group = subprocess.Popen, globals()["group_empty"]
    try:
        for fault in ("receipt_write", "communication", "timeout", "group"):

            class FakeProcess:
                pid = 424242
                returncode = None

                def __init__(self, failure):
                    self.failure = failure

                def communicate(self, timeout):
                    if self.failure == "communication":
                        raise OSError("mock communication failure")
                    if self.failure == "timeout":
                        raise subprocess.TimeoutExpired("synthetic", timeout)
                    self.returncode = 0
                    return b"synthetic", b""

            fake = FakeProcess(fault)
            subprocess.Popen = lambda *args, _fake=fake, **kwargs: _fake
            globals()["group_empty"] = lambda _pid, _fault=fault: _fault != "group"
            manager = object.__new__(Manager)
            manager.safe = True
            manager.deadline = time.monotonic() + 60
            manager.handles = []
            manager.record = {"processes": []}

            def save(_fault=fault):
                if _fault == "receipt_write":
                    raise OSError("mock receipt failure")

            manager.save = save
            try:
                manager.process(["mock-only"], {}, 60, "synthetic")
            except (OSError, GateError):
                require(
                    not manager.safe and manager.handles[0][0] is fake,
                    "OriginalProcessNotRetained",
                )
                checks += 1
            else:
                raise GateError("ProcessFailureAuthorizedCleanup")
    finally:
        subprocess.Popen = original_popen
        globals()["group_empty"] = original_group
    manager = object.__new__(Manager)
    manager.safe = True

    def unknown_grant():
        raise OSError("mock lost grant outcome")

    manager._ready_runner = unknown_grant
    try:
        manager.ready_runner()
    except GateError:
        require(not manager.safe, "GrantUncertaintyAllowedCleanup")
        checks += 1
    else:
        raise GateError("GrantFaultAccepted")
    manager.deadline = time.monotonic() - 1
    try:
        manager.remaining(60)
    except GateError:
        checks += 1
    else:
        raise GateError("ExpiredStageContinued")
    manager.deadline = time.monotonic() + 0.25
    try:
        manager.connect_budget()
    except GateError:
        checks += 1
    else:
        raise GateError("ConnectionExceededRemainingStage")
    original_clock = time.monotonic
    try:
        manager.record = {}
        manager.save = lambda: None
        time.monotonic = lambda: 100.0
        manager.begin_stage("allocation", 60)
        time.monotonic = lambda: 159.0
        require(
            manager.remaining(60) == 1 and manager.connect_budget() == 1,
            "StageBudgetResetPerOperation",
        )
        checks += 1
        time.monotonic = lambda: 160.0
        try:
            manager.remaining(60)
        except GateError:
            checks += 1
        else:
            raise GateError("StageDeadlineNotShared")
    finally:
        time.monotonic = original_clock
    manager.safe = True
    manager.handles = [(type("PendingProcess", (), {"returncode": None, "pid": 1})(), {})]
    try:
        manager.cleanup()
    except GateError:
        checks += 1
    else:
        raise GateError("PendingTrackedProcessCleanupAllowed")
    manager.record = {"state": "TESTED", "test_result": "passed"}
    manager.note_failure(GateError("SyntheticPostCheckFailed"))
    require(
        manager.record["test_result"] == "passed"
        and manager.record["post_check_result"] == "failed",
        "TestResultOverwritten",
    )
    checks += 1
    print(json.dumps({"mock_contract_checks": checks, "real_postgresql": "NOT RUN"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--ci-manager", action="store_true")
    parser.add_argument("--child", choices=("upgrade", "current", "check", "tests"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    require(
        sum((args.self_check, args.ci_manager, args.child is not None)) == 1,
        "ModeRequired",
    )
    if args.self_check:
        return self_check()
    if args.child:
        require(args.evidence is not None, "ChildEvidenceRequired")
        return child_main(args.child, args.evidence)
    return Manager().run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GateError as failure:
        print(json.dumps({"failure": str(failure)}))
        raise SystemExit(1) from None
    except Exception as failure:  # noqa: BLE001 -- never print credentials or exception repr.
        print(json.dumps({"failure": type(failure).__name__}))
        raise SystemExit(1) from None
