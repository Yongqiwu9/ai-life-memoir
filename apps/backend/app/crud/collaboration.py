"""C2A database operations. Business and authorization rules stay in services."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.collaboration import (
    CommandIdempotencyRecord,
    FamilyInvitation,
    FamilyMembership,
)
from app.models.family import Family


def get_family(db: Session, family_id: uuid.UUID, *, lock: bool = False):
    statement = select(Family).where(Family.id == family_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def get_invitation(db: Session, invitation_id: uuid.UUID, *, lock: bool = False):
    statement = select(FamilyInvitation).where(FamilyInvitation.id == invitation_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def get_membership(db: Session, membership_id: uuid.UUID, *, lock: bool = False):
    statement = select(FamilyMembership).where(FamilyMembership.id == membership_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def get_family_membership(
    db: Session, family_id: uuid.UUID, user_id: uuid.UUID, *, lock: bool = False
):
    statement = select(FamilyMembership).where(
        FamilyMembership.family_id == family_id,
        FamilyMembership.user_id == user_id,
    )
    return db.scalar(statement.with_for_update() if lock else statement)


def list_active_memberships(
    db: Session, family_id: uuid.UUID, *, offset: int, limit: int
) -> tuple[list[FamilyMembership], int]:
    condition = (
        FamilyMembership.family_id == family_id,
        FamilyMembership.state == "active",
    )
    items = list(
        db.scalars(
            select(FamilyMembership)
            .where(*condition)
            .order_by(FamilyMembership.joined_at, FamilyMembership.id)
            .offset(offset)
            .limit(limit)
        ).all()
    )
    total = db.scalar(select(func.count()).select_from(FamilyMembership).where(*condition)) or 0
    return items, total


def find_idempotency(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None,
    operation: str,
    idempotency_key: uuid.UUID,
    lock: bool = False,
):
    statement = select(CommandIdempotencyRecord).where(
        CommandIdempotencyRecord.actor_user_id == actor_user_id,
        CommandIdempotencyRecord.operation == operation,
        CommandIdempotencyRecord.idempotency_key == idempotency_key,
    )
    return db.scalar(statement.with_for_update() if lock else statement)
