import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import family as family_crud
from app.models.family import Family
from app.models.user import User
from app.schemas.family import FamilyCreate, FamilyUpdate


def _get_owned_family(db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID) -> Family:
    family = family_crud.get_family(db, owner_id=user_id, family_id=family_id)
    if family is None:
        raise NotFoundException("Family not found")
    return family


def create_family(db: Session, *, actor: User, data: FamilyCreate) -> Family:
    if actor.principal_kind != "account":
        raise NotFoundException("User not found")
    return family_crud.create_family(db, owner_id=actor.id, name=data.name)


def get_family(db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID) -> Family:
    return _get_owned_family(db, user_id=user_id, family_id=family_id)


def list_families(
    db: Session,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[Family], int]:
    offset = (page - 1) * page_size
    return family_crud.list_families(db, owner_id=user_id, offset=offset, limit=page_size)


def update_family(
    db: Session,
    *,
    user_id: uuid.UUID,
    family_id: uuid.UUID,
    data: FamilyUpdate,
) -> Family:
    family = _get_owned_family(db, user_id=user_id, family_id=family_id)
    if data.name is None:
        return family
    return family_crud.update_family(db, family=family, name=data.name)


def delete_family(db: Session, *, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    family = _get_owned_family(db, user_id=user_id, family_id=family_id)
    family_crud.delete_family(db, family=family)
