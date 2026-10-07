import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import create_verification_proof
from app.dependencies.participant_actor import ParticipantActor
from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.interview import Interview
from app.models.interview_participant import InterviewParticipant
from app.models.user import User
from app.services import interview_participant as participant_service
from test_support.database import resolve_test_database_url
from tests.c1_support import TestOnlyRightsProvider

pytestmark = pytest.mark.integration


@pytest.fixture()
def c2b_schema(monkeypatch):
    url = make_url(resolve_test_database_url())
    schema = "c2b_test_" + uuid.uuid4().hex
    admin_engine = create_engine(url, hide_parameters=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = url.set(query={**url.query, "options": f"-csearch_path={schema}"})
    monkeypatch.setenv("TEST_DATABASE_URL", isolated.render_as_string(hide_password=False))
    monkeypatch.setenv("TEST_MIGRATION_MODE", "1")
    engine = create_engine(isolated, hide_parameters=True)
    config = Config("alembic.ini")
    try:
        yield config, engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def test_c2b_fresh_upgrade_constraints_and_empty_downgrade(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    command.check(config)
    inspector = inspect(engine)
    assert "interview_participants" in inspector.get_table_names()
    unique_constraints = {
        (item["name"], tuple(item["column_names"]))
        for item in inspector.get_unique_constraints("interview_participants")
    }
    assert (
        "uq_interview_participants_id_scope",
        ("id", "interview_scope_id"),
    ) in unique_constraints
    foreign_keys = inspector.get_foreign_keys("interview_participants")
    actions = {
        tuple(item["constrained_columns"]): item["options"].get("ondelete") for item in foreign_keys
    }
    assert actions[("interview_id",)] == "SET NULL"
    assert actions[("family_member_id",)] == "SET NULL"
    assert actions[("user_id",)] == "RESTRICT"
    assert actions[("verified_contact_id", "user_id")] == "RESTRICT"
    command.downgrade(config, "b7e2c4d891a0")
    assert "interview_participants" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    command.check(config)


def test_postgres_parent_set_null_and_manual_family_member_changes(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as db:
        owner = User(
            principal_kind="account",
            email=f"fk-owner-{uuid.uuid4().hex}@example.com",
            password_hash="hash",
        )
        db.add(owner)
        db.flush()
        family = Family(owner_id=owner.id, name="C2B FK family")
        db.add(family)
        db.flush()
        member = FamilyMember(family_id=family.id, name="Primary")
        other_member = FamilyMember(family_id=family.id, name="Other")
        db.add_all([member, other_member])
        db.flush()
        interview = Interview(family_member_id=member.id, title="FK", type="life_story")
        db.add(interview)
        db.flush()
        now = datetime.now(UTC)
        provider = TestOnlyRightsProvider()
        contact = UserContact(
            user_id=owner.id,
            kind="email",
            value_ciphertext=provider.encrypt(owner.email.encode()),
            lookup_hash=provider.lookup("email", owner.email),
            state="verified",
            verified_at=now,
        )
        db.add(contact)
        db.flush()
        challenge = AuthChallenge(
            user_id=owner.id,
            context_kind="participant_confirmation",
            context_id=uuid.uuid4(),
            channel_ciphertext=provider.encrypt(b"context"),
            channel_hash=contact.lookup_hash,
            code_digest=b"x" * 32,
            state="consumed",
            expires_at=now + timedelta(minutes=5),
            consumed_at=now,
            attempt_count=0,
        )
        db.add(challenge)
        db.flush()
        participant = InterviewParticipant(
            interview_id=interview.id,
            interview_scope_id=interview.id,
            user_id=owner.id,
            family_member_id=member.id,
            roles="speaker",
            state="verified",
            eligibility_state="eligible",
            verified_contact_id=contact.id,
            verification_ref=challenge.id,
            verified_at=now,
            adult_declaration_at=now,
            version=2,
        )
        unlinked = InterviewParticipant(
            interview_id=interview.id,
            interview_scope_id=interview.id,
            roles="speaker",
            state="proposed",
            eligibility_state="unknown",
            version=1,
        )
        db.add_all([participant, unlinked])
        db.commit()
        participant_id = participant.id
        interview_id = interview.id
        scope_id = interview.id
        member_id = member.id
        other_member_id = other_member.id
        unlinked_id = unlinked.id
        evidence = (
            participant.user_id,
            participant.verified_contact_id,
            participant.verification_ref,
            participant.verified_at,
            participant.adult_declaration_at,
            participant.version,
        )

        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("UPDATE interview_participants SET family_member_id=NULL WHERE id=:id"),
                {"id": participant_id},
            )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("UPDATE interview_participants SET family_member_id=:other WHERE id=:id"),
                {"id": participant_id, "other": other_member_id},
            )
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("UPDATE interview_participants SET family_member_id=:member WHERE id=:id"),
                {"id": unlinked_id, "member": member_id},
            )

        db.execute(text("DELETE FROM interviews WHERE id=:id"), {"id": interview_id})
        db.commit()
        db.expire_all()
        stored = db.get(InterviewParticipant, participant_id)
        assert stored is not None
        assert stored.interview_id is None
        assert stored.interview_scope_id == scope_id
        assert stored.family_member_id == member_id

        db.execute(text("DELETE FROM family_members WHERE id=:id"), {"id": member_id})
        db.commit()
        db.expire_all()
        stored = db.get(InterviewParticipant, participant_id)
        assert stored is not None
        assert stored.family_member_id is None
        assert stored.interview_scope_id == scope_id
        assert (
            stored.user_id,
            stored.verified_contact_id,
            stored.verification_ref,
            stored.verified_at,
            stored.adult_declaration_at,
            stored.version,
        ) == evidence


