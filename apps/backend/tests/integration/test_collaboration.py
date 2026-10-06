import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import create_verification_proof
from app.models.collaboration import (
    CommandIdempotencyRecord,
    FamilyInvitation,
    FamilyMembership,
)
from app.models.family import Family
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.user import User
from app.schemas.collaboration import InvitationCreate
from app.services import collaboration as collaboration_service
from app.services import privacy_policy
from test_support.database import resolve_test_database_url
from tests.c1_support import TestOnlyRightsProvider, policy_documents

pytestmark = pytest.mark.integration


@pytest.fixture()
def c2a_migration_schema(monkeypatch):
    url = make_url(resolve_test_database_url())
    schema = "c2a_migration_test_" + uuid.uuid4().hex
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
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def _account(email: str) -> User:
    return User(principal_kind="account", email=email, password_hash="test-hash")


def _approved_invitation(family_id, owner_id, recipient_hash, *, recipient_user_id=None):
    now = datetime.now(UTC)
    return FamilyInvitation(
        id=uuid.uuid4(),
        family_id=family_id,
        requested_by_user_id=owner_id,
        recipient_hash=recipient_hash,
        recipient_ciphertext=b"opaque-integration-ciphertext",
        recipient_user_id=recipient_user_id,
        approved_by_user_id=owner_id,
        token_digest=uuid.uuid4().bytes + uuid.uuid4().bytes,
        state="approved",
        version=1,
        approved_at=now,
        expires_at=now + timedelta(minutes=5),
    )


def _acceptance_fixture(postgres_engine):
    provider = TestOnlyRightsProvider()
    token = "integration-invitation-token-" + uuid.uuid4().hex
    now = datetime.now(UTC)
    with Session(postgres_engine, expire_on_commit=False) as db:
        suffix = uuid.uuid4().hex
        owner = _account(f"accept-owner-{suffix}@example.com")
        recipient = _account(f"accept-recipient-{suffix}@example.com")
        db.add_all([owner, recipient])
        db.flush()
        family = Family(owner_id=owner.id, name="Acceptance race")
        db.add(family)
        db.flush()
        recipient_hash = provider.lookup("email", recipient.email)
        invitation = _approved_invitation(
            family.id,
            owner.id,
            recipient_hash,
            recipient_user_id=recipient.id,
        )
        invitation.token_digest = collaboration_service.invitation_token_digest(
            provider, invitation.id, token
        )
        db.add(invitation)
        db.flush()
        contact = UserContact(
            user_id=recipient.id,
            kind="email",
            value_ciphertext=provider.encrypt(recipient.email.encode()),
            lookup_hash=recipient_hash,
            state="verified",
            verified_at=now,
        )
        db.add(contact)
        db.flush()
        challenge = AuthChallenge(
            user_id=recipient.id,
            context_kind="invitation_acceptance",
            context_id=invitation.id,
            channel_ciphertext=provider.encrypt(b"integration-context"),
            channel_hash=recipient_hash,
            code_digest=provider.code_digest(uuid.uuid4(), "unused"),
            state="consumed",
            expires_at=now + timedelta(minutes=5),
            consumed_at=now,
            attempt_count=0,
        )
        db.add(challenge)
        db.flush()
        proof = create_verification_proof(
            subject=str(recipient.id),
            auth_generation=recipient.auth_generation,
            context_kind="invitation_acceptance",
            context_id=str(invitation.id),
            challenge_id=str(challenge.id),
            contact_id=str(contact.id),
            expires_at=now + timedelta(minutes=3),
        )
        result = {
            "owner_id": owner.id,
            "recipient_id": recipient.id,
            "family_id": family.id,
            "invitation_id": invitation.id,
            "version": invitation.version,
            "token": token,
            "proof": proof,
            "contact_id": contact.id,
            "challenge_id": challenge.id,
        }
        db.commit()
    return provider, result


def _cleanup_acceptance_fixture(postgres_engine, fixture):
    with postgres_engine.begin() as connection:
        connection.execute(
            delete(CommandIdempotencyRecord).where(
                CommandIdempotencyRecord.actor_user_id == fixture["recipient_id"]
            )
        )
        connection.execute(delete(AuthChallenge).where(AuthChallenge.id == fixture["challenge_id"]))
        connection.execute(delete(UserContact).where(UserContact.id == fixture["contact_id"]))
        connection.execute(delete(Family).where(Family.id == fixture["family_id"]))
        connection.execute(
            delete(User).where(User.id.in_([fixture["owner_id"], fixture["recipient_id"]]))
        )


