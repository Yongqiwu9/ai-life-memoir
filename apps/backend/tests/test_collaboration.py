import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.rights_auth_provider import get_rights_auth_provider
from app.core.security import decode_verification_proof
from app.main import app
from app.models.collaboration import CommandIdempotencyRecord, FamilyInvitation, FamilyMembership
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.user import User
from app.schemas.family import FamilyCreate
from app.services import collaboration as collaboration_service
from app.services import command_idempotency as idempotency_service
from app.services import family as family_service
from app.services import privacy_policy as policy_service
from tests.c1_support import TestOnlyRightsProvider, policy_documents


@pytest.fixture()
def collaboration_provider(client):
    provider = TestOnlyRightsProvider()
    app.dependency_overrides[get_rights_auth_provider] = lambda: provider
    return provider


@pytest.fixture()
def active_collaboration_policy(db_session):
    parameters, notices, capabilities = policy_documents()
    policy = policy_service.create_draft(
        db_session,
        version="collaboration-test-v1",
        parameters=parameters,
        notices=notices,
        capabilities=capabilities,
    )
    policy_service.publish_policy(db_session, policy.id)
    db_session.commit()
    return policy


def _register_and_login(client, email: str):
    password = "strong-password-1"
    assert (
        client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        ).status_code
        == 201
    )
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _with_key(headers: dict[str, str], key: uuid.UUID | None = None):
    return {**headers, "Idempotency-Key": str(key or uuid.uuid4())}


def _create_family(client, headers, name="Collaboration family"):
    response = client.post("/api/v1/families", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def _owner_invitation(client, provider, owner_headers, family_id, recipient_email):
    response = client.post(
        f"/api/v1/families/{family_id}/invitations",
        json={"recipient_kind": "email", "recipient": recipient_email},
        headers=_with_key(owner_headers),
    )
    assert response.status_code == 201
    invitation = response.json()
    return invitation, provider.deliveries[uuid.UUID(invitation["id"])]


def _verify_invitation(client, provider, recipient_headers, invitation, token):
    challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient_headers),
    )
    assert challenge.status_code == 202
    challenge_id = uuid.UUID(challenge.json()["id"])
    response = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": provider.deliveries[challenge_id]},
        headers=_with_key(recipient_headers),
    )
    assert response.status_code == 200
    return response.json()["verification_proof"], challenge_id


def _accept_invitation(client, recipient_headers, invitation, token, proof, key=None):
    return client.post(
        f"/api/v1/invitations/{invitation['id']}/accept",
        json={
            "expected_version": invitation["version"],
            "invitation_token": token,
            "verification_proof": proof,
        },
        headers=_with_key(recipient_headers, key),
    )


def _join_family(client, provider, owner_headers, recipient_headers, family_id, email):
    invitation, token = _owner_invitation(
        client, provider, owner_headers, family_id, recipient_email=email
    )
    proof, _ = _verify_invitation(client, provider, recipient_headers, invitation, token)
    response = _accept_invitation(client, recipient_headers, invitation, token, proof)
    assert response.status_code == 200
    return response.json()


def _assert_archive_not_found(response, *private_values):
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["details"] is None
    serialized = response.text
    for value in private_values:
        assert str(value) not in serialized


def test_owner_invites_verified_account_and_accept_is_idempotent(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "c2a-owner@example.com")
    recipient_headers = _register_and_login(client, "c2a-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "c2a-recipient@example.com",
    )

    assert invitation["state"] == "approved"
    assert "recipient_hash" not in invitation
    assert "recipient_ciphertext" not in invitation
    assert "token_digest" not in invitation

    proof, challenge_id = _verify_invitation(
        client, collaboration_provider, recipient_headers, invitation, token
    )
    claims = decode_verification_proof(proof)
    assert claims["context_kind"] == "invitation_acceptance"
    assert claims["context_id"] == invitation["id"]
    assert claims["challenge_id"] == str(challenge_id)

    key = uuid.uuid4()
    accepted = _accept_invitation(client, recipient_headers, invitation, token, proof, key=key)
    replayed = _accept_invitation(client, recipient_headers, invitation, token, proof, key=key)
    assert accepted.status_code == replayed.status_code == 200
    assert accepted.json() == replayed.json()
    assert accepted.json()["generation"] == 1

    membership_count = db_session.query(FamilyMembership).count()
    assert membership_count == 1
    records = list(db_session.scalars(select(CommandIdempotencyRecord)).all())
    assert records
    for record in records:
        serialized = str(record.response_body).lower()
        assert token not in serialized
        assert proof not in serialized
        assert "verification_proof" not in serialized

    left = client.delete(
        f"/api/v1/families/{family['id']}/memberships/{accepted.json()['id']}",
        params={"expected_generation": 1},
        headers=_with_key(recipient_headers),
    )
    historical_replay = _accept_invitation(
        client, recipient_headers, invitation, token, proof, key=key
    )
    assert left.status_code == historical_replay.status_code == 200
    assert left.json()["state"] == "left"
    assert historical_replay.json() == accepted.json()
    stored_membership = db_session.get(FamilyMembership, uuid.UUID(accepted.json()["id"]))
    assert stored_membership.state == "left"