def test_postgres_verified_participant_identity_graph_blocks_user_delete(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            principal_kind="account",
            email=f"restrict-{uuid.uuid4().hex}@example.com",
            password_hash="hash",
        )
        db.add(user)
        db.flush()
        now = datetime.now(UTC)
        provider = TestOnlyRightsProvider()
        contact = UserContact(
            user_id=user.id,
            kind="email",
            value_ciphertext=provider.encrypt(user.email.encode()),
            lookup_hash=provider.lookup("email", user.email),
            state="verified",
            verified_at=now,
        )
        db.add(contact)
        db.flush()
        verification_ref = uuid.uuid4()
        participant = InterviewParticipant(
            interview_scope_id=uuid.uuid4(),
            user_id=user.id,
            roles="speaker",
            state="verified",
            eligibility_state="eligible",
            verified_contact_id=contact.id,
            verification_ref=verification_ref,
            verified_at=now,
            adult_declaration_at=now,
            version=2,
        )
        db.add(participant)
        db.commit()
        user_id = user.id
        contact_id = contact.id
        participant_id = participant.id
        evidence = (
            participant.user_id,
            participant.verified_contact_id,
            participant.verification_ref,
            participant.verified_at,
            participant.adult_declaration_at,
        )
        version = participant.version

    with Session(engine) as delete_db:
        with pytest.raises(IntegrityError) as error:
            delete_db.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
            delete_db.commit()
        assert error.value.orig.sqlstate == "23503"
        delete_db.rollback()

    with Session(engine) as read_db:
        assert read_db.get(User, user_id) is not None
        assert read_db.get(UserContact, contact_id) is not None
        stored = read_db.get(InterviewParticipant, participant_id)
        assert stored is not None
        assert stored.state == "verified"
        assert stored.eligibility_state == "eligible"
        assert stored.version == version
        assert (
            stored.user_id,
            stored.verified_contact_id,
            stored.verification_ref,
            stored.verified_at,
            stored.adult_declaration_at,
        ) == evidence