def _collaboration_fixture(engine):
    provider = TestOnlyRightsProvider()
    with Session(engine, expire_on_commit=False) as db:
        parameters, notices, capabilities = policy_documents()
        policy = privacy_policy.create_draft(
            db,
            version="concurrency-policy",
            parameters=parameters,
            notices=notices,
            capabilities=capabilities,
        )
        privacy_policy.publish_policy(db, policy.id)
        suffix = uuid.uuid4().hex
        owner = _account(f"flow-owner-{suffix}@example.com")
        collaborator = _account(f"flow-collaborator-{suffix}@example.com")
        db.add_all([owner, collaborator])
        db.flush()
        family = Family(owner_id=owner.id, name="Collaboration race")
        db.add(family)
        db.flush()
        membership = FamilyMembership(
            family_id=family.id,
            user_id=collaborator.id,
            role="collaborator",
            state="active",
            generation=1,
            joined_at=datetime.now(UTC),
        )
        db.add(membership)
        db.flush()
        result = {
            "owner_id": owner.id,
            "collaborator_id": collaborator.id,
            "family_id": family.id,
            "membership_id": membership.id,
        }
        db.commit()
    return provider, result


def _pending_invitation(engine, provider, fixture, channel):
    with Session(engine, expire_on_commit=False) as db:
        invitation = FamilyInvitation(
            id=uuid.uuid4(),
            family_id=fixture["family_id"],
            requested_by_user_id=fixture["collaborator_id"],
            recipient_hash=provider.lookup("email", channel),
            recipient_ciphertext=provider.encrypt(
                ('{"kind":"email","channel":"' + channel + '"}').encode()
            ),
            state="pending_owner",
            version=1,
        )
        db.add(invitation)
        db.commit()
        return invitation.id


def test_fresh_upgrade_has_c2a_schema_and_restrict_owner(c2a_migration_schema):
    config, engine = c2a_migration_schema
    command.upgrade(config, "head")
    command.check(config)
    inspector = inspect(engine)
    assert {
        "command_idempotency_records",
        "family_invitations",
        "family_memberships",
    }.issubset(inspector.get_table_names())
    owner_fk = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("families")
        if foreign_key["constrained_columns"] == ["owner_id"]
    )
    assert owner_fk["options"].get("ondelete") == "RESTRICT"
    command.downgrade(config, "c1a7d45e92b0")
    assert "family_memberships" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    command.check(config)


def test_postgres_collaboration_constraints_and_fk_actions(db_session):
    suffix = uuid.uuid4().hex
    owner = _account(f"owner-{suffix}@example.com")
    member = _account(f"member-{suffix}@example.com")
    other = _account(f"other-{suffix}@example.com")
    db_session.add_all([owner, member, other])
    db_session.flush()
    family = Family(owner_id=owner.id, name="C2A constraints")
    db_session.add(family)
    db_session.flush()
    invitation = _approved_invitation(family.id, owner.id, b"r" * 32, recipient_user_id=member.id)
    db_session.add(invitation)
    db_session.flush()
    membership = FamilyMembership(
        family_id=family.id,
        user_id=member.id,
        role="collaborator",
        state="active",
        generation=1,
        accepted_invitation_id=invitation.id,
        joined_at=datetime.now(UTC),
    )
    db_session.add(membership)
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(User).where(User.id == owner.id))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(delete(User).where(User.id == member.id))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            FamilyMembership(
                family_id=family.id,
                user_id=other.id,
                role="owner",
                state="active",
                generation=1,
                joined_at=datetime.now(UTC),
            )
        )
        db_session.flush()

    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE family_invitations SET recipient_hash=:hash WHERE id=:id"),
            {"hash": b"s" * 32, "id": invitation.id},
        )
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE family_memberships SET user_id=:user_id WHERE id=:id"),
            {"user_id": other.id, "id": membership.id},
        )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            FamilyMembership(
                family_id=family.id,
                user_id=member.id,
                role="collaborator",
                state="active",
                generation=1,
                joined_at=datetime.now(UTC),
            )
        )
        db_session.flush()

    db_session.delete(invitation)
    db_session.flush()
    db_session.refresh(membership)
    assert membership.accepted_invitation_id is None
    membership_id = membership.id
    db_session.delete(family)
    db_session.flush()
    db_session.expire_all()
    assert db_session.get(FamilyMembership, membership_id) is None


