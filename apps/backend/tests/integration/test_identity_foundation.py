import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.models.identity_foundation import AuthChallenge, PrivacyPolicyVersion, UserContact
from app.models.user import User
from app.schemas.rights_auth import ChallengeCreate
from app.services import privacy_policy, rights_auth
from app.services import user as user_service
from test_support.database import resolve_test_database_url
from tests.c1_support import TestOnlyRightsProvider, policy_documents

pytestmark = pytest.mark.integration


@pytest.fixture()
def migration_schema(monkeypatch):
    # Resolver validates PostgreSQL and a dedicated test database before any DDL.
    url = make_url(resolve_test_database_url())
    schema = "c1_migration_test_" + uuid.uuid4().hex
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = url.set(query={**url.query, "options": f"-csearch_path={schema}"})
    monkeypatch.setenv("TEST_DATABASE_URL", isolated.render_as_string(hide_password=False))
    monkeypatch.setenv("TEST_MIGRATION_MODE", "1")
    isolated_engine = create_engine(isolated, hide_parameters=True)
    try:
        yield Config("alembic.ini"), isolated_engine
    finally:
        isolated_engine.dispose()
        with engine.begin() as connection:
            # Exact server-generated schema in the already validated test DB only.
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def test_fresh_postgres_upgrade_backfill_and_safe_empty_downgrade(migration_schema):
    config, engine = migration_schema
    command.upgrade(config, "adf9c60d178d")
    old_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,password_hash,is_active) VALUES (:id,:email,:hash,true)"
            ),
            {"id": old_id, "email": "legacy-migration@example.com", "hash": "old-hash"},
        )
    command.upgrade(config, "head")
    command.check(config)
    assert {"privacy_policy_versions", "user_contacts", "auth_challenges"}.issubset(
        inspect(engine).get_table_names()
    )
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT principal_kind,auth_generation,email FROM users WHERE id=:id"),
            {"id": old_id},
        ).one()
        assert row.principal_kind == "account" and row.auth_generation == 1
        assert row.email == "legacy-migration@example.com"
        assert connection.execute(text("SELECT count(*) FROM user_contacts")).scalar_one() == 0
    command.downgrade(config, "adf9c60d178d")
    assert "user_contacts" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    command.check(config)


@pytest.mark.parametrize("unsafe_data", ["rights_only", "generation", "policy", "challenge"])
def test_downgrade_refuses_identity_or_privacy_evidence(migration_schema, unsafe_data):
    config, engine = migration_schema
    command.upgrade(config, "head")
    with Session(engine) as db:
        if unsafe_data == "rights_only":
            db.add(User(principal_kind="rights_only"))
        elif unsafe_data == "generation":
            db.add(User(email="generation@example.com", password_hash="hash", auth_generation=2))
        elif unsafe_data == "policy":
            privacy_policy.create_draft(
                db, version="evidence", parameters={}, notices={}, capabilities={}
            )
        else:
            provider = TestOnlyRightsProvider()
            rights_auth.create_challenge(
                db, ChallengeCreate(kind="email", channel="challenge@example.com"), provider
            )
        db.commit()
    with pytest.raises(RuntimeError, match="downgrade refused"):
        command.downgrade(config, "adf9c60d178d")
    command.check(config)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "c1a7d45e92b0"
        )


@pytest.mark.parametrize(
    "attributes",
    [
        {"principal_kind": "invalid"},
        {"principal_kind": "account"},
        {
            "principal_kind": "rights_only",
            "email": "credential@example.com",
            "password_hash": "hash",
        },
        {"principal_kind": "system", "email": "credential@example.com", "password_hash": "hash"},
        {"principal_kind": "rights_only", "auth_generation": 0},
    ],
)
def test_postgres_principal_checks(db_session, attributes):
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(User(**attributes))
        db_session.flush()