def test_postgres_participant_user_fk_directly_restricts_delete(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    participant_user_fk = next(
        item
        for item in inspect(engine).get_foreign_keys("interview_participants")
        if item["constrained_columns"] == ["user_id"] and item["referred_table"] == "users"
    )
    assert participant_user_fk["options"].get("ondelete") == "RESTRICT"
    constraint_name = participant_user_fk["name"]

    with Session(engine, expire_on_commit=False) as db:
        user = User(
            principal_kind="account",
            email=f"participant-restrict-{uuid.uuid4().hex}@example.com",
            password_hash="hash",
        )
        db.add(user)
        db.flush()
        participant = InterviewParticipant(
            interview_scope_id=uuid.uuid4(),
            user_id=user.id,
            roles="speaker",
            state="disputed",
            eligibility_state="unknown",
            version=1,
        )
        db.add(participant)
        db.commit()
        user_id = user.id
        participant_id = participant.id

    with Session(engine) as delete_db:
        with pytest.raises(IntegrityError) as error:
            delete_db.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
            delete_db.commit()
        assert error.value.orig.sqlstate == "23503"
        assert error.value.orig.diag.constraint_name == constraint_name
        delete_db.rollback()

    with Session(engine) as read_db:
        assert read_db.get(User, user_id) is not None
        stored = read_db.get(InterviewParticipant, participant_id)
        assert stored is not None
        assert stored.user_id == user_id
        assert stored.state == "disputed"
        assert stored.eligibility_state == "unknown"
        assert stored.version == 1


def test_postgres_interview_scope_id_is_database_immutable(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            principal_kind="account",
            email=f"scope-{uuid.uuid4().hex}@example.com",
            password_hash="hash",
        )
        db.add(user)
        db.flush()
        now = datetime.now(UTC)
        provider = TestOnlyRightsProvider()
        contact = UserContact(
            user_id=user.id,
            kind="email",
            value_ciphertext=provider.encrypt(user.email.encode()),
            lookup_hash=provider.lookup("email", user.email),
            state="verified",
            verified_at=now,
        )
        db.add(contact)
        db.flush()
        participant = InterviewParticipant(
            interview_scope_id=uuid.uuid4(),
            user_id=user.id,
            roles="speaker",
            state="verified",
            eligibility_state="eligible",
            verified_contact_id=contact.id,
            verification_ref=uuid.uuid4(),
            verified_at=now,
            adult_declaration_at=now,
            version=3,
        )
        db.add(participant)
        db.commit()
        participant_id = participant.id
        original_scope_id = participant.interview_scope_id
        replacement_scope_id = uuid.uuid4()
        assert replacement_scope_id != original_scope_id
        preserved = (
            participant.state,
            participant.version,
            participant.family_member_id,
            participant.user_id,
            participant.verified_contact_id,
            participant.verification_ref,
            participant.verified_at,
            participant.adult_declaration_at,
        )

        with pytest.raises(DBAPIError) as error, db.begin_nested():
            db.execute(
                text(
                    "UPDATE interview_participants "
                    "SET interview_scope_id=:scope WHERE id=:participant_id"
                ),
                {"scope": replacement_scope_id, "participant_id": participant_id},
            )
        assert error.value.orig.diag.message_primary == "Participant identity evidence is immutable"
        db.expire_all()
        stored = db.get(InterviewParticipant, participant_id)
        assert stored is not None
        assert stored.interview_scope_id == original_scope_id
        assert (
            stored.state,
            stored.version,
            stored.family_member_id,
            stored.user_id,
            stored.verified_contact_id,
            stored.verification_ref,
            stored.verified_at,
            stored.adult_declaration_at,
        ) == preserved


def _participant_row(
    *,
    scope_id=None,
    user_id=None,
    contact_id=None,
    state="proposed",
    eligibility="unknown",
    version=1,
    verification_ref=None,
    verified_at=None,
    adult_at=None,
):
    return InterviewParticipant(
        interview_scope_id=scope_id or uuid.uuid4(),
        user_id=user_id,
        roles="speaker",
        state=state,
        eligibility_state=eligibility,
        verified_contact_id=contact_id,
        verification_ref=verification_ref,
        verified_at=verified_at,
        adult_declaration_at=adult_at,
        version=version,
    )


def test_postgres_partial_unique_version_state_and_verified_invariants(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    now = datetime.now(UTC)
    with Session(engine) as db:
        user = User(
            principal_kind="account",
            email=f"checks-{uuid.uuid4().hex}@example.com",
            password_hash="hash",
        )
        db.add(user)
        db.flush()
        provider = TestOnlyRightsProvider()
        contact = UserContact(
            user_id=user.id,
            kind="email",
            value_ciphertext=provider.encrypt(user.email.encode()),
            lookup_hash=provider.lookup("email", user.email),
            state="verified",
            verified_at=now,
        )
        db.add(contact)
        db.flush()

        shared_scope = uuid.uuid4()
        db.add_all(
            [
                _participant_row(scope_id=shared_scope),
                _participant_row(scope_id=shared_scope),
            ]
        )
        db.flush()
        complete = {
            "user_id": user.id,
            "contact_id": contact.id,
            "state": "verified",
            "eligibility": "eligible",
            "verification_ref": uuid.uuid4(),
            "verified_at": now,
            "adult_at": now,
        }
        db.add(_participant_row(scope_id=shared_scope, **complete))
        db.flush()
        for duplicate_state, duplicate_eligibility in (
            ("verified", "eligible"),
            ("inactive", "eligible"),
            ("disputed", "unknown"),
        ):
            values = {
                "scope_id": shared_scope,
                "user_id": user.id,
                "state": duplicate_state,
                "eligibility": duplicate_eligibility,
            }
            if duplicate_state == "verified":
                values.update(
                    contact_id=contact.id,
                    verification_ref=uuid.uuid4(),
                    verified_at=now,
                    adult_at=now,
                )
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(_participant_row(**values))
                db.flush()

        for invalid_version in (0, -1):
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(_participant_row(version=invalid_version))
                db.flush()
        db.add(_participant_row(version=1))
        db.flush()

        legal = (
            ("proposed", "unknown"),
            ("inactive", "eligible"),
            ("inactive", "ineligible"),
            ("disputed", "unknown"),
            ("disputed", "eligible"),
            ("disputed", "ineligible"),
        )
        for state, eligibility in legal:
            db.add(_participant_row(state=state, eligibility=eligibility))
        db.add(_participant_row(**complete))
        db.flush()

        legal_set = set(legal) | {("verified", "eligible")}
        all_combinations = {
            (state, eligibility)
            for state in ("proposed", "verified", "inactive", "disputed")
            for eligibility in ("unknown", "eligible", "ineligible")
        }
        for state, eligibility in sorted(all_combinations - legal_set):
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(_participant_row(state=state, eligibility=eligibility))
                db.flush()

        verified_fields = {
            "user_id": user.id,
            "contact_id": contact.id,
            "verification_ref": uuid.uuid4(),
            "verified_at": now,
            "adult_at": now,
        }
        for missing in verified_fields:
            values = {**verified_fields, missing: None}
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(
                    _participant_row(
                        state="verified",
                        eligibility="eligible",
                        **values,
                    )
                )
                db.flush()
        accepted = _participant_row(
            state="verified",
            eligibility="eligible",
            **verified_fields,
        )
        db.add(accepted)
        db.commit()
        assert db.get(InterviewParticipant, accepted.id) is not None


def _identity_fixture(engine):
    provider = TestOnlyRightsProvider()
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as db:
        suffix = uuid.uuid4().hex
        owner = User(
            principal_kind="account", email=f"owner-{suffix}@example.com", password_hash="hash"
        )
        first = User(
            principal_kind="account", email=f"first-{suffix}@example.com", password_hash="hash"
        )
        second = User(
            principal_kind="account", email=f"second-{suffix}@example.com", password_hash="hash"
        )
        db.add_all([owner, first, second])
        db.flush()
        family = Family(owner_id=owner.id, name="C2B race")
        db.add(family)
        db.flush()
        member = FamilyMember(family_id=family.id, name="Subject")
        db.add(member)
        db.flush()
        interview = Interview(family_member_id=member.id, title="Race", type="life_story")
        db.add(interview)
        db.flush()
        participant = InterviewParticipant(
            interview_id=interview.id,
            interview_scope_id=interview.id,
            roles="speaker",
            state="proposed",
            eligibility_state="unknown",
            version=1,
        )
        db.add(participant)
        db.flush()
        proofs = {}
        for user in (first, second):
            channel_hash = provider.lookup("email", user.email)
            contact = UserContact(
                user_id=user.id,
                kind="email",
                value_ciphertext=provider.encrypt(user.email.encode()),
                lookup_hash=channel_hash,
                state="verified",
                verified_at=now,
            )
            db.add(contact)
            db.flush()
            challenge = AuthChallenge(
                user_id=user.id,
                context_kind="participant_confirmation",
                context_id=participant.id,
                channel_ciphertext=provider.encrypt(b"context"),
                channel_hash=channel_hash,
                code_digest=b"x" * 32,
                state="consumed",
                expires_at=now + timedelta(minutes=5),
                consumed_at=now,
                attempt_count=0,
            )
            db.add(challenge)
            db.flush()
            proofs[user.id] = create_verification_proof(
                subject=str(user.id),
                principal_kind="account",
                auth_generation=user.auth_generation,
                context_kind="participant_confirmation",
                context_id=str(participant.id),
                challenge_id=str(challenge.id),
                contact_id=str(contact.id),
                expires_at=now + timedelta(minutes=3),
            )
        result = participant.id, first.id, second.id, proofs
        db.commit()
    return provider, result


def test_postgres_claim_race_has_one_winner(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    provider, (participant_id, first_id, second_id, proofs) = _identity_fixture(engine)

    def confirm(user_id):
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            try:
                result = participant_service.confirm(
                    db,
                    actor=ParticipantActor(user, "account", None),
                    participant_id=participant_id,
                    proof=proofs[user_id],
                    adult_autonomous_decision=True,
                    expected_version=1,
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return "confirmed", result.user_id
            except AppException as error:
                return error.code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, (first_id, second_id)))
    assert sorted(item[0] for item in results) == ["PARTICIPANT_CONFLICT", "confirmed"]
    with Session(engine) as db:
        participant = db.get(InterviewParticipant, participant_id)
        assert participant.state == "verified"
        assert participant.version == 2
        assert participant.user_id in (first_id, second_id)


@pytest.mark.parametrize("same_key", [False, True])
def test_postgres_double_confirm_is_atomic(c2b_schema, same_key):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    provider, (participant_id, user_id, _, proofs) = _identity_fixture(engine)
    shared_key = uuid.uuid4()

    def confirm():
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            try:
                result = participant_service.confirm(
                    db,
                    actor=ParticipantActor(user, "account", None),
                    participant_id=participant_id,
                    proof=proofs[user_id],
                    adult_autonomous_decision=True,
                    expected_version=1,
                    idempotency_key=shared_key if same_key else uuid.uuid4(),
                    provider=provider,
                )
                return "confirmed", result.version
            except AppException as error:
                return error.code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: confirm(), range(2)))
    if same_key:
        assert results == [("confirmed", 2), ("confirmed", 2)]
    else:
        assert sorted(item[0] for item in results) == ["PARTICIPANT_CONFLICT", "confirmed"]
    with Session(engine) as db:
        participant = db.get(InterviewParticipant, participant_id)
        assert participant.state == "verified"
        assert participant.version == 2
        assert participant.user_id == user_id