def test_postgres_partial_uniques_and_idempotency_digest(db_session):
    suffix = uuid.uuid4().hex
    owner = _account(f"partial-owner-{suffix}@example.com")
    db_session.add(owner)
    db_session.flush()
    family = Family(owner_id=owner.id, name="Partial unique")
    db_session.add(family)
    db_session.flush()
    first = _approved_invitation(family.id, owner.id, b"p" * 32)
    db_session.add(first)
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_approved_invitation(family.id, owner.id, b"p" * 32))
        db_session.flush()
    first.state = "revoked"
    db_session.flush()
    replacement = _approved_invitation(family.id, owner.id, b"p" * 32)
    db_session.add(replacement)
    db_session.flush()
    token_collision = _approved_invitation(family.id, owner.id, b"q" * 32)
    token_collision.token_digest = replacement.token_digest
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(token_collision)
        db_session.flush()

    record = CommandIdempotencyRecord(
        actor_user_id=owner.id,
        operation="integration.operation",
        idempotency_key=uuid.uuid4(),
        request_digest=b"d" * 32,
        state="processing",
    )
    db_session.add(record)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            CommandIdempotencyRecord(
                actor_user_id=owner.id,
                operation=record.operation,
                idempotency_key=record.idempotency_key,
                request_digest=b"e" * 32,
                state="processing",
            )
        )
        db_session.flush()

    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE command_idempotency_records SET operation='changed' WHERE id=:id"),
            {"id": record.id},
        )
    record.state = "completed"
    record.response_status = 200
    record.response_body = {"state": "complete"}
    record.completed_at = datetime.now(UTC)
    db_session.flush()
    with pytest.raises(DBAPIError), db_session.begin_nested():
        db_session.execute(
            text("UPDATE command_idempotency_records SET response_body='{}'::jsonb WHERE id=:id"),
            {"id": record.id},
        )

    assert replacement.created_at.tzinfo is not None
    assert db_session.execute(
        text(
            "SELECT pg_typeof(recipient_hash)::text, pg_typeof(expires_at)::text "
            "FROM family_invitations WHERE id=:id"
        ),
        {"id": replacement.id},
    ).one() == ("bytea", "timestamp with time zone")
    assert (
        db_session.execute(
            text(
                "SELECT pg_typeof(response_body)::text "
                "FROM command_idempotency_records WHERE id=:id"
            ),
            {"id": record.id},
        ).scalar_one()
        == "jsonb"
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            CommandIdempotencyRecord(
                actor_user_id=owner.id,
                operation="invalid-digest",
                idempotency_key=uuid.uuid4(),
                request_digest=b"short",
                state="processing",
            )
        )
        db_session.flush()


def test_postgres_concurrent_membership_insert_allows_one_winner(postgres_engine):
    suffix = uuid.uuid4().hex
    owner_id, member_id, family_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with postgres_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id,email,password_hash,is_active,principal_kind,auth_generation) "
                "VALUES (:owner,:owner_email,'hash',true,'account',1),"
                "(:member,:member_email,'hash',true,'account',1)"
            ),
            {
                "owner": owner_id,
                "owner_email": f"concurrent-owner-{suffix}@example.com",
                "member": member_id,
                "member_email": f"concurrent-member-{suffix}@example.com",
            },
        )
        connection.execute(
            text("INSERT INTO families (id,owner_id,name) VALUES (:id,:owner,'Concurrent')"),
            {"id": family_id, "owner": owner_id},
        )

    def insert_membership():
        try:
            with postgres_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO family_memberships "
                        "(id,family_id,user_id,role,state,generation,joined_at) "
                        "VALUES (:id,:family,:member,'collaborator','active',1,now())"
                    ),
                    {"id": uuid.uuid4(), "family": family_id, "member": member_id},
                )
            return "committed"
        except IntegrityError:
            return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: insert_membership(), range(2)))
        assert sorted(results) == ["committed", "conflict"]
        with postgres_engine.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM family_memberships "
                        "WHERE family_id=:family AND user_id=:member"
                    ),
                    {"family": family_id, "member": member_id},
                ).scalar_one()
                == 1
            )
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(delete(Family).where(Family.id == family_id))
            connection.execute(delete(User).where(User.id.in_([owner_id, member_id])))


