import copy
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.rights_auth_provider import get_rights_auth_provider, keyed_digest
from app.core.security import create_access_token, decode_rights_token
from app.main import app
from app.models.identity_foundation import AuthChallenge, UserContact
from app.models.user import User
from app.schemas.privacy_policy import Duration, PolicyParameters
from app.schemas.rights_auth import ChallengeCreate, ChallengeVerify, UserContactOut
from app.services import privacy_policy as policy_service
from app.services import rights_auth as rights_service
from tests.c1_support import TestOnlyRightsProvider, policy_documents


@pytest.fixture()
def rights_provider(client):
    provider = TestOnlyRightsProvider()
    app.dependency_overrides[get_rights_auth_provider] = lambda: provider
    return provider


def issue(client, provider, channel="rights-test@example.com"):
    receipt = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": channel}
    )
    assert receipt.status_code == 202
    challenge_id = uuid.UUID(receipt.json()["id"])
    code = provider.deliveries[challenge_id]
    verified = client.post(
        f"/api/v1/rights-auth/challenges/{challenge_id}/verify", json={"code": code}
    )
    assert verified.status_code == 200
    return verified.json()["access_token"], challenge_id


def active_policy(db):
    parameters, notices, capabilities = policy_documents()
    policy = policy_service.create_draft(
        db, version="test-v1", parameters=parameters, notices=notices, capabilities=capabilities
    )
    policy_service.publish_policy(db, policy.id)
    db.commit()
    return policy


@pytest.mark.parametrize(
    "attributes",
    [
        {"principal_kind": "account", "email": None, "password_hash": None},
        {"principal_kind": "account", "email": "test@example.com", "password_hash": ""},
        {"principal_kind": "rights_only", "email": "test@example.com", "password_hash": "hash"},
        {"principal_kind": "system", "email": "test@example.com", "password_hash": "hash"},
        {"principal_kind": "unknown", "email": None, "password_hash": None},
        {
            "principal_kind": "rights_only",
            "email": None,
            "password_hash": None,
            "auth_generation": 0,
        },
    ],
)
def test_db_principal_invariants(db_session, attributes):
    db_session.add(User(**attributes))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("kind", ["rights_only", "system"])
def test_non_accounts_have_no_password_login(client, db_session, kind):
    db_session.add(User(principal_kind=kind, email=None, password_hash=None))
    db_session.commit()
    response = client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "anything"}
    )
    assert response.status_code == 401


def test_policy_draft_and_activation(db_session):
    draft = policy_service.create_draft(
        db_session, version="incomplete", parameters={}, notices={}, capabilities={}
    )
    with pytest.raises(AppException) as error:
        policy_service.publish_policy(db_session, draft.id)
    assert error.value.code == "INVALID_POLICY"
    assert draft.state == "draft"
    parameters, notices, capabilities = policy_documents()
    policy_service.update_draft(
        db_session, draft.id, parameters=parameters, notices=notices, capabilities=capabilities
    )
    policy_service.publish_policy(db_session, draft.id)
    db_session.commit()
    assert policy_service.require_processing_capability(db_session, "capture").id == draft.id
    with pytest.raises(AppException):
        policy_service.update_draft(
            db_session, draft.id, parameters={}, notices={}, capabilities={}
        )
    draft.parameters = {}
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()


def test_retired_policy_not_current(db_session):
    policy = active_policy(db_session)
    policy_service.retire_policy(db_session, policy.id)
    db_session.commit()
    with pytest.raises(AppException) as error:
        policy_service.require_processing_capability(db_session, "external_processing")
    assert error.value.status_code == 503
    with pytest.raises(AppException):
        policy_service.publish_policy(db_session, policy.id)


def test_missing_policy_keeps_privacy_safety_path(db_session):
    for capability in (
        "capture",
        "consent",
        "source_restore",
        "sanitization_publish",
        "external_processing",
    ):
        with pytest.raises(AppException) as error:
            policy_service.require_processing_capability(db_session, capability)
        assert error.value.status_code == 503
    policy_service.privacy_safety_path("withdrawal")
    policy_service.privacy_safety_path("deletion")


@pytest.mark.parametrize("value", [0, -1, "30 days", 1.5, True, {"days": 30}])
def test_duration_is_explicit_positive_integer(value):
    with pytest.raises(ValidationError):
        Duration.model_validate({"seconds": value})


def test_policy_no_hidden_defaults_and_coverage():
    with pytest.raises(ValidationError):
        PolicyParameters.model_validate({})
    parameters, _, _ = policy_documents()
    parameters["sanitization_retry_limit"] = -1
    with pytest.raises(ValidationError):
        PolicyParameters.model_validate(parameters)
    parameters["sanitization_retry_limit"] = 0
    parameters["deletion_ledger_retention"] = {"seconds": 1}
    with pytest.raises(ValidationError):
        PolicyParameters.model_validate(parameters)