def test_postgres_confirm_vs_inactive_preserves_legal_state(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    provider, (participant_id, user_id, _, proofs) = _identity_fixture(engine)

    def confirm():
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            try:
                result = participant_service.confirm(
                    db,
                    actor=ParticipantActor(user, "account", None),
                    participant_id=participant_id,
                    proof=proofs[user_id],
                    adult_autonomous_decision=True,
                    expected_version=1,
                    idempotency_key=uuid.uuid4(),
                    provider=provider,
                )
                return result.state
            except AppException as error:
                return error.code

    def inactivate():
        with Session(engine, expire_on_commit=False) as db:
            user = db.get(User, user_id)
            try:
                result = participant_service.inactivate(
                    db,
                    actor=ParticipantActor(user, "account", None),
                    participant_id=participant_id,
                    expected_version=2,
                    idempotency_key=uuid.uuid4(),
                )
                return result.state
            except AppException as error:
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        confirm_future = executor.submit(confirm)
        inactive_future = executor.submit(inactivate)
        results = [confirm_future.result(), inactive_future.result()]
    with Session(engine) as db:
        participant = db.get(InterviewParticipant, participant_id)
        assert participant.state in ("verified", "inactive")
        assert participant.eligibility_state == "eligible"
        assert participant.user_id == user_id
        assert participant.version in (2, 3)
        assert "verified" in results


def test_postgres_participant_checks_composite_fk_and_downgrade_guard(c2b_schema):
    config, engine = c2b_schema
    command.upgrade(config, "head")
    provider, (participant_id, first_id, _, proofs) = _identity_fixture(engine)
    with Session(engine) as db:
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("UPDATE interview_participants SET roles='operator' WHERE id=:id"),
                {"id": participant_id},
            )
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(
                text(
                    "UPDATE interview_participants SET state='verified', "
                    "eligibility_state='eligible' WHERE id=:id"
                ),
                {"id": participant_id},
            )

        user = db.get(User, first_id)
        proof = proofs[first_id]
        confirmed = participant_service.confirm(
            db,
            actor=ParticipantActor(user, "account", None),
            participant_id=participant_id,
            proof=proof,
            adult_autonomous_decision=True,
            expected_version=1,
            idempotency_key=uuid.uuid4(),
            provider=provider,
        )
        assert confirmed.state == "verified"
        other_contact = db.query(UserContact).filter(UserContact.user_id != first_id).first()
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(
                text("UPDATE interview_participants SET verified_contact_id=:contact WHERE id=:id"),
                {"contact": other_contact.id, "id": participant_id},
            )
    with pytest.raises(RuntimeError, match="C2B downgrade refused"):
        command.downgrade(config, "b7e2c4d891a0")