@pytest.mark.parametrize("same_key", [False, True])
def test_postgres_concurrent_invitation_acceptance_is_atomic(postgres_engine, same_key):
    provider, fixture = _acceptance_fixture(postgres_engine)
    shared_key = uuid.uuid4()

    def accept(index):
        with Session(postgres_engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["recipient_id"])
            try:
                membership = collaboration_service.accept_invitation(
                    db,
                    actor=actor,
                    invitation_id=fixture["invitation_id"],
                    expected_version=fixture["version"],
                    invitation_token=fixture["token"],
                    verification_proof=fixture["proof"],
                    idempotency_key=shared_key if same_key else uuid.uuid4(),
                    provider=provider,
                )
                return "accepted", membership.id
            except AppException as error:
                return error.code, None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(accept, range(2)))
        if same_key:
            assert [result[0] for result in results] == ["accepted", "accepted"]
            assert results[0][1] == results[1][1]
        else:
            assert sorted(result[0] for result in results) == [
                "INVALID_INVITATION",
                "accepted",
            ]

        with Session(postgres_engine) as db:
            invitation = db.get(FamilyInvitation, fixture["invitation_id"])
            memberships = list(
                db.scalars(
                    select(FamilyMembership).where(
                        FamilyMembership.family_id == fixture["family_id"],
                        FamilyMembership.user_id == fixture["recipient_id"],
                    )
                ).all()
            )
            completed = list(
                db.scalars(
                    select(CommandIdempotencyRecord).where(
                        CommandIdempotencyRecord.actor_user_id == fixture["recipient_id"],
                        CommandIdempotencyRecord.operation == "family_invitation.accept",
                        CommandIdempotencyRecord.state == "completed",
                    )
                ).all()
            )
            assert invitation.state == "accepted"
            assert len(memberships) == 1 and memberships[0].state == "active"
            assert len(completed) == 1
            assert completed[0].resource_id == memberships[0].id
    finally:
        _cleanup_acceptance_fixture(postgres_engine, fixture)