def test_unverified_capability_and_tampering_fail_closed(db_session):
    parameters, notices, capabilities = policy_documents()
    capabilities["capture"]["verified"] = False
    draft = policy_service.create_draft(
        db_session,
        version="unverified",
        parameters=parameters,
        notices=notices,
        capabilities=capabilities,
    )
    with pytest.raises(AppException):
        policy_service.publish_policy(db_session, draft.id)
    policy = active_policy(db_session)
    # In-place JSON changes are not ORM-tracked; the gate still checks the digest.
    policy.notices["recording"] = "tampered"
    with pytest.raises(AppException):
        policy_service.require_processing_capability(db_session, "capture")


def test_new_user_contact_and_challenge_never_store_plaintext(client, rights_provider, db_session):
    token, challenge_id = issue(client, rights_provider)
    payload = decode_rights_token(token)
    user = db_session.get(User, uuid.UUID(payload["sub"]))
    contact = db_session.scalar(select(UserContact))
    challenge = db_session.get(AuthChallenge, challenge_id)
    assert user.principal_kind == "rights_only"
    assert user.email is None and user.password_hash is None
    assert b"rights-test@example.com" not in contact.value_ciphertext
    assert contact.lookup_hash == rights_provider.lookup("email", "rights-test@example.com")
    assert contact.lookup_hash != hashlib.sha256(b"rights-test@example.com").digest()
    assert challenge.code_digest != rights_provider.deliveries[challenge_id].encode()
    assert (
        challenge.code_digest
        != hashlib.sha256(rights_provider.deliveries[challenge_id].encode()).digest()
    )
    dto = UserContactOut.model_validate(contact).model_dump()
    assert set(dto) == {"id", "kind", "state"}
    assert "ciphertext" not in repr(contact) and "rights-test" not in repr(contact)
    me = client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert set(me.json()) == {"id", "principal_kind", "authentication", "capabilities"}
    assert challenge.state == "consumed" and challenge.consumed_at is not None


def test_rights_account_api_isolation(client, rights_provider):
    token, _ = issue(client, rights_provider)
    headers = {"Authorization": f"Bearer {token}"}
    for method, path, body in [
        ("get", "/api/v1/users/me", None),
        ("get", "/api/v1/families", None),
        ("post", "/api/v1/families", {"name": "Denied"}),
        ("get", f"/api/v1/interviews/{uuid.uuid4()}", None),
        ("get", f"/api/v1/audios/{uuid.uuid4()}", None),
    ]:
        response = getattr(client, method)(
            path, headers=headers, **({"json": body} if body else {})
        )
        assert response.status_code == 401
    client.post(
        "/api/v1/auth/register",
        json={"email": "account@example.com", "password": "strong-password"},
    )
    account_token = client.post(
        "/api/v1/auth/login", json={"email": "account@example.com", "password": "strong-password"}
    ).json()["access_token"]
    assert (
        client.get(
            "/api/v1/rights/me", headers={"Authorization": f"Bearer {account_token}"}
        ).status_code
        == 401
    )


def test_generation_rejects_account_and_rights_tokens(client, rights_provider, db_session):
    token, _ = issue(client, rights_provider)
    payload = decode_rights_token(token)
    user = db_session.get(User, uuid.UUID(payload["sub"]))
    user.auth_generation += 1
    db_session.commit()
    assert (
        client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )
    registered = client.post(
        "/api/v1/auth/register", json={"email": "gen@example.com", "password": "strong-password"}
    ).json()
    account = db_session.get(User, uuid.UUID(registered["id"]))
    account_token = create_access_token(str(account.id), auth_generation=account.auth_generation)
    account.auth_generation += 1
    db_session.commit()
    assert (
        client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {account_token}"}
        ).status_code
        == 401
    )


def test_challenge_wrong_code_lock_and_replay(client, rights_provider, db_session):
    receipt = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "phone", "channel": "+12025550123"}
    ).json()
    challenge_id = uuid.UUID(receipt["id"])
    path = f"/api/v1/rights-auth/challenges/{challenge_id}/verify"
    for attempt in range(1, 4):
        assert client.post(path, json={"code": "wrong-code"}).status_code == 401
        db_session.expire_all()
        assert db_session.get(AuthChallenge, challenge_id).attempt_count == attempt
    assert db_session.get(AuthChallenge, challenge_id).state == "locked"
    assert (
        client.post(path, json={"code": rights_provider.deliveries[challenge_id]}).status_code
        == 401
    )
    token, consumed_id = issue(client, rights_provider)
    assert token
    replay = client.post(
        f"/api/v1/rights-auth/challenges/{consumed_id}/verify",
        json={"code": rights_provider.deliveries[consumed_id]},
    )
    assert replay.status_code == 401


