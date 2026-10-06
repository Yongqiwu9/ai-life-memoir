import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.crud import identity_foundation as crud
from app.models.identity_foundation import PrivacyPolicyVersion
from app.schemas.privacy_policy import (
    DraftPolicyParameters,
    PolicyCapabilities,
    PolicyNotices,
    PolicyParameters,
    PrivacySafetyAction,
    ProcessingCapability,
)


def policy_digest(version: str, parameters: dict, notices: dict, capabilities: dict) -> bytes:
    document = {
        "version": version,
        "parameters": parameters,
        "notices": notices,
        "capabilities": capabilities,
    }
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).digest()


def _validate_draft_parameters(parameters: dict) -> None:
    try:
        DraftPolicyParameters.model_validate(parameters)
    except (ValidationError, TypeError, ValueError):
        raise AppException(
            "Invalid policy parameters", code="INVALID_POLICY", status_code=422
        ) from None


def _validate_complete(policy: PrivacyPolicyVersion) -> None:
    PolicyParameters.model_validate(policy.parameters)
    PolicyNotices.model_validate(policy.notices)
    PolicyCapabilities.model_validate(policy.capabilities)
    if policy.digest != policy_digest(
        policy.version, policy.parameters, policy.notices, policy.capabilities
    ):
        raise ValueError("Policy integrity check failed")


def create_draft(db: Session, *, version: str, parameters: dict, notices: dict, capabilities: dict):
    if not version.strip() or len(version) > 100:
        raise AppException("Invalid policy version", code="INVALID_POLICY", status_code=422)
    _validate_draft_parameters(parameters)
    policy = PrivacyPolicyVersion(
        version=version,
        state="draft",
        parameters=parameters,
        notices=notices,
        capabilities=capabilities,
        digest=policy_digest(version, parameters, notices, capabilities),
    )
    crud.add_and_flush(db, policy)
    return policy


def update_draft(
    db: Session, policy_id: UUID, *, parameters: dict, notices: dict, capabilities: dict
):
    policy = crud.get_policy(db, policy_id, lock=True)
    if policy is None or policy.state != "draft" or policy.published_at is not None:
        raise AppException(
            "Published policy is immutable", code="POLICY_IMMUTABLE", status_code=409
        )
    _validate_draft_parameters(parameters)
    policy.parameters, policy.notices, policy.capabilities = parameters, notices, capabilities
    policy.digest = policy_digest(policy.version, parameters, notices, capabilities)
    db.flush()
    return policy


def publish_policy(db: Session, policy_id: UUID):
    policy = crud.get_policy(db, policy_id, lock=True)
    if policy is None or policy.state != "draft" or policy.published_at is not None:
        raise AppException(
            "Policy cannot be published", code="INVALID_POLICY_STATE", status_code=409
        )
    try:
        _validate_complete(policy)
    except (ValidationError, ValueError, TypeError):
        raise AppException(
            "Policy is incomplete or unverified", code="INVALID_POLICY", status_code=422
        ) from None
    if crud.active_policies(db):
        raise AppException(
            "Retire the current policy first", code="ACTIVE_POLICY_EXISTS", status_code=409
        )
    policy.state, policy.published_at = "active", datetime.now(UTC)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppException(
            "Policy publication conflict", code="POLICY_CONFLICT", status_code=409
        ) from None
    return policy


def retire_policy(db: Session, policy_id: UUID):
    policy = crud.get_policy(db, policy_id, lock=True)
    if policy is None or policy.state != "active":
        raise AppException("Policy is not active", code="INVALID_POLICY_STATE", status_code=409)
    policy.state = "retired"
    db.flush()
    return policy


def require_processing_capability(db: Session, capability: ProcessingCapability):
    """Future activation/processing uses this gate; rights safety does not."""
    if capability not in PolicyCapabilities.model_fields:
        raise ValueError("Unknown processing capability")
    policies = crud.active_policies(db)
    try:
        if len(policies) != 1:
            raise ValueError("No unique active policy")
        policy = policies[0]
        _validate_complete(policy)
        if policy.published_at is None:
            raise ValueError("Unpublished policy")
    except (ValidationError, ValueError, TypeError):
        raise AppException(
            "Privacy processing capability unavailable", code="POLICY_UNAVAILABLE", status_code=503
        ) from None
    return policy


def invitation_window_seconds(db: Session) -> int:
    """Return the explicit active-policy invitation window; never invent a default."""
    policies = crud.active_policies(db)
    try:
        if len(policies) != 1:
            raise ValueError("No unique active policy")
        policy = policies[0]
        _validate_complete(policy)
        if policy.published_at is None:
            raise ValueError("Unpublished policy")
        return PolicyParameters.model_validate(policy.parameters).invitation_window.seconds
    except (ValidationError, ValueError, TypeError):
        raise AppException(
            "Invitation policy unavailable", code="POLICY_UNAVAILABLE", status_code=503
        ) from None


def privacy_safety_path(action: PrivacySafetyAction) -> None:
    """Policy-independent classification only, not a withdrawal/deletion implementation.

    Callers must still check verified identity and actual Source/scope ownership.
    """
    if action not in ("withdrawal", "deletion"):
        raise ValueError("Unknown privacy safety action")
