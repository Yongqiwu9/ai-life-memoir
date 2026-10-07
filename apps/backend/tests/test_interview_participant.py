import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.rights_auth_provider import get_rights_auth_provider
from app.core.security import decode_verification_proof
from app.main import app
from app.models.collaboration import CommandIdempotencyRecord, FamilyInvitation, FamilyMembership
from app.models.identity_foundation import UserContact
from app.models.interview_participant import InterviewParticipant
from app.models.user import User
from app.services import command_idempotency as idempotency_service
from app.services import privacy_policy as policy_service
from tests.c1_support import TestOnlyRightsProvider, policy_documents


@pytest.fixture()
def participant_provider(client):
    provider = TestOnlyRightsProvider()
    app.dependency_overrides[get_rights_auth_provider] = lambda: provider
    return provider


@pytest.fixture()
def active_participant_policy(db_session):
    parameters, notices, capabilities = policy_documents()
    policy = policy_service.create_draft(
        db_session,
        version="participant-test-v1",
        parameters=parameters,
        notices=notices,
        capabilities=capabilities,
    )
    policy_service.publish_policy(db_session, policy.id)
    db_session.commit()
    return policy


def _with_key(headers, key=None):
    return {**headers, "Idempotency-Key": str(key or uuid.uuid4())}


def _account(client, email):
    password = "strong-password-1"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        ).status_code
        == 201
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _interview(client, owner_headers):
    family = client.post(
        "/api/v1/families", json={"name": "C2B family"}, headers=owner_headers
    ).json()
    member = client.post(
        f"/api/v1/families/{family['id']}/members",
        json={"name": "Primary subject"},
        headers=owner_headers,
    ).json()
    interview = client.post(
        f"/api/v1/family-members/{member['id']}/interviews",
        json={"title": "Identity interview", "type": "life_story"},
        headers=owner_headers,
    ).json()
    return family, member, interview


def _proposal(client, owner_headers, interview_id, family_member_id=None):
    response = client.post(
        f"/api/v1/interviews/{interview_id}/participants",
        json={"roles": "speaker", "family_member_id": family_member_id},
        headers=_with_key(owner_headers),
    )
    assert response.status_code == 201
    return response.json()


def _participant_proof(client, provider, actor_headers, participant_id, contact=None):
    payload = {"context_kind": "participant_confirmation", "context_id": participant_id}
    if contact:
        payload.update({"contact_kind": contact[0], "contact": contact[1]})
    challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json=payload,
        headers=_with_key(actor_headers),
    )
    assert challenge.status_code == 202, challenge.text
    challenge_id = uuid.UUID(challenge.json()["id"])
    verified = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": provider.deliveries[challenge_id]},
        headers=_with_key(actor_headers),
    )
    assert verified.status_code == 200, verified.text
    return verified.json()["verification_proof"]


def _invitation(client, provider, owner, family_id, recipient_email):
    response = client.post(
        f"/api/v1/families/{family_id}/invitations",
        json={"recipient_kind": "email", "recipient": recipient_email},
        headers=_with_key(owner),
    )
    assert response.status_code == 201, response.text
    invitation = response.json()
    return invitation, provider.deliveries[uuid.UUID(invitation["id"])]


def _invitation_proof(client, provider, recipient, invitation, token):
    challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient),
    )
    assert challenge.status_code == 202, challenge.text
    challenge_id = uuid.UUID(challenge.json()["id"])
    verified = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": provider.deliveries[challenge_id]},
        headers=_with_key(recipient),
    )
    assert verified.status_code == 200, verified.text
    return verified.json()["verification_proof"]