def test_expired_challenge(client, rights_provider, monkeypatch):
    receipt = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "expiry@example.com"}
    ).json()
    challenge_id = uuid.UUID(receipt["id"])

    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(seconds=120)

    monkeypatch.setattr(rights_service, "datetime", FutureDatetime)
    assert (
        client.post(
            f"/api/v1/rights-auth/challenges/{challenge_id}/verify",
            json={"code": rights_provider.deliveries[challenge_id]},
        ).status_code
        == 401
    )


def test_legacy_email_is_not_verified_or_merged(client, rights_provider, db_session):
    client.post(
        "/api/v1/auth/register", json={"email": "legacy@example.com", "password": "strong-password"}
    )
    before = db_session.scalar(select(func.count()).select_from(User))
    receipt = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "legacy@example.com"}
    )
    assert receipt.status_code == 202
    challenge_id = uuid.UUID(receipt.json()["id"])
    result = client.post(
        f"/api/v1/rights-auth/challenges/{challenge_id}/verify",
        json={"code": rights_provider.deliveries[challenge_id]},
    )
    assert result.status_code == 401
    assert db_session.scalar(select(func.count()).select_from(User)) == before
    assert db_session.scalar(select(func.count()).select_from(UserContact)) == 0


def test_creation_receipts_do_not_enumerate_and_inputs_do_not_echo(client, rights_provider):
    client.post(
        "/api/v1/auth/register",
        json={"email": "existing@example.com", "password": "strong-password"},
    )
    existing = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "existing@example.com"}
    )
    unknown = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "unknown@example.com"}
    )
    assert existing.status_code == unknown.status_code == 202
    assert set(existing.json()) == set(unknown.json()) == {"id", "status"}
    for body in (
        {"kind": "email", "channel": "private-invalid"},
        {"kind": "email", "channel": "private@example.com", "state": "verified"},
    ):
        response = client.post("/api/v1/rights-auth/challenges", json=body)
        assert response.status_code == 422 and "private" not in response.text
    assert "private" not in repr(ChallengeCreate(kind="email", channel="private@example.com"))
    assert "test-code" not in repr(ChallengeVerify(code="test-code"))


def test_provider_gated_and_rate_limited(client, rights_provider):
    rights_provider.available = False
    assert (
        client.post(
            "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "gate@example.com"}
        ).status_code
        == 503
    )
    rights_provider.available = True
    rights_provider.rate_allowed = False
    assert (
        client.post(
            "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "gate@example.com"}
        ).status_code
        == 429
    )
    app.dependency_overrides.pop(get_rights_auth_provider)
    assert (
        client.post(
            "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "gate@example.com"}
        ).status_code
        == 503
    )


def test_delivery_failure_invalidates_receipt(client, rights_provider, db_session):
    rights_provider.delivery_fails = True
    assert (
        client.post(
            "/api/v1/rights-auth/challenges",
            json={"kind": "email", "channel": "delivery@example.com"},
        ).status_code
        == 503
    )
    db_session.expire_all()
    assert db_session.scalar(select(AuthChallenge)).state == "expired"


def test_repeat_verified_contact_reuses_same_principal(client, rights_provider):
    first, _ = issue(client, rights_provider)
    second, _ = issue(client, rights_provider)
    assert decode_rights_token(first)["sub"] == decode_rights_token(second)["sub"]


