from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.rights_auth_provider import RightsAuthProvider, get_rights_auth_provider
from app.dependencies.auth import SessionDep
from app.dependencies.rights_auth import get_rights_user
from app.models.user import User
from app.schemas.rights_auth import ChallengeCreate, ChallengeReceipt, ChallengeVerify, RightsMe
from app.schemas.user import Token
from app.services import rights_auth as service

router = APIRouter(tags=["rights-auth"])
ProviderDep = Annotated[RightsAuthProvider, Depends(get_rights_auth_provider)]
RightsUserDep = Annotated[User, Depends(get_rights_user)]


@router.post("/rights-auth/challenges", response_model=ChallengeReceipt, status_code=202)
def create_challenge(payload: ChallengeCreate, db: SessionDep, provider: ProviderDep):
    return ChallengeReceipt(id=service.create_challenge(db, payload, provider))


@router.post("/rights-auth/challenges/{challenge_id}/verify", response_model=Token)
def verify_challenge(
    challenge_id: UUID, payload: ChallengeVerify, db: SessionDep, provider: ProviderDep
):
    return Token(
        access_token=service.verify_challenge(
            db, challenge_id, payload.code.get_secret_value(), provider
        )
    )


@router.get("/rights/me", response_model=RightsMe)
def rights_me(current_user: RightsUserDep):
    return RightsMe(
        id=current_user.id,
        principal_kind=current_user.principal_kind,
        capabilities=["rights:identity"],
    )