def test_account_claim_confirm_read_and_self_inactivate_are_idempotent(
    client, db_session, participant_provider
):
    owner = _account(client, "c2b-owner@example.com")
    speaker = _account(client, "c2b-speaker@example.com")
    _, member, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"], member["id"])
    assert participant["state"] == "proposed"
    assert "interview_id" not in participant and "user_id" not in participant

    proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", "c2b-speaker@example.com"),
    )
    key = uuid.uuid4()
    payload = {
        "verification_proof": proof,
        "adult_autonomous_decision": True,
        "expected_version": 1,
    }
    confirmed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json=payload,
        headers=_with_key(speaker, key),
    )
    replayed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json=payload,
        headers=_with_key(speaker, key),
    )
    assert confirmed.status_code == replayed.status_code == 200
    assert confirmed.json() == replayed.json()
    assert confirmed.json()["state"] == "verified"
    assert confirmed.json()["eligibility_state"] == "eligible"

    own = client.get(f"/api/v1/rights/participants/{participant['id']}", headers=speaker)
    assert own.status_code == 200
    assert set(own.json()) == {
        "id",
        "roles",
        "state",
        "eligibility_state",
        "verified_at",
        "adult_declaration_at",
        "version",
        "created_at",
        "updated_at",
    }
    inactive = client.post(
        f"/api/v1/participants/{participant['id']}/inactive",
        json={"expected_version": 2},
        headers=_with_key(speaker),
    )
    assert inactive.status_code == 200 and inactive.json()["state"] == "inactive"
    stored = db_session.get(InterviewParticipant, uuid.UUID(participant["id"]))
    assert stored.interview_scope_id == uuid.UUID(interview["id"])


def test_rights_only_can_confirm_inactivate_and_is_denied_every_archive_layer(
    client, participant_provider
):
    owner = _account(client, "c2b-rights-owner@example.com")
    family, _, interview = _interview(client, owner)
    session = client.post(
        f"/api/v1/interviews/{interview['id']}/sessions", json={}, headers=owner
    ).json()
    audio = client.post(f"/api/v1/sessions/{session['id']}/audios", json={}, headers=owner).json()
    transcript = client.post(
        f"/api/v1/audios/{audio['id']}/transcripts", json={}, headers=owner
    ).json()
    segment = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "rights isolation"},
        headers=owner,
    ).json()
    client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "rights isolation"},
        headers=owner,
    ).raise_for_status()
    participant = _proposal(client, owner, interview["id"])

    challenge = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "phone", "channel": "+8613800001234"}
    )
    challenge_id = uuid.UUID(challenge.json()["id"])
    token = client.post(
        f"/api/v1/rights-auth/challenges/{challenge_id}/verify",
        json={"code": participant_provider.deliveries[challenge_id]},
    ).json()["access_token"]
    rights = {"Authorization": f"Bearer {token}"}
    proof = _participant_proof(client, participant_provider, rights, participant["id"])
    confirmed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(rights),
    )
    assert confirmed.status_code == 200
    assert (
        client.get(f"/api/v1/rights/participants/{participant['id']}", headers=rights).status_code
        == 200
    )
    denied = (
        ("users/me", client.get("/api/v1/users/me", headers=rights)),
        ("family", client.get(f"/api/v1/families/{family['id']}", headers=rights)),
        ("interview", client.get(f"/api/v1/interviews/{interview['id']}", headers=rights)),
        ("session", client.get(f"/api/v1/sessions/{session['id']}", headers=rights)),
        ("audio", client.get(f"/api/v1/audios/{audio['id']}", headers=rights)),
        (
            "transcript",
            client.get(f"/api/v1/transcripts/{transcript['id']}", headers=rights),
        ),
        ("segment", client.get(f"/api/v1/segments/{segment['id']}", headers=rights)),
        (
            "message",
            client.get(f"/api/v1/sessions/{session['id']}/messages", headers=rights),
        ),
    )
    assert {name: response.status_code for name, response in denied} == {
        "users/me": 401,
        "family": 401,
        "interview": 401,
        "session": 401,
        "audio": 401,
        "transcript": 401,
        "segment": 401,
        "message": 401,
    }
    inactive_key = uuid.uuid4()
    inactive_payload = {"expected_version": 2}
    first = client.post(
        f"/api/v1/participants/{participant['id']}/inactive",
        json=inactive_payload,
        headers=_with_key(rights, inactive_key),
    )
    replay = client.post(
        f"/api/v1/participants/{participant['id']}/inactive",
        json=inactive_payload,
        headers=_with_key(rights, inactive_key),
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["state"] == "inactive"
    assert first.json()["version"] == 3


def test_cross_user_and_owner_cannot_confirm_or_inactivate_speaker(client, participant_provider):
    owner = _account(client, "c2b-isolation-owner@example.com")
    speaker = _account(client, "c2b-isolation-speaker@example.com")
    attacker = _account(client, "c2b-isolation-attacker@example.com")
    _, _, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"])
    proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", "c2b-isolation-speaker@example.com"),
    )
    for headers in (owner, attacker):
        denied = client.post(
            f"/api/v1/participants/{participant['id']}/confirm",
            json={
                "verification_proof": proof,
                "adult_autonomous_decision": True,
                "expected_version": 1,
            },
            headers=_with_key(headers),
        )
        assert denied.status_code == 401
    confirmed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(speaker),
    )
    assert confirmed.status_code == 200
    assert (
        client.get(f"/api/v1/rights/participants/{participant['id']}", headers=attacker).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/participants/{participant['id']}/inactive",
            json={"expected_version": 2},
            headers=_with_key(owner),
        ).status_code
        == 404
    )