def test_forwarded_token_wrong_account_and_cross_invitation_proof_are_rejected(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "forward-owner@example.com")
    recipient_headers = _register_and_login(client, "forward-recipient@example.com")
    attacker_headers = _register_and_login(client, "forward-attacker@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "forward-recipient@example.com",
    )

    wrong_challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(attacker_headers),
    )
    assert wrong_challenge.status_code == 401

    proof, _ = _verify_invitation(
        client, collaboration_provider, recipient_headers, invitation, token
    )
    second, second_token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "another-recipient@example.com",
    )
    wrong_context = _accept_invitation(client, recipient_headers, second, second_token, proof)
    assert wrong_context.status_code == 401


def test_collaborator_invitation_requires_owner_approval_and_content_stays_owner_only(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "approval-owner@example.com")
    collaborator_headers = _register_and_login(client, "approval-collaborator@example.com")
    family = _create_family(client, owner_headers)
    _join_family(
        client,
        collaboration_provider,
        owner_headers,
        collaborator_headers,
        family["id"],
        "approval-collaborator@example.com",
    )

    proposed = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "third-person@example.com"},
        headers=_with_key(collaborator_headers),
    )
    assert proposed.status_code == 201
    assert proposed.json()["state"] == "pending_owner"
    invitation_id = proposed.json()["id"]

    self_approve = client.post(
        f"/api/v1/invitations/{invitation_id}/approve",
        json={"expected_version": 1},
        headers=_with_key(collaborator_headers),
    )
    assert self_approve.status_code == 403
    approved = client.post(
        f"/api/v1/invitations/{invitation_id}/approve",
        json={"expected_version": 1},
        headers=_with_key(owner_headers),
    )
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"

    assert (
        client.get(f"/api/v1/families/{family['id']}", headers=collaborator_headers).status_code
        == 404
    )