def test_postgres_accept_vs_expire_has_one_terminal_result(postgres_engine):
    provider, fixture = _acceptance_fixture(postgres_engine)

    def accept():
        with Session(postgres_engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["recipient_id"])
            try:
                collaboration_service.accept_invitation(
                    db,
                    actor=actor,
                    invitation_id=fixture["invitation_id"],
                    expected_version=fixture["version"],
                    invitation_token=fixture["token"],
                    verification_proof=fixture["proof"],
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return "accepted"
            except AppException as error:
                return error.code

    def expire():
        with Session(postgres_engine) as db:
            invitation = db.scalar(
                select(FamilyInvitation)
                .where(FamilyInvitation.id == fixture["invitation_id"])
                .with_for_update()
            )
            if invitation.state == "approved":
                invitation.state = "expired"
                invitation.version += 1
                db.commit()
                return "expired"
            db.rollback()
            return invitation.state

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            accepted_future = executor.submit(accept)
            expired_future = executor.submit(expire)
            results = [accepted_future.result(), expired_future.result()]
        with Session(postgres_engine) as db:
            invitation = db.get(FamilyInvitation, fixture["invitation_id"])
            memberships = list(
                db.scalars(
                    select(FamilyMembership).where(
                        FamilyMembership.family_id == fixture["family_id"],
                        FamilyMembership.user_id == fixture["recipient_id"],
                    )
                ).all()
            )
            assert invitation.state in ("accepted", "expired")
            assert len(memberships) == (1 if invitation.state == "accepted" else 0)
            assert "accepted" in results or "expired" in results
    finally:
        _cleanup_acceptance_fixture(postgres_engine, fixture)


def test_postgres_rejoin_wins_over_stale_generation_mutation(postgres_engine):
    provider, fixture = _acceptance_fixture(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        membership = FamilyMembership(
            family_id=fixture["family_id"],
            user_id=fixture["recipient_id"],
            role="collaborator",
            state="revoked",
            generation=2,
            joined_at=datetime.now(UTC) - timedelta(days=1),
            ended_at=datetime.now(UTC),
        )
        db.add(membership)
        db.commit()
        membership_id = membership.id

    def rejoin():
        with Session(postgres_engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["recipient_id"])
            try:
                membership = collaboration_service.accept_invitation(
                    db,
                    actor=actor,
                    invitation_id=fixture["invitation_id"],
                    expected_version=fixture["version"],
                    invitation_token=fixture["token"],
                    verification_proof=fixture["proof"],
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return "rejoined", membership.generation
            except AppException as error:
                return error.code, None

    def stale_revoke():
        with Session(postgres_engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["owner_id"])
            try:
                membership = collaboration_service.end_membership(
                    db,
                    actor=actor,
                    family_id=fixture["family_id"],
                    membership_id=membership_id,
                    expected_generation=2,
                    idempotency_key=uuid.uuid4(),
                )
                return "revoked", membership.generation
            except AppException as error:
                return error.code, None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            rejoin_future = executor.submit(rejoin)
            stale_future = executor.submit(stale_revoke)
            results = [rejoin_future.result(), stale_future.result()]
        assert ("rejoined", 3) in results
        assert ("MEMBERSHIP_CONFLICT", None) in results
        with Session(postgres_engine) as db:
            membership = db.get(FamilyMembership, membership_id)
            assert membership.state == "active"
            assert membership.generation == 3
    finally:
        _cleanup_acceptance_fixture(postgres_engine, fixture)


def test_postgres_membership_revoke_linearizes_collaborator_authorization(
    c2a_migration_schema,
):
    config, engine = c2a_migration_schema
    command.upgrade(config, "head")
    provider, fixture = _collaboration_fixture(engine)
    concurrent_recipient = f"race-recipient-{uuid.uuid4().hex}@example.com"

    def collaborator_create():
        with Session(engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["collaborator_id"])
            try:
                invitation = collaboration_service.create_invitation(
                    db,
                    actor=actor,
                    family_id=fixture["family_id"],
                    data=InvitationCreate(recipient_kind="email", recipient=concurrent_recipient),
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return "created", invitation.id
            except AppException as error:
                return error.code, None

    def owner_revoke():
        with Session(engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["owner_id"])
            membership = collaboration_service.end_membership(
                db,
                actor=actor,
                family_id=fixture["family_id"],
                membership_id=fixture["membership_id"],
                expected_generation=1,
                idempotency_key=uuid.uuid4(),
            )
            return membership.state, membership.generation

    with ThreadPoolExecutor(max_workers=2) as executor:
        create_future = executor.submit(collaborator_create)
        revoke_future = executor.submit(owner_revoke)
        create_result = create_future.result()
        revoke_result = revoke_future.result()

    assert revoke_result == ("revoked", 2)
    assert create_result[0] in ("created", "NOT_FOUND")
    with Session(engine) as db:
        membership = db.get(FamilyMembership, fixture["membership_id"])
        invitations = list(
            db.scalars(
                select(FamilyInvitation).where(
                    FamilyInvitation.family_id == fixture["family_id"],
                    FamilyInvitation.requested_by_user_id == fixture["collaborator_id"],
                    FamilyInvitation.recipient_hash
                    == provider.lookup("email", concurrent_recipient),
                )
            ).all()
        )
        assert membership.state == "revoked"
        assert membership.generation == 2
        assert len(invitations) == (1 if create_result[0] == "created" else 0)

        collaborator = db.get(User, fixture["collaborator_id"])
        with pytest.raises(AppException) as denied:
            collaboration_service.create_invitation(
                db,
                actor=collaborator,
                family_id=fixture["family_id"],
                data=InvitationCreate(
                    recipient_kind="email",
                    recipient=f"post-revoke-{uuid.uuid4().hex}@example.com",
                ),
                idempotency_key=uuid.uuid4(),
                provider=provider,
            )
        assert denied.value.status_code == 404

        db.rollback()
        owner = db.get(User, fixture["owner_id"])
        owner_invitation = collaboration_service.create_invitation(
            db,
            actor=owner,
            family_id=fixture["family_id"],
            data=InvitationCreate(
                recipient_kind="email",
                recipient=f"owner-after-revoke-{uuid.uuid4().hex}@example.com",
            ),
            idempotency_key=uuid.uuid4(),
            provider=provider,
        )
        assert owner_invitation.state == "approved"


def test_postgres_approve_vs_cancel_and_approve_vs_revoke(c2a_migration_schema):
    config, engine = c2a_migration_schema
    command.upgrade(config, "head")
    provider, fixture = _collaboration_fixture(engine)

    def transition(invitation_id, action, expected_version):
        with Session(engine, expire_on_commit=False) as db:
            actor_id = (
                fixture["owner_id"]
                if action in ("approve", "revoke")
                else fixture["collaborator_id"]
            )
            actor = db.get(User, actor_id)
            try:
                if action == "approve":
                    result = collaboration_service.approve_invitation(
                        db,
                        actor=actor,
                        invitation_id=invitation_id,
                        expected_version=expected_version,
                        idempotency_key=uuid.uuid4(),
                        provider=provider,
                    )
                else:
                    result = collaboration_service.transition_invitation(
                        db,
                        actor=actor,
                        invitation_id=invitation_id,
                        expected_version=expected_version,
                        action=action,
                        idempotency_key=uuid.uuid4(),
                    )
                return "ok", result.state
            except AppException as error:
                return error.code, None

    invitation_id = _pending_invitation(engine, provider, fixture, "approve-cancel@example.com")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda arguments: transition(invitation_id, *arguments),
                [("approve", 1), ("cancel", 1)],
            )
        )
    assert sorted(result[0] for result in results) == ["INVITATION_CONFLICT", "ok"], results
    with Session(engine) as db:
        assert db.get(FamilyInvitation, invitation_id).state in ("approved", "cancelled")

    invitation_id = _pending_invitation(engine, provider, fixture, "approve-revoke@example.com")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda arguments: transition(invitation_id, *arguments),
                [("approve", 1), ("revoke", 2)],
            )
        )
    assert any(result[0] == "ok" for result in results)
    with Session(engine) as db:
        invitation = db.get(FamilyInvitation, invitation_id)
        assert invitation.state in ("approved", "revoked")
        assert invitation.version in (2, 3)


