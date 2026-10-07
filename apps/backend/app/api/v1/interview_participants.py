import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from app.core.rights_auth_provider import RightsAuthProvider, get_rights_auth_provider
from app.dependencies.auth import SessionDep, get_current_user
from app.dependencies.participant_actor import ParticipantActorDep
from app.models.user import User
from app.schemas.interview_participant import (
    ParticipantConfirm,
    ParticipantInactivate,
    ParticipantProposal,
    ParticipantRead,
)
from app.services import interview_participant as service

router = APIRouter(tags=["interview-participants"])
CurrentUser = Annotated[User, Depends(get_current_user)]
ProviderDep = Annotated[RightsAuthProvider, Depends(get_rights_auth_provider)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]


@router.post(
    "/interviews/{interview_id}/participants", response_model=ParticipantRead, status_code=201
)
def propose_participant(
    interview_id: uuid.UUID,
    data: ParticipantProposal,
    db: SessionDep,
    current_user: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> ParticipantRead:
    return ParticipantRead.model_validate(
        service.propose(
            db,
            actor=current_user,
            interview_id=interview_id,
            family_member_id=data.family_member_id,
            roles=data.roles,
            idempotency_key=idempotency_key,
        )
    )


@router.post("/participants/{participant_id}/confirm", response_model=ParticipantRead)
def confirm_participant(
    participant_id: uuid.UUID,
    data: ParticipantConfirm,
    db: SessionDep,
    actor: ParticipantActorDep,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> ParticipantRead:
    return ParticipantRead.model_validate(
        service.confirm(
            db,
            actor=actor,
            participant_id=participant_id,
            proof=data.verification_proof.get_secret_value(),
            adult_autonomous_decision=data.adult_autonomous_decision,
            expected_version=data.expected_version,
            idempotency_key=idempotency_key,
            provider=provider,
        )
    )


@router.post("/participants/{participant_id}/inactive", response_model=ParticipantRead)
def inactivate_participant(
    participant_id: uuid.UUID,
    data: ParticipantInactivate,
    db: SessionDep,
    actor: ParticipantActorDep,
    idempotency_key: IdempotencyKey,
) -> ParticipantRead:
    return ParticipantRead.model_validate(
        service.inactivate(
            db,
            actor=actor,
            participant_id=participant_id,
            expected_version=data.expected_version,
            idempotency_key=idempotency_key,
        )
    )


@router.get("/rights/participants/{participant_id}", response_model=ParticipantRead)
def read_own_participant(
    participant_id: uuid.UUID, db: SessionDep, actor: ParticipantActorDep
) -> ParticipantRead:
    return ParticipantRead.model_validate(
        service.get_self(db, actor=actor, participant_id=participant_id)
    )