def test_collaborator_cannot_read_existing_archive_content_matrix(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "content-owner@example.com")
    collaborator_headers = _register_and_login(client, "content-collaborator@example.com")
    owner_id = client.get("/api/v1/users/me", headers=owner_headers).json()["id"]
    family = _create_family(client, owner_headers, "Private family name")
    member = client.post(
        f"/api/v1/families/{family['id']}/members",
        json={"name": "Private family member"},
        headers=owner_headers,
    ).json()
    interview = client.post(
        f"/api/v1/family-members/{member['id']}/interviews",
        json={"title": "Private interview", "type": "life_story"},
        headers=owner_headers,
    ).json()
    session = client.post(
        f"/api/v1/interviews/{interview['id']}/sessions", json={}, headers=owner_headers
    ).json()
    audio = client.post(
        f"/api/v1/sessions/{session['id']}/audios", json={}, headers=owner_headers
    ).json()
    transcript = client.post(
        f"/api/v1/audios/{audio['id']}/transcripts", json={}, headers=owner_headers
    ).json()
    segment = client.post(
        f"/api/v1/transcripts/{transcript['id']}/segments",
        json={"text": "Private transcript text"},
        headers=owner_headers,
    ).json()
    message = client.post(
        f"/api/v1/sessions/{session['id']}/messages",
        json={"content": "Private message text"},
        headers=owner_headers,
    ).json()
    _join_family(
        client,
        collaboration_provider,
        owner_headers,
        collaborator_headers,
        family["id"],
        "content-collaborator@example.com",
    )

    allowed = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "content-third@example.com"},
        headers=_with_key(collaborator_headers),
    )
    assert allowed.status_code == 201
    assert allowed.json()["state"] == "pending_owner"

    private_values = (
        owner_id,
        family["id"],
        member["id"],
        interview["id"],
        session["id"],
        audio["id"],
        transcript["id"],
        segment["id"],
        message["id"],
        "Private family name",
        "Private family member",
        "Private interview",
        "Private transcript text",
        "Private message text",
    )
    family_listing = client.get("/api/v1/families", headers=collaborator_headers)
    assert family_listing.status_code == 200
    assert family_listing.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}
    for private_value in private_values:
        assert str(private_value) not in family_listing.text

    responses = {
        "family.get": client.get(f"/api/v1/families/{family['id']}", headers=collaborator_headers),
        "family.patch": client.patch(
            f"/api/v1/families/{family['id']}",
            json={"name": "Unauthorized family update"},
            headers=collaborator_headers,
        ),
        "family.delete": client.delete(
            f"/api/v1/families/{family['id']}", headers=collaborator_headers
        ),
        "family_member.create": client.post(
            f"/api/v1/families/{family['id']}/members",
            json={"name": "Unauthorized member"},
            headers=collaborator_headers,
        ),
        "family_member.list": client.get(
            f"/api/v1/families/{family['id']}/members", headers=collaborator_headers
        ),
        "family_member.get": client.get(
            f"/api/v1/families/{family['id']}/members/{member['id']}",
            headers=collaborator_headers,
        ),
        "family_member.patch": client.patch(
            f"/api/v1/families/{family['id']}/members/{member['id']}",
            json={"name": "Unauthorized member update"},
            headers=collaborator_headers,
        ),
        "family_member.delete": client.delete(
            f"/api/v1/families/{family['id']}/members/{member['id']}",
            headers=collaborator_headers,
        ),
        "interview.create": client.post(
            f"/api/v1/family-members/{member['id']}/interviews",
            json={"title": "Unauthorized interview", "type": "life_story"},
            headers=collaborator_headers,
        ),
        "interview.list": client.get(
            f"/api/v1/family-members/{member['id']}/interviews",
            headers=collaborator_headers,
        ),
        "interview.get": client.get(
            f"/api/v1/interviews/{interview['id']}", headers=collaborator_headers
        ),
        "interview.patch": client.patch(
            f"/api/v1/interviews/{interview['id']}",
            json={"title": "Unauthorized interview update"},
            headers=collaborator_headers,
        ),
        "interview.delete": client.delete(
            f"/api/v1/interviews/{interview['id']}", headers=collaborator_headers
        ),
        "session.create": client.post(
            f"/api/v1/interviews/{interview['id']}/sessions",
            json={},
            headers=collaborator_headers,
        ),
        "session.list": client.get(
            f"/api/v1/interviews/{interview['id']}/sessions",
            headers=collaborator_headers,
        ),
        "session.get": client.get(
            f"/api/v1/sessions/{session['id']}", headers=collaborator_headers
        ),
        "audio.create": client.post(
            f"/api/v1/sessions/{session['id']}/audios",
            json={},
            headers=collaborator_headers,
        ),
        "audio.list": client.get(
            f"/api/v1/sessions/{session['id']}/audios", headers=collaborator_headers
        ),
        "audio.get": client.get(f"/api/v1/audios/{audio['id']}", headers=collaborator_headers),
        "transcript.create": client.post(
            f"/api/v1/audios/{audio['id']}/transcripts",
            json={},
            headers=collaborator_headers,
        ),
        "transcript.list": client.get(
            f"/api/v1/audios/{audio['id']}/transcripts", headers=collaborator_headers
        ),
        "transcript.get": client.get(
            f"/api/v1/transcripts/{transcript['id']}", headers=collaborator_headers
        ),
        "segment.create": client.post(
            f"/api/v1/transcripts/{transcript['id']}/segments",
            json={"text": "Unauthorized segment"},
            headers=collaborator_headers,
        ),
        "segment.list": client.get(
            f"/api/v1/transcripts/{transcript['id']}/segments",
            headers=collaborator_headers,
        ),
        "segment.get": client.get(
            f"/api/v1/segments/{segment['id']}", headers=collaborator_headers
        ),
        "message.create": client.post(
            f"/api/v1/sessions/{session['id']}/messages",
            json={"content": "Unauthorized message"},
            headers=collaborator_headers,
        ),
        "message.list": client.get(
            f"/api/v1/sessions/{session['id']}/messages", headers=collaborator_headers
        ),
    }
    assert len(responses) == 27
    for response in responses.values():
        _assert_archive_not_found(response, *private_values)


