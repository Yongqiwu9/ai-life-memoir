import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import collaboration as crud
from app.models.collaboration import FamilyMembership
from app.models.family import Family
from app.models.user import User


@dataclass(frozen=True)
class CollaborationAccess:
    family: Family
    role: Literal["owner", "collaborator"]
    membership: FamilyMembership | None


def require_family_actor(
    db: Session, *, actor: User, family_id: uuid.UUID, lock: bool = False
) -> CollaborationAccess:
    if actor.principal_kind != "account":
        raise NotFoundException("Family not found")
    family = crud.get_family(db, family_id, lock=lock)
    if family is None:
        raise NotFoundException("Family not found")
    if family.owner_id == actor.id:
        return CollaborationAccess(family=family, role="owner", membership=None)
    membership = crud.get_family_membership(db, family_id, actor.id, lock=lock)
    if membership is None or membership.state != "active":
        raise NotFoundException("Family not found")
    return CollaborationAccess(family=family, role="collaborator", membership=membership)


def require_family_owner(
    db: Session, *, actor: User, family_id: uuid.UUID, lock: bool = False
) -> Family:
    if actor.principal_kind != "account":
        raise NotFoundException("Family not found")
    family = crud.get_family(db, family_id, lock=lock)
    if family is None or family.owner_id != actor.id:
        raise NotFoundException("Family not found")
    return family
