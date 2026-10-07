import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.exceptions import AppException
from app.core.rights_auth_provider import RightsAuthProvider, get_rights_auth_provider
from app.crud import identity_foundation as identity_crud
from app.dependencies.auth import SessionDep
from app.dependencies.participant_actor import ParticipantActorDep
from app.schemas.collaboration import (
    IdentityVerificationChallengeCreate,
    IdentityVerificationChallengeVerify,
    IdentityVerificationReceipt,
    VerificationProofResponse,
)
from app.services import identity_verification as service

router = APIRouter(prefix="/identity-verifications", tags=["identity-verifications"])
ProviderDep = Annotated[RightsAuthProvider, Depends(get_rights_auth_provider)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


@router.post("/challenges", response_model=IdentityVerificationReceipt, status_code=202)
def create_challenge(
    data: IdentityVerificationChallengeCreate,
    db: SessionDep,
    actor: ParticipantActorDep,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> IdentityVerificationReceipt:
    if data.context_kind == "invitation_acceptance":
        if actor.authentication != "account" or data.invitation_token is None:
            raise AppException(
                "Verification unavailable or invalid", code="INVALID_VERIFICATION", status_code=401
            )
        challenge_id = service.create_invitation_challenge(
            db,
            actor=actor.user,
            invitation_id=data.context_id,
            invitation_token=data.invitation_token.get_secret_value(),
            idempotency_key=idempotency_key,
            provider=provider,
        )
    else:
        challenge_id = service.create_participant_challenge(
            db,
            actor=actor,
            participant_id=data.context_id,
            contact_kind=data.contact_kind,
            contact_value=data.contact.get_secret_value() if data.contact else None,
            idempotency_key=idempotency_key,
            provider=provider,
        )
    return IdentityVerificationReceipt(id=challenge_id)


@router.post("/challenges/{challenge_id}/verify", response_model=VerificationProofResponse)
def verify_challenge(
    challenge_id: uuid.UUID,
    data: IdentityVerificationChallengeVerify,
    db: SessionDep,
    actor: ParticipantActorDep,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> VerificationProofResponse:
    challenge = identity_crud.get_challenge(db, challenge_id)
    if challenge is not None and challenge.context_kind == "participant_confirmation":
        proof = service.verify_participant_challenge(
            db,
            actor=actor,
            challenge_id=challenge_id,
            code=data.code.get_secret_value(),
            idempotency_key=idempotency_key,
            provider=provider,
        )
    else:
        if actor.authentication != "account":
            raise AppException(
                "Verification unavailable or invalid", code="INVALID_VERIFICATION", status_code=401
            )
        proof = service.verify_invitation_challenge(
            db,
            actor=actor.user,
            challenge_id=challenge_id,
            code=data.code.get_secret_value(),
            idempotency_key=idempotency_key,
            provider=provider,
        )
    return VerificationProofResponse(verification_proof=proof)