def test_membership_leave_rejoin_and_stale_generation_rejected(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "generation-owner@example.com")
    member_headers = _register_and_login(client, "generation-member@example.com")
    family = _create_family(client, owner_headers)
    membership = _join_family(
        client,
        collaboration_provider,
        owner_headers,
        member_headers,
        family["id"],
        "generation-member@example.com",
    )

    left = client.delete(
        f"/api/v1/families/{family['id']}/memberships/{membership['id']}",
        params={"expected_generation": 1},
        headers=_with_key(member_headers),
    )
    assert left.status_code == 200
    assert left.json()["state"] == "left"
    assert left.json()["generation"] == 2

    stale = client.delete(
        f"/api/v1/families/{family['id']}/memberships/{membership['id']}",
        params={"expected_generation": 1},
        headers=_with_key(owner_headers),
    )
    assert stale.status_code == 409

    rejoined = _join_family(
        client,
        collaboration_provider,
        owner_headers,
        member_headers,
        family["id"],
        "generation-member@example.com",
    )
    assert rejoined["id"] == membership["id"]
    assert rejoined["generation"] == 3
    assert rejoined["state"] == "active"


def test_verification_replay_keeps_original_expiry_and_wrong_code_is_safe(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "proof-owner@example.com")
    recipient_headers = _register_and_login(client, "proof-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "proof-recipient@example.com",
    )
    challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient_headers),
    )
    challenge_id = uuid.UUID(challenge.json()["id"])

    wrong_key = uuid.uuid4()
    wrong = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": "wrong-code"},
        headers=_with_key(recipient_headers, wrong_key),
    )
    wrong_replay = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": "wrong-code"},
        headers=_with_key(recipient_headers, wrong_key),
    )
    assert wrong.status_code == wrong_replay.status_code == 401
    assert "wrong-code" not in str(wrong.json())

    verify_key = uuid.uuid4()
    payload = {"code": collaboration_provider.deliveries[challenge_id]}
    first = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json=payload,
        headers=_with_key(recipient_headers, verify_key),
    )
    second = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json=payload,
        headers=_with_key(recipient_headers, verify_key),
    )
    assert first.status_code == second.status_code == 200
    first_claims = decode_verification_proof(first.json()["verification_proof"])
    second_claims = decode_verification_proof(second.json()["verification_proof"])
    assert first_claims["exp"] == second_claims["exp"]
    assert first_claims["iat"] == second_claims["iat"]

    failed_record = db_session.scalar(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.idempotency_key == wrong_key
        )
    )
    assert failed_record.response_body == {"error_code": "INVALID_VERIFICATION"}


def test_idempotency_result_snapshots_are_operation_specific_and_default_deny():
    invitation_id = uuid.uuid4()
    now = datetime.now(UTC)
    safe_payload = {
        "id": invitation_id,
        "family_id": uuid.uuid4(),
        "requested_by_user_id": uuid.uuid4(),
        "recipient_user_id": None,
        "approved_by_user_id": None,
        "state": "pending_owner",
        "version": 1,
        "approved_at": None,
        "accepted_at": None,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    }
    snapshot = idempotency_service.InvitationResultSnapshot.model_validate(safe_payload)
    record = CommandIdempotencyRecord(
        actor_user_id=uuid.uuid4(),
        operation="family_invitation.create",
        idempotency_key=uuid.uuid4(),
        request_digest=b"d" * 32,
        state="processing",
    )
    idempotency_service.complete(
        record,
        resource_kind="family_invitation",
        resource_id=invitation_id,
        response_status=201,
        snapshot=snapshot,
    )
    assert record.response_body == snapshot.model_dump(mode="json")

    unsafe_payloads = (
        {**safe_payload, "unknown": "value"},
        {**safe_payload, "state": {"nested": "object"}},
        {**safe_payload, "nested": {"token": "raw-token"}},
        {**safe_payload, "recipient_ciphertext_backup": "ciphertext"},
        {**safe_payload, "verification_proof": "raw-proof"},
        {**safe_payload, "invitation_token": "plaintext-token"},
    )
    for payload in unsafe_payloads:
        with pytest.raises(ValidationError):
            idempotency_service.InvitationResultSnapshot.model_validate(payload)

    wrong_operation = CommandIdempotencyRecord(
        actor_user_id=uuid.uuid4(),
        operation="family_membership.revoke",
        idempotency_key=uuid.uuid4(),
        request_digest=b"e" * 32,
        state="processing",
    )
    with pytest.raises(ValueError, match="not allowed"):
        idempotency_service.complete(
            wrong_operation,
            resource_kind="family_invitation",
            resource_id=invitation_id,
            response_status=201,
            snapshot=snapshot,
        )
    with pytest.raises(ValueError, match="not allowed"):
        idempotency_service.complete(
            CommandIdempotencyRecord(
                actor_user_id=uuid.uuid4(),
                operation="unknown.operation",
                idempotency_key=uuid.uuid4(),
                request_digest=b"f" * 32,
                state="processing",
            ),
            resource_kind="unknown",
            resource_id=uuid.uuid4(),
            response_status=200,
            snapshot=idempotency_service.ChallengeAcceptedSnapshot(),
        )


