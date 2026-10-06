"""Database operations only; business rules live in Services."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.identity_foundation import AuthChallenge, PrivacyPolicyVersion, UserContact
from app.models.user import User


def add_and_flush(db: Session, item):
    db.add(item)
    db.flush()
    return item


def get_policy(db: Session, policy_id: uuid.UUID, *, lock: bool = False):
    statement = select(PrivacyPolicyVersion).where(PrivacyPolicyVersion.id == policy_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def active_policies(db: Session):
    return list(
        db.scalars(select(PrivacyPolicyVersion).where(PrivacyPolicyVersion.state == "active"))
    )


def get_challenge(db: Session, challenge_id: uuid.UUID, *, lock: bool = False):
    statement = select(AuthChallenge).where(AuthChallenge.id == challenge_id)
    return db.scalar(statement.with_for_update() if lock else statement)


def contacts_for_channel(db: Session, kind: str, lookup_hash: bytes):
    return list(
        db.scalars(
            select(UserContact)
            .where(UserContact.kind == kind, UserContact.lookup_hash == lookup_hash)
            .with_for_update()
        )
    )


def transition_challenge(
    db: Session, challenge_id: uuid.UUID, *, state: str, attempts: int, values: dict
) -> bool:
    result = db.execute(
        update(AuthChallenge)
        .where(
            AuthChallenge.id == challenge_id,
            AuthChallenge.state == state,
            AuthChallenge.attempt_count == attempts,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def locked_user(db: Session, user_id: uuid.UUID):
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def get_contact(db: Session, contact_id: uuid.UUID):
    return db.get(UserContact, contact_id)