def test_adult_declaration_and_client_controlled_identity_fields_fail_closed(
    client, participant_provider
):
    owner = _account(client, "c2b-input-owner@example.com")
    _, _, interview = _interview(client, owner)
    rejected = client.post(
        f"/api/v1/interviews/{interview['id']}/participants",
        json={"roles": "speaker", "state": "verified", "user_id": str(uuid.uuid4())},
        headers=_with_key(owner),
    )
    assert rejected.status_code == 422
    raw_proof = "raw-proof-must-not-leak"
    invalid_adult = client.post(
        f"/api/v1/participants/{uuid.uuid4()}/confirm",
        json={
            "verification_proof": raw_proof,
            "adult_autonomous_decision": False,
            "expected_version": 1,
        },
        headers=_with_key(owner),
    )
    assert invalid_adult.status_code == 422
    assert raw_proof not in invalid_adult.text


def test_active_collaborator_can_propose_but_revoked_and_subject_mismatch_are_denied(
    client, db_session
):
    owner = _account(client, "c2b-collab-owner@example.com")
    collaborator = _account(client, "c2b-collaborator@example.com")
    family, _, interview = _interview(client, owner)
    collaborator_user = db_session.scalar(
        select(User).where(User.email == "c2b-collaborator@example.com")
    )
    membership = FamilyMembership(
        family_id=uuid.UUID(family["id"]),
        user_id=collaborator_user.id,
        role="collaborator",
        state="active",
        generation=1,
        joined_at=datetime.now(UTC),
    )
    db_session.add(membership)
    db_session.commit()
    assert _proposal(client, collaborator, interview["id"])["state"] == "proposed"

    other_member = client.post(
        f"/api/v1/families/{family['id']}/members",
        json={"name": "Other subject"},
        headers=owner,
    ).json()
    mismatch = client.post(
        f"/api/v1/interviews/{interview['id']}/participants",
        json={"roles": "speaker", "family_member_id": other_member["id"]},
        headers=_with_key(owner),
    )
    assert mismatch.status_code == 409

    membership.state = "revoked"
    membership.generation += 1
    membership.ended_at = datetime.now(UTC)
    db_session.commit()
    denied = client.post(
        f"/api/v1/interviews/{interview['id']}/participants",
        json={"roles": "speaker"},
        headers=_with_key(collaborator),
    )
    assert denied.status_code == 404


def test_participant_and_invitation_proofs_are_bidirectionally_isolated(
    client, db_session, participant_provider, active_participant_policy
):
    owner = _account(client, "c2b-context-owner@example.com")
    recipient_email = "c2b-context-recipient@example.com"
    recipient = _account(client, recipient_email)
    family, _, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"])
    invitation, token = _invitation(
        client, participant_provider, owner, family["id"], recipient_email
    )
    invitation_proof = _invitation_proof(client, participant_provider, recipient, invitation, token)
    rejected_participant = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": invitation_proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(recipient),
    )
    assert rejected_participant.status_code == 401
    stored_participant = db_session.get(InterviewParticipant, uuid.UUID(participant["id"]))
    assert (stored_participant.state, stored_participant.version, stored_participant.user_id) == (
        "proposed",
        1,
        None,
    )

    participant_proof = _participant_proof(
        client,
        participant_provider,
        recipient,
        participant["id"],
        ("email", recipient_email),
    )
    rejected_invitation = client.post(
        f"/api/v1/invitations/{invitation['id']}/accept",
        json={
            "expected_version": invitation["version"],
            "invitation_token": token,
            "verification_proof": participant_proof,
        },
        headers=_with_key(recipient),
    )
    assert rejected_invitation.status_code == 401
    stored_invitation = db_session.get(FamilyInvitation, uuid.UUID(invitation["id"]))
    assert stored_invitation.state == invitation["state"]
    assert stored_invitation.version == invitation["version"]