def test_sensitive_request_fingerprints_are_keyed_domain_separated_and_stable():
    provider = TestOnlyRightsProvider()
    family_id = uuid.uuid4()
    invitation_id = uuid.uuid4()
    challenge_id = uuid.uuid4()
    recipient = "a@b.co"
    invitation_token = "low-entropy-token"
    verification_code = "123456"
    verification_proof = "header.payload.signature"

    recipient_fingerprint = provider.lookup("email", recipient)
    token_fingerprint = idempotency_service.invitation_token_fingerprint(
        provider, invitation_id, invitation_token
    )
    code_fingerprint = idempotency_service.verification_code_fingerprint(
        provider, challenge_id, verification_code
    )
    proof_fingerprint = idempotency_service.verification_proof_fingerprint(
        provider, invitation_id, verification_proof
    )

    safe_payloads = (
        (
            recipient,
            idempotency_service.invitation_create_request(
                family_id, "email", recipient_fingerprint
            ),
        ),
        (
            invitation_token,
            idempotency_service.invitation_challenge_request(invitation_id, token_fingerprint),
        ),
        (
            verification_code,
            idempotency_service.invitation_verify_request(challenge_id, code_fingerprint),
        ),
        (
            verification_proof,
            idempotency_service.invitation_accept_request(
                invitation_id, 1, token_fingerprint, proof_fingerprint
            ),
        ),
    )
    for raw_value, payload in safe_payloads:
        assert raw_value.encode() not in idempotency_service.canonical_request_bytes(payload)

    assert recipient_fingerprint != hashlib.sha256(recipient.encode()).digest()
    assert code_fingerprint != hashlib.sha256(verification_code.encode()).digest()
    assert token_fingerprint != proof_fingerprint
    assert token_fingerprint != idempotency_service.invitation_token_fingerprint(
        provider, invitation_id, invitation_token + "-different"
    )
    assert code_fingerprint != idempotency_service.verification_code_fingerprint(
        provider, challenge_id, verification_code + "7"
    )
    assert proof_fingerprint != idempotency_service.verification_proof_fingerprint(
        provider, invitation_id, verification_proof + "-different"
    )

    ordered = {"family_id": str(family_id), "expected_version": 1}
    reversed_order = {"expected_version": 1, "family_id": str(family_id)}
    assert idempotency_service.canonical_request_bytes(
        ordered
    ) == idempotency_service.canonical_request_bytes(reversed_order)
    assert idempotency_service.safe_request_digest(
        ordered
    ) == idempotency_service.safe_request_digest(reversed_order)