def test_postgres_duplicate_invitation_command_has_one_resource(c2a_migration_schema):
    config, engine = c2a_migration_schema
    command.upgrade(config, "head")
    provider, fixture = _collaboration_fixture(engine)
    data = InvitationCreate(recipient_kind="email", recipient="duplicate-command@example.com")

    def create_invitation():
        with Session(engine, expire_on_commit=False) as db:
            actor = db.get(User, fixture["owner_id"])
            try:
                invitation = collaboration_service.create_invitation(
                    db,
                    actor=actor,
                    family_id=fixture["family_id"],
                    data=data,
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return "ok", invitation.id
            except AppException as error:
                return error.code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_invitation(), range(2)))
    assert sorted(result[0] for result in results) == ["INVITATION_CONFLICT", "ok"]
    with Session(engine) as db:
        invitations = list(
            db.scalars(
                select(FamilyInvitation).where(
                    FamilyInvitation.family_id == fixture["family_id"],
                    FamilyInvitation.recipient_hash
                    == provider.lookup("email", "duplicate-command@example.com"),
                    FamilyInvitation.state.in_(["pending_owner", "approved"]),
                )
            ).all()
        )
        assert len(invitations) == 1


def test_c2a_downgrade_refuses_collaboration_evidence(c2a_migration_schema):
    config, engine = c2a_migration_schema
    command.upgrade(config, "head")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO command_idempotency_records "
                "(id,operation,idempotency_key,request_digest,state) "
                "VALUES (:id,'evidence',:key,:digest,'processing')"
            ),
            {"id": uuid.uuid4(), "key": uuid.uuid4(), "digest": b"x" * 32},
        )
    with pytest.raises(RuntimeError, match="C2A downgrade refused"):
        command.downgrade(config, "c1a7d45e92b0")
    with engine.connect() as connection:
        assert connection.scalar(select(CommandIdempotencyRecord.id)) is not None