def test_expired_wrong_type_and_legacy_tokens_rejected(client, rights_provider):
    token, _ = issue(client, rights_provider)
    payload = decode_rights_token(token)
    expired = copy.deepcopy(payload)
    expired["exp"] = int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())
    expired_token = jwt.encode(expired, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert (
        client.get(
            "/api/v1/rights/me", headers={"Authorization": f"Bearer {expired_token}"}
        ).status_code
        == 401
    )
    legacy = jwt.encode(
        {"sub": payload["sub"], "iat": payload["iat"], "exp": payload["exp"]},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {legacy}"}).status_code
        == 401
    )
    wrong_type = copy.deepcopy(payload)
    wrong_type["token_type"] = "account"
    wrong_token = jwt.encode(wrong_type, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert (
        client.get(
            "/api/v1/rights/me", headers={"Authorization": f"Bearer {wrong_token}"}
        ).status_code
        == 401
    )


def test_server_key_and_context_bound_digest():
    key = hashlib.sha256(uuid.uuid4().bytes).digest()
    first = keyed_digest(key, b"first", b"code")
    assert first != hashlib.sha256(b"code").digest()
    assert first != keyed_digest(key, b"second", b"code")
    with pytest.raises(ValueError):
        keyed_digest(b"short", b"first", b"code")


def test_draft_rejects_present_invalid_values(db_session):
    for parameters in (
        {"sanitization_review_window": {"seconds": "30 days"}},
        {"sanitization_retry_limit": -1},
        {"sanitization_retry_limit": True},
        {"unknown_default": {"seconds": 30}},
    ):
        with pytest.raises(AppException) as error:
            policy_service.create_draft(
                db_session,
                version=str(uuid.uuid4()),
                parameters=parameters,
                notices={},
                capabilities={},
            )
        assert error.value.status_code == 422


def test_revoked_contact_cannot_authenticate_or_implicitly_recover(
    client, rights_provider, db_session
):
    token, _ = issue(client, rights_provider)
    contact = db_session.scalar(select(UserContact))
    contact.state, contact.revoked_at = "revoked", datetime.now(UTC)
    db_session.commit()
    assert (
        client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )
    receipt = client.post(
        "/api/v1/rights-auth/challenges",
        json={"kind": "email", "channel": "rights-test@example.com"},
    ).json()
    challenge_id = uuid.UUID(receipt["id"])
    assert (
        client.post(
            f"/api/v1/rights-auth/challenges/{challenge_id}/verify",
            json={"code": rights_provider.deliveries[challenge_id]},
        ).status_code
        == 401
    )
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


def test_shared_channel_identity_conflict_rejected(client, rights_provider, db_session):
    issue(client, rights_provider)
    other = User(principal_kind="rights_only")
    db_session.add(other)
    db_session.flush()
    db_session.add(
        UserContact(
            user_id=other.id,
            kind="email",
            value_ciphertext=rights_provider.encrypt(b"rights-test@example.com"),
            lookup_hash=rights_provider.lookup("email", "rights-test@example.com"),
            state="legacy_unverified",
        )
    )
    db_session.commit()
    receipt = client.post(
        "/api/v1/rights-auth/challenges",
        json={"kind": "email", "channel": "rights-test@example.com"},
    ).json()
    challenge_id = uuid.UUID(receipt["id"])
    assert (
        client.post(
            f"/api/v1/rights-auth/challenges/{challenge_id}/verify",
            json={"code": rights_provider.deliveries[challenge_id]},
        ).status_code
        == 401
    )
    assert db_session.scalar(select(func.count()).select_from(User)) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"token_type": "account"},
        {"scope": ["account:api"]},
        {"principal_kind": "system"},
        {"auth_generation": True},
        {"aud": "ordinary-account"},
        {"iss": "untrusted"},
        {"contact_id": str(uuid.uuid4())},
        {"verification_ref": str(uuid.uuid4())},
    ],
)
def test_signed_but_invalid_rights_claims_rejected(client, rights_provider, change):
    token, _ = issue(client, rights_provider)
    payload = decode_rights_token(token)
    payload.update(change)
    forged = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert (
        client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {forged}"}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {forged}"}).status_code
        == 401
    )


def test_rights_remain_independent_of_account_active_flag_and_processing_policy(
    client, rights_provider, db_session
):
    token, _ = issue(client, rights_provider)
    user = db_session.get(User, uuid.UUID(decode_rights_token(token)["sub"]))
    user.is_active = False
    db_session.commit()
    assert (
        client.get("/api/v1/rights/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 200
    )
    with pytest.raises(AppException):
        policy_service.require_processing_capability(db_session, "capture")


def test_sensitive_validation_and_provider_exceptions_do_not_leak(client, rights_provider, caplog):
    code = "private-verification-value"
    response = client.post(
        f"/api/v1/rights-auth/challenges/{uuid.uuid4()}/verify",
        json={"code": code, "attempt_count": 0},
    )
    assert response.status_code == 422 and code not in response.text

    def failed_delivery(*_args):
        raise RuntimeError("private@example.com private-verification-value")

    rights_provider.deliver = failed_delivery
    response = client.post(
        "/api/v1/rights-auth/challenges", json={"kind": "email", "channel": "private@example.com"}
    )
    assert response.status_code == 503
    assert "private" not in response.text and "private" not in caplog.text


def test_published_policy_cannot_be_deleted_by_orm(db_session):
    policy = active_policy(db_session)
    db_session.delete(policy)
    with pytest.raises(ValueError, match="immutable"):
        db_session.flush()
    db_session.rollback()