def test_sensitive_idempotency_inputs_conflict_without_plaintext_persistence(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "fingerprint-owner@example.com")
    recipient_headers = _register_and_login(client, "fingerprint-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "fingerprint-recipient@example.com",
    )

    challenge_key = uuid.uuid4()
    challenge = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient_headers, challenge_key),
    )
    token_conflict = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token + "-different",
        },
        headers=_with_key(recipient_headers, challenge_key),
    )
    assert challenge.status_code == 202
    assert token_conflict.status_code == 409

    challenge_id = uuid.UUID(challenge.json()["id"])
    code = collaboration_provider.deliveries[challenge_id]
    verify_key = uuid.uuid4()
    verified = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": code},
        headers=_with_key(recipient_headers, verify_key),
    )
    code_conflict = client.post(
        f"/api/v1/identity-verifications/challenges/{challenge_id}/verify",
        json={"code": code + "-different"},
        headers=_with_key(recipient_headers, verify_key),
    )
    assert verified.status_code == 200
    assert code_conflict.status_code == 409

    proof = verified.json()["verification_proof"]
    accept_key = uuid.uuid4()
    accepted = _accept_invitation(
        client, recipient_headers, invitation, token, proof, key=accept_key
    )
    accept_token_conflict = _accept_invitation(
        client, recipient_headers, invitation, token + "-different", proof, key=accept_key
    )
    accept_proof_conflict = _accept_invitation(
        client, recipient_headers, invitation, token, proof + "-different", key=accept_key
    )
    assert accepted.status_code == 200
    assert accept_token_conflict.status_code == 409
    assert accept_proof_conflict.status_code == 409

    records = db_session.scalars(
        select(CommandIdempotencyRecord).where(
            CommandIdempotencyRecord.idempotency_key.in_((challenge_key, verify_key, accept_key))
        )
    ).all()
    serialized_records = repr([(record.request_digest, record.response_body) for record in records])
    for raw_value in (token, code, proof):
        assert raw_value not in serialized_records


def test_verification_proof_cannot_be_used_as_account_token(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "token-owner@example.com")
    recipient_headers = _register_and_login(client, "token-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "token-recipient@example.com",
    )
    proof, _ = _verify_invitation(
        client, collaboration_provider, recipient_headers, invitation, token
    )
    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {proof}"})
    assert response.status_code == 401
    assert (
        client.get(
            f"/api/v1/families/{family['id']}",
            headers={"Authorization": f"Bearer {proof}"},
        ).status_code
        == 401
    )
    assert (
        client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {proof}"}).status_code
        == 401
    )

    forged = jwt.encode(
        {
            **decode_verification_proof(proof),
            "context_id": str(uuid.uuid4()),
            "exp": datetime.now(UTC) + timedelta(minutes=2),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    rejected = _accept_invitation(client, recipient_headers, invitation, token, forged)
    assert rejected.status_code == 401


def test_idempotency_key_digest_conflict_and_duplicate_invitation(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "idempotency-owner@example.com")
    _register_and_login(client, "idempotency-recipient@example.com")
    family = _create_family(client, owner_headers)
    key = uuid.uuid4()
    first = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "idempotency-recipient@example.com"},
        headers=_with_key(owner_headers, key),
    )
    replay = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "idempotency-recipient@example.com"},
        headers=_with_key(owner_headers, key),
    )
    conflict = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "different@example.com"},
        headers=_with_key(owner_headers, key),
    )
    duplicate = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "idempotency-recipient@example.com"},
        headers=_with_key(owner_headers),
    )
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert conflict.status_code == 409
    assert duplicate.status_code == 409

    revoked = client.post(
        f"/api/v1/invitations/{first.json()['id']}/revoke",
        json={"expected_version": first.json()["version"]},
        headers=_with_key(owner_headers),
    )
    historical_replay = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "idempotency-recipient@example.com"},
        headers=_with_key(owner_headers, key),
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    assert historical_replay.status_code == 201
    assert historical_replay.json() == first.json()