def test_postgres_jsonb_bytea_uniqueness_and_published_guard(db_session):
    parameters, notices, capabilities = policy_documents()
    policy = privacy_policy.create_draft(
        db_session,
        version="pg-policy",
        parameters=parameters,
        notices=notices,
        capabilities=capabilities,
    )
    assert isinstance(policy.id, uuid.UUID) and isinstance(policy.digest, bytes)
    assert (
        db_session.execute(
            text("SELECT jsonb_typeof(parameters) FROM privacy_policy_versions WHERE id=:id"),
            {"id": policy.id},
        ).scalar_one()
        == "object"
    )
    assert (
        db_session.execute(
            text("SELECT pg_typeof(digest)::text FROM privacy_policy_versions WHERE id=:id"),
            {"id": policy.id},
        ).scalar_one()
        == "bytea"
    )
    for duplicate_version, duplicate_digest in (
        (policy.version, b"x" * 32),
        ("different-version", policy.digest),
    ):
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(
                PrivacyPolicyVersion(
                    version=duplicate_version,
                    digest=duplicate_digest,
                    parameters={},
                    notices={},
                    capabilities={},
                    state="draft",
                )
            )
            db_session.flush()
    privacy_policy.publish_policy(db_session, policy.id)
    db_session.flush()
    assert policy.created_at.tzinfo is not None and policy.published_at.tzinfo is not None
    for statement in (
        "UPDATE privacy_policy_versions SET parameters='{}'::jsonb WHERE id=:id",
        "UPDATE privacy_policy_versions SET published_at=NULL WHERE id=:id",
        "DELETE FROM privacy_policy_versions WHERE id=:id",
    ):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(text(statement), {"id": policy.id})


def test_postgres_incomplete_active_policy_rejected_by_database(db_session):
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.add(
            PrivacyPolicyVersion(
                version="incomplete-active",
                state="active",
                parameters={},
                notices={},
                capabilities={},
                digest=b"a" * 32,
                published_at=datetime.now(UTC),
            )
        )
        db_session.flush()


def test_postgres_contact_partial_unique_and_restrict(db_session):
    user = User(principal_kind="rights_only")
    db_session.add(user)
    db_session.flush()
    first = UserContact(
        user_id=user.id,
        kind="email",
        value_ciphertext=b"opaque-fixture",
        lookup_hash=b"x" * 32,
        state="verified",
        verified_at=datetime.now(UTC),
    )
    db_session.add(first)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            UserContact(
                user_id=user.id,
                kind="email",
                value_ciphertext=b"second-fixture",
                lookup_hash=b"x" * 32,
                state="pending",
            )
        )
        db_session.flush()
    first.state, first.revoked_at = "revoked", datetime.now(UTC)
    db_session.flush()
    replacement = UserContact(
        user_id=user.id,
        kind="email",
        value_ciphertext=b"new-fixture",
        lookup_hash=b"x" * 32,
        state="verified",
        verified_at=datetime.now(UTC),
    )
    db_session.add(replacement)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(User).where(User.id == user.id))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            UserContact(
                user_id=uuid.uuid4(),
                kind="email",
                value_ciphertext=b"orphan",
                lookup_hash=b"o" * 32,
                state="pending",
            )
        )
        db_session.flush()


def test_postgres_challenge_checks_and_context_immutability(db_session):
    now = datetime.now(UTC)
    challenge = AuthChallenge(
        context_kind="rights_auth",
        channel_ciphertext=b"opaque-test",
        channel_hash=b"h" * 32,
        code_digest=b"c" * 32,
        state="pending",
        expires_at=now + timedelta(seconds=60),
        attempt_count=0,
    )
    db_session.add(challenge)
    db_session.flush()
    assert challenge.expires_at.tzinfo is not None
    for statement in (
        "UPDATE auth_challenges SET attempt_count=-1 WHERE id=:id",
        "UPDATE auth_challenges SET state='unknown' WHERE id=:id",
        "UPDATE auth_challenges SET state='consumed' WHERE id=:id",
        "UPDATE auth_challenges SET code_digest=:digest WHERE id=:id",
    ):
        with pytest.raises(DBAPIError), db_session.begin_nested():
            db_session.execute(text(statement), {"id": challenge.id, "digest": b"z" * 32})
    user = User(principal_kind="rights_only")
    db_session.add(user)
    db_session.flush()
    challenge.user_id = user.id
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(User).where(User.id == user.id))


def test_postgres_account_and_rights_regression(db_session):
    user = user_service.register_user(
        db_session, email="pg-auth@example.com", password="strong-password"
    )
    assert user.principal_kind == "account" and user.auth_generation == 1
    assert user_service.login_user(
        db_session, email="pg-auth@example.com", password="strong-password"
    )
    provider = TestOnlyRightsProvider()
    challenge_id = rights_auth.create_challenge(
        db_session, ChallengeCreate(kind="email", channel="pg-rights@example.com"), provider
    )
    token = rights_auth.verify_challenge(
        db_session, challenge_id, provider.deliveries[challenge_id], provider
    )
    assert token and db_session.get(AuthChallenge, challenge_id).state == "consumed"
    assert db_session.scalar(select(UserContact)).state == "verified"
