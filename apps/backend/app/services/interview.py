import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import family as family_crud
from app.crud import family_member as family_member_crud
from app.crud import interview as interview_crud
from app.models.interview import Interview
from app.schemas.interview import InterviewCreate, InterviewUpdate


def _get_owned_member(db: Session, *, user_id: uuid.UUID, member_id: uuid.UUID) -> None:
    member = family_member_crud.get_family_member_by_id(db, member_id=member_id)
    if member is None:
        raise NotFoundException("Family member not found")
    family = family_crud.get_family(db, owner_id=user_id, family_id=member.family_id)
    if family is None:
        raise NotFoundException("Family member not found")


def get_owned_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    interview = interview_crud.get_interview_by_id(db, interview_id=interview_id)
    if interview is None:
        raise NotFoundException("Interview not found")
    _get_owned_member(db, user_id=user_id, member_id=interview.family_member_id)
    return interview


def create_interview(
    db: Session,
    *,
    user_id: uuid.UUID,
    member_id: uuid.UUID,
    data: InterviewCreate,
) -> Interview:
    _get_owned_member(db, user_id=user_id, member_id=member_id)
    return interview_crud.create_interview(
        db,
        family_member_id=member_id,
        title=data.title,
        type_=data.type.value,
    )


def get_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    return get_owned_interview(db, user_id=user_id, interview_id=interview_id)


def list_interviews(
    db: Session,
    *,
    user_id: uuid.UUID,
    member_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[Interview], int]:
    _get_owned_member(db, user_id=user_id, member_id=member_id)
    offset = (page - 1) * page_size
    return interview_crud.list_interviews(
        db,
        family_member_id=member_id,
        offset=offset,
        limit=page_size,
    )


def update_interview(
    db: Session,
    *,
    user_id: uuid.UUID,
    interview_id: uuid.UUID,
    data: InterviewUpdate,
) -> Interview:
    interview = get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    values: dict[str, str] = {}
    if data.title is not None:
        values["title"] = data.title
    if data.status is not None:
        values["status"] = data.status.value
    if data.type is not None:
        values["type"] = data.type.value
    if not values:
        return interview
    return interview_crud.update_interview(db, interview=interview, values=values)


def delete_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> None:
    interview = get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    interview_crud.delete_interview(db, interview=interview)