def test_invitation_transitions_membership_authorization_and_isolation(
    client, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "transition-owner@example.com")
    collaborator_headers = _register_and_login(client, "transition-member@example.com")
    outsider_headers = _register_and_login(client, "transition-outsider@example.com")
    family = _create_family(client, owner_headers)
    other_family = _create_family(client, outsider_headers, "Other family")
    membership = _join_family(
        client,
        collaboration_provider,
        owner_headers,
        collaborator_headers,
        family["id"],
        "transition-member@example.com",
    )

    owner_list = client.get(f"/api/v1/families/{family['id']}/memberships", headers=owner_headers)
    assert owner_list.status_code == 200
    assert [item["id"] for item in owner_list.json()["items"]] == [membership["id"]]

    pending_reject = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "reject@example.com"},
        headers=_with_key(collaborator_headers),
    ).json()
    wrong_version = client.post(
        f"/api/v1/invitations/{pending_reject['id']}/reject",
        json={"expected_version": 2},
        headers=_with_key(owner_headers),
    )
    assert wrong_version.status_code == 409
    rejected = client.post(
        f"/api/v1/invitations/{pending_reject['id']}/reject",
        json={"expected_version": 1},
        headers=_with_key(owner_headers),
    )
    assert rejected.status_code == 200 and rejected.json()["state"] == "rejected"
    reject_again = client.post(
        f"/api/v1/invitations/{pending_reject['id']}/reject",
        json={"expected_version": 2},
        headers=_with_key(owner_headers),
    )
    assert reject_again.status_code == 409

    pending_cancel = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "cancel@example.com"},
        headers=_with_key(collaborator_headers),
    ).json()
    cancelled = client.post(
        f"/api/v1/invitations/{pending_cancel['id']}/cancel",
        json={"expected_version": 1},
        headers=_with_key(collaborator_headers),
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"

    approved, _ = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "revoke-invitation@example.com",
    )
    revoked = client.post(
        f"/api/v1/invitations/{approved['id']}/revoke",
        json={"expected_version": approved["version"]},
        headers=_with_key(owner_headers),
    )
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"

    cannot_revoke_other = client.delete(
        f"/api/v1/families/{family['id']}/memberships/{uuid.uuid4()}",
        params={"expected_generation": 1},
        headers=_with_key(collaborator_headers),
    )
    cross_family = client.delete(
        f"/api/v1/families/{other_family['id']}/memberships/{membership['id']}",
        params={"expected_generation": 1},
        headers=_with_key(owner_headers),
    )
    assert cannot_revoke_other.status_code == cross_family.status_code == 404

    owner_revoked = client.delete(
        f"/api/v1/families/{family['id']}/memberships/{membership['id']}",
        params={"expected_generation": 1},
        headers=_with_key(owner_headers),
    )
    assert owner_revoked.status_code == 200
    assert owner_revoked.json()["state"] == "revoked"
    assert (
        client.get(
            f"/api/v1/families/{family['id']}/memberships", headers=collaborator_headers
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("aud", "wrong-audience"),
        ("iss", "wrong-issuer"),
        ("scope", ["account:api"]),
        ("token_type", "account"),
        ("context_kind", "participant_confirmation"),
        ("context_id", str(uuid.uuid4())),
        ("sub", str(uuid.uuid4())),
        ("auth_generation", 999),
    ],
)
def test_verification_proof_claim_confusion_rejected(
    client,
    collaboration_provider,
    active_collaboration_policy,
    claim,
    value,
):
    owner_headers = _register_and_login(client, f"claims-owner-{claim}@example.com")
    recipient_email = f"claims-recipient-{claim}@example.com"
    recipient_headers = _register_and_login(client, recipient_email)
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client, collaboration_provider, owner_headers, family["id"], recipient_email
    )
    proof, _ = _verify_invitation(
        client, collaboration_provider, recipient_headers, invitation, token
    )
    claims = decode_verification_proof(proof)
    claims[claim] = value
    forged = jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert (
        _accept_invitation(client, recipient_headers, invitation, token, forged).status_code == 401
    )