@pytest.mark.parametrize("stale_kind", ["contact", "auth_generation"])
def test_participant_confirmation_rejects_stale_security_state(
    client, db_session, participant_provider, stale_kind
):
    owner = _account(client, f"c2b-stale-owner-{stale_kind}@example.com")
    speaker_email = f"c2b-stale-speaker-{stale_kind}@example.com"
    speaker = _account(client, speaker_email)
    _, _, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"])
    proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", speaker_email),
    )
    claims = decode_verification_proof(proof)
    if stale_kind == "contact":
        contact = db_session.get(UserContact, uuid.UUID(claims["contact_id"]))
        contact.state = "revoked"
        contact.revoked_at = datetime.now(UTC)
    else:
        user = db_session.get(User, uuid.UUID(claims["sub"]))
        user.auth_generation += 1
    db_session.commit()
    rejected = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(speaker),
    )
    assert rejected.status_code == 401
    db_session.expire_all()
    stored = db_session.get(InterviewParticipant, uuid.UUID(participant["id"]))
    assert (stored.state, stored.version, stored.user_id) == ("proposed", 1, None)


def test_participant_confirm_idempotency_fingerprints_proof_and_rejects_changed_proof(
    client, db_session, participant_provider
):
    owner = _account(client, "c2b-proof-owner@example.com")
    speaker_email = "c2b-proof-speaker@example.com"
    speaker = _account(client, speaker_email)
    _, _, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"])
    first_proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", speaker_email),
    )
    second_proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", speaker_email),
    )
    key = uuid.uuid4()
    first = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": first_proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(speaker, key),
    )
    changed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": second_proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(speaker, key),
    )
    assert first.status_code == 200
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    record = db_session.scalar(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.operation == "interview_participant.confirm",
            CommandIdempotencyRecord.idempotency_key == key,
        )
    )
    serialized = repr((record.request_digest, record.response_body))
    assert first_proof not in serialized and second_proof not in serialized
    fingerprint = idempotency_service.verification_proof_fingerprint(
        participant_provider, uuid.UUID(participant["id"]), first_proof
    )
    canonical = idempotency_service.canonical_request_bytes(
        idempotency_service.participant_confirm_request(
            uuid.UUID(participant["id"]), 1, fingerprint, True
        )
    )
    assert first_proof.encode() not in canonical
    assert second_proof.encode() not in canonical


def test_participant_snapshots_default_deny_and_no_consent_side_effects(
    client, db_session, participant_provider
):
    owner = _account(client, "c2b-snapshot-owner@example.com")
    speaker_email = "c2b-snapshot-speaker@example.com"
    speaker = _account(client, speaker_email)
    _, _, interview = _interview(client, owner)
    participant = _proposal(client, owner, interview["id"])
    proof = _participant_proof(
        client,
        participant_provider,
        speaker,
        participant["id"],
        ("email", speaker_email),
    )
    confirmed = client.post(
        f"/api/v1/participants/{participant['id']}/confirm",
        json={
            "verification_proof": proof,
            "adult_autonomous_decision": True,
            "expected_version": 1,
        },
        headers=_with_key(speaker),
    )
    assert confirmed.status_code == 200
    operations = {
        "identity_verification.participant_challenge",
        "identity_verification.participant_verify",
        "interview_participant.propose",
        "interview_participant.confirm",
        "interview_participant.inactivate",
    }
    assert operations <= idempotency_service._ALLOWED_SNAPSHOTS.keys()
    with pytest.raises(ValidationError):
        idempotency_service.ParticipantResultSnapshot.model_validate(
            {**confirmed.json(), "unexpected": {"nested": "denied"}}
        )
    table_names = set(db_session.get_bind().dialect.get_table_names(db_session.connection()))
    assert (
        not {
            "consent_grants",
            "consent_events",
            "source_consent_bindings",
        }
        & table_names
    )
