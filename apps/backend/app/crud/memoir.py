from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.models.family import Family
from app.models.family_member import FamilyMember
from app.models.memoir import Memoir, MemoirSection


def get(db: Session, memoir_id: UUID):
    return db.scalar(select(Memoir).options(defer(Memoir.title)).where(Memoir.id == memoir_id))


def get_owned(db: Session, user_id: UUID, memoir_id: UUID):
    return db.scalar(
        select(Memoir)
        .options(defer(Memoir.title))
        .join(FamilyMember, Memoir.family_member_id == FamilyMember.id)
        .join(Family, FamilyMember.family_id == Family.id)
        .where(Memoir.id == memoir_id, Family.owner_id == user_id)
        .execution_options(populate_existing=True)
    )


def section_query(memoir_id):
    return (
        select(MemoirSection)
        .options(defer(MemoirSection.title), defer(MemoirSection.content))
        .where(MemoirSection.memoir_id == memoir_id)
        .execution_options(populate_existing=True)
    )


def sections(db, memoir_id: UUID, page=None, page_size=None):
    query = section_query(memoir_id).order_by(MemoirSection.position, MemoirSection.id)
    if page is not None:
        query = query.offset((page - 1) * page_size).limit(page_size)
    return list(db.scalars(query))


def get_section(db, memoir_id: UUID, section_id: UUID):
    return db.scalar(section_query(memoir_id).where(MemoirSection.id == section_id))


def section_count(db, memoir_id: UUID):
    return (
        db.scalar(
            select(func.count())
            .select_from(MemoirSection)
            .where(MemoirSection.memoir_id == memoir_id)
        )
        or 0
    )


def section_body(db, memoir_id: UUID, section_id: UUID):
    return db.execute(
        select(MemoirSection.title, MemoirSection.content).where(
            MemoirSection.memoir_id == memoir_id, MemoirSection.id == section_id
        )
    ).first()


def memoir_title(db, memoir_id: UUID):
    return db.scalar(select(Memoir.title).where(Memoir.id == memoir_id))


def create(
    db: Session,
    member_id: UUID,
    title: str,
    sections: list[dict[str, object]],
    *,
    record_origin="versioned",
):
    memoir = Memoir(
        family_member_id=member_id,
        title=title,
        record_origin=record_origin,
        sections=[MemoirSection(**section) for section in sections],
    )
    db.add(memoir)
    db.flush()
    return memoir