def test_revoked_contact_unconsumed_challenge_expired_proof_and_invitation_expiry(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "proof-state-owner@example.com")
    recipient_headers = _register_and_login(client, "proof-state-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "proof-state-recipient@example.com",
    )
    proof, challenge_id = _verify_invitation(
        client, collaboration_provider, recipient_headers, invitation, token
    )
    claims = decode_verification_proof(proof)
    contact = db_session.get(UserContact, uuid.UUID(claims["contact_id"]))
    challenge = db_session.get(AuthChallenge, challenge_id)

    contact.state = "revoked"
    contact.revoked_at = datetime.now(UTC)
    db_session.commit()
    assert (
        _accept_invitation(client, recipient_headers, invitation, token, proof).status_code == 401
    )
    contact.state = "verified"
    contact.revoked_at = None
    challenge.state = "pending"
    db_session.commit()
    assert (
        _accept_invitation(client, recipient_headers, invitation, token, proof).status_code == 401
    )
    challenge.state = "consumed"
    expired_claims = {**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)}
    expired = jwt.encode(expired_claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    db_session.commit()
    assert (
        _accept_invitation(client, recipient_headers, invitation, token, expired).status_code == 401
    )

    stored_invitation = db_session.get(FamilyInvitation, uuid.UUID(invitation["id"]))
    stored_invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    expired_invitation = _accept_invitation(client, recipient_headers, invitation, token, proof)
    assert expired_invitation.status_code == 401
    db_session.refresh(stored_invitation)
    assert stored_invitation.state == "expired"


def test_non_account_principals_cannot_own_or_accept(
    db_session, collaboration_provider, active_collaboration_policy
):
    owner = User(
        principal_kind="account",
        email="principal-owner@example.com",
        password_hash="hash",
    )
    rights_only = User(principal_kind="rights_only")
    system = User(principal_kind="system")
    db_session.add_all([owner, rights_only, system])
    db_session.flush()
    family = family_service.create_family(
        db_session, actor=owner, data=FamilyCreate(name="Principal checks")
    )
    db_session.commit()

    for principal in (rights_only, system):
        with pytest.raises(AppException) as owner_error:
            family_service.create_family(
                db_session, actor=principal, data=FamilyCreate(name="Invalid owner")
            )
        assert owner_error.value.status_code == 404
        with pytest.raises(AppException) as accept_error:
            collaboration_service.accept_invitation(
                db_session,
                actor=principal,
                invitation_id=uuid.uuid4(),
                expected_version=1,
                invitation_token="not-a-token",
                verification_proof="not-a-proof",
                idempotency_key=uuid.uuid4(),
                provider=collaboration_provider,
            )
        assert accept_error.value.status_code == 401
    assert family.owner_id == owner.id


def test_invitation_token_and_corrupt_recipient_binding_fail_closed(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "binding-owner@example.com")
    recipient_headers = _register_and_login(client, "binding-recipient@example.com")
    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        "binding-recipient@example.com",
    )

    wrong_token = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": "wrong-token",
        },
        headers=_with_key(recipient_headers),
    )
    assert wrong_token.status_code == 401

    db_session.execute(
        FamilyInvitation.__table__.update()
        .where(FamilyInvitation.id == uuid.UUID(invitation["id"]))
        .values(recipient_hash=b"x" * 32)
    )
    db_session.commit()
    corrupt_binding = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient_headers),
    )
    assert corrupt_binding.status_code == 401


def test_shared_contact_conflict_no_user_merge_and_provider_fail_closed(
    client, db_session, collaboration_provider, active_collaboration_policy
):
    owner_headers = _register_and_login(client, "conflict-owner@example.com")
    _register_and_login(client, "conflict-existing@example.com")
    recipient_headers = _register_and_login(client, "conflict-recipient@example.com")
    owner = db_session.scalar(select(User).where(User.email == "conflict-owner@example.com"))
    conflicting = db_session.scalar(
        select(User).where(User.email == "conflict-existing@example.com")
    )
    recipient = db_session.scalar(
        select(User).where(User.email == "conflict-recipient@example.com")
    )
    assert owner is not None and conflicting is not None and recipient is not None
    original_user_ids = set(db_session.scalars(select(User.id)).all())
    recipient_hash = collaboration_provider.lookup("email", recipient.email)
    db_session.add(
        UserContact(
            user_id=conflicting.id,
            kind="email",
            value_ciphertext=collaboration_provider.encrypt(recipient.email.encode()),
            lookup_hash=recipient_hash,
            state="revoked",
            revoked_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    family = _create_family(client, owner_headers)
    invitation, token = _owner_invitation(
        client,
        collaboration_provider,
        owner_headers,
        family["id"],
        recipient.email,
    )
    conflict = client.post(
        "/api/v1/identity-verifications/challenges",
        json={
            "context_kind": "invitation_acceptance",
            "context_id": invitation["id"],
            "invitation_token": token,
        },
        headers=_with_key(recipient_headers),
    )
    assert conflict.status_code == 401
    assert set(db_session.scalars(select(User.id)).all()) == original_user_ids
    assert conflicting.id != recipient.id

    collaboration_provider.available = False
    unavailable = client.post(
        f"/api/v1/families/{family['id']}/invitations",
        json={"recipient_kind": "email", "recipient": "unavailable@example.com"},
        headers=_with_key(owner_headers),
    )
    assert unavailable.status_code == 503
    collaboration_provider.available = True
