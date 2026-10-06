import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from app.core.rights_auth_provider import RightsAuthProvider, get_rights_auth_provider
from app.dependencies.auth import SessionDep, get_current_user
from app.models.user import User
from app.schemas.collaboration import (
    InvitationAccept,
    InvitationCreate,
    InvitationRead,
    InvitationTransition,
    MembershipList,
    MembershipRead,
)
from app.services import collaboration as service

router = APIRouter(tags=["family-collaboration"])
CurrentUser = Annotated[User, Depends(get_current_user)]
ProviderDep = Annotated[RightsAuthProvider, Depends(get_rights_auth_provider)]
IdempotencyKey = Annotated[uuid.UUID, Header(alias="Idempotency-Key")]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
ExpectedGeneration = Annotated[int, Query(gt=0)]


@router.post("/families/{family_id}/invitations", response_model=InvitationRead, status_code=201)
def create_invitation(
    family_id: uuid.UUID,
    data: InvitationCreate,
    db: SessionDep,
    current_user: CurrentUser,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> InvitationRead:
    invitation = service.create_invitation(
        db,
        actor=current_user,
        family_id=family_id,
        data=data,
        idempotency_key=idempotency_key,
        provider=provider,
    )
    return InvitationRead.model_validate(invitation)


@router.post("/invitations/{invitation_id}/approve", response_model=InvitationRead)
def approve_invitation(
    invitation_id: uuid.UUID,
    data: InvitationTransition,
    db: SessionDep,
    current_user: CurrentUser,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> InvitationRead:
    return InvitationRead.model_validate(
        service.approve_invitation(
            db,
            actor=current_user,
            invitation_id=invitation_id,
            expected_version=data.expected_version,
            idempotency_key=idempotency_key,
            provider=provider,
        )
    )


def _transition(
    *,
    action: str,
    invitation_id: uuid.UUID,
    data: InvitationTransition,
    db,
    current_user,
    idempotency_key: uuid.UUID,
) -> InvitationRead:
    return InvitationRead.model_validate(
        service.transition_invitation(
            db,
            actor=current_user,
            invitation_id=invitation_id,
            expected_version=data.expected_version,
            action=action,
            idempotency_key=idempotency_key,
        )
    )


@router.post("/invitations/{invitation_id}/reject", response_model=InvitationRead)
def reject_invitation(
    invitation_id: uuid.UUID,
    data: InvitationTransition,
    db: SessionDep,
    current_user: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> InvitationRead:
    return _transition(
        action="reject",
        invitation_id=invitation_id,
        data=data,
        db=db,
        current_user=current_user,
        idempotency_key=idempotency_key,
    )


@router.post("/invitations/{invitation_id}/cancel", response_model=InvitationRead)
def cancel_invitation(
    invitation_id: uuid.UUID,
    data: InvitationTransition,
    db: SessionDep,
    current_user: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> InvitationRead:
    return _transition(
        action="cancel",
        invitation_id=invitation_id,
        data=data,
        db=db,
        current_user=current_user,
        idempotency_key=idempotency_key,
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=InvitationRead)
def revoke_invitation(
    invitation_id: uuid.UUID,
    data: InvitationTransition,
    db: SessionDep,
    current_user: CurrentUser,
    idempotency_key: IdempotencyKey,
) -> InvitationRead:
    return _transition(
        action="revoke",
        invitation_id=invitation_id,
        data=data,
        db=db,
        current_user=current_user,
        idempotency_key=idempotency_key,
    )


@router.post("/invitations/{invitation_id}/accept", response_model=MembershipRead)
def accept_invitation(
    invitation_id: uuid.UUID,
    data: InvitationAccept,
    db: SessionDep,
    current_user: CurrentUser,
    provider: ProviderDep,
    idempotency_key: IdempotencyKey,
) -> MembershipRead:
    membership = service.accept_invitation(
        db,
        actor=current_user,
        invitation_id=invitation_id,
        expected_version=data.expected_version,
        invitation_token=data.invitation_token.get_secret_value(),
        verification_proof=data.verification_proof.get_secret_value(),
        idempotency_key=idempotency_key,
        provider=provider,
    )
    return MembershipRead.model_validate(membership)


@router.get("/families/{family_id}/memberships", response_model=MembershipList)
def list_memberships(
    family_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
    page: Page = 1,
    page_size: PageSize = 20,
) -> MembershipList:
    items, total = service.list_memberships(
        db, actor=current_user, family_id=family_id, page=page, page_size=page_size
    )
    return MembershipList(items=items, page=page, page_size=page_size, total=total)


@router.delete("/families/{family_id}/memberships/{membership_id}", response_model=MembershipRead)
def end_membership(
    family_id: uuid.UUID,
    membership_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
    idempotency_key: IdempotencyKey,
    expected_generation: ExpectedGeneration,
) -> MembershipRead:
    return MembershipRead.model_validate(
        service.end_membership(
            db,
            actor=current_user,
            family_id=family_id,
            membership_id=membership_id,
            expected_generation=expected_generation,
            idempotency_key=idempotency_key,
        )
    )
