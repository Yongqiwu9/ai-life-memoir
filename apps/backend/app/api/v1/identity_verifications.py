import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.rights_auth_provider import RightsAuthProvider, get_rights_auth_provider
from app.dependencies.auth import SessionDep, get_current_user
from app.models.user import User
from app.schemas.collaboration import (
    IdentityVerificationChallengeCreate,
    IdentityVerificationChallengeVerify,
    IdentityVerificationReceipt,
    VerificationProofResponse,
)
from app.services import identity_verification as service

router = APIRouter(prefix="/identity-verifications", tags=["identity-verifications"])
CurrentUser = Annotated[User, Depends(get_current_user)]
ProviderDep = Annotated[RightsAuthProvider, Depends(get_rights_auth_provider)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


@router.post("/challenges", response_model=IdentityVerificationReceipt, status_code=202)
def create_challenge(
    data: IdentityVerificationChallengeCreate,
    db: SessionDep,
    current_user: CurrentUser,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> IdentityVerificationReceipt:
    challenge_id = service.create_invitation_challenge(
        db,
        actor=current_user,
        invitation_id=data.context_id,
        invitation_token=data.invitation_token.get_secret_value(),
        idempotency_key=idempotency_key,
        provider=provider,
    )
    return IdentityVerificationReceipt(id=challenge_id)


@router.post("/challenges/{challenge_id}/verify", response_model=VerificationProofResponse)
def verify_challenge(
    challenge_id: uuid.UUID,
    data: IdentityVerificationChallengeVerify,
    db: SessionDep,
    current_user: CurrentUser,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> VerificationProofResponse:
    proof = service.verify_invitation_challenge(
        db,
        actor=current_user,
        challenge_id=challenge_id,
        code=data.code.get_secret_value(),
        idempotency_key=idempotency_key,
        provider=provider,
    )
    return VerificationProofResponse(verification_proof=proof)
