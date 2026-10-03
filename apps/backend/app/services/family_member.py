import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import family as family_crud
from app.crud import family_member as family_member_crud
from app.models.family_member import FamilyMember
from app.schemas.family_member import FamilyMemberCreate, FamilyMemberUpdate


def _require_owned_family(db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    family = family_crud.get_family(db, owner_id=user_id, family_id=family_id)
    if family is None:
        raise NotFoundException("Family not found")


def _get_member_in_family(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    member_id: uuid.UUID,
) -> FamilyMember:
    _require_owned_family(db, user_id=user_id, family_id=family_id)
    member = family_member_crud.get_family_member(
        db,
        family_id=family_id,
        member_id=member_id,
    )
    if member is None:
        raise NotFoundException("Family member not found")
    return member


def create_family_member(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    data: FamilyMemberCreate,
) -> FamilyMember:
    _require_owned_family(db, user_id=user_id, family_id=family_id)
    return family_member_crud.create_family_member(db, family_id=family_id, name=data.name)


def get_family_member(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    member_id: uuid.UUID,
) -> FamilyMember:
    return _get_member_in_family(
        db,
        user_id=user_id,
        family_id=family_id,
        member_id=member_id,
    )


def list_family_members(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[FamilyMember], int]:
    _require_owned_family(db, user_id=user_id, family_id=family_id)
    offset = (page - 1) * page_size
    return family_member_crud.list_family_members(
        db,
        family_id=family_id,
        offset=offset,
        limit=page_size,
    )


def update_family_member(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    member_id: uuid.UUID,
    data: FamilyMemberUpdate,
) -> FamilyMember:
    member = _get_member_in_family(
        db,
        user_id=user_id,
        family_id=family_id,
        member_id=member_id,
    )
    if data.name is None:
        return member
    return family_member_crud.update_family_member(db, member=member, name=data.name)


def delete_family_member(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    member_id: uuid.UUID,
) -> None:
    member = _get_member_in_family(
        db,
        user_id=user_id,
        family_id=family_id,
        member_id=member_id,
    )
    family_member_crud.delete_family_member(db, member=member)
