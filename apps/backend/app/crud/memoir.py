from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.memoir import Memoir, MemoirSection


def get(db: Session, memoir_id: UUID) -> Memoir | None:
    return db.scalar(
        select(Memoir).where(Memoir.id == memoir_id).options(selectinload(Memoir.sections))
    )


def create(db: Session, member_id: UUID, title: str, sections: list[dict[str, object]]) -> Memoir:
    memoir = Memoir(
        family_member_id=member_id,
        title=title,
        sections=[MemoirSection(**section) for section in sections],
    )
    db.add(memoir)
    db.flush()
    return memoir
