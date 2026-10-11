from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.crud import family_member as member_crud
from app.crud import memory as crud
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services import interview as interview_service
from app.services import interview_session as session_service


def authorize_member(db: Session, user_id: UUID, member_id: UUID) -> None:
    interview_service._get_owned_member(db, user_id=user_id, member_id=member_id)


def get(db: Session, user_id: UUID, memory_id: UUID) -> Memory:
    memory = member_crud.get_owned_memory(db, owner_id=user_id, memory_id=memory_id)
    if memory is None:
        raise NotFoundException("Memory not found")
    return memory


def create(db: Session, user_id: UUID, member_id: UUID, data: MemoryCreate) -> Memory:
    authorize_member(db, user_id, member_id)
    message = crud.get_message(db, data.source_message_id)
    if message is None:
        raise NotFoundException("Source message not found")
    session = session_service.get_owned_session(db, user_id=user_id, session_id=message.session_id)
    interview = interview_service.get_owned_interview(
        db, user_id=user_id, interview_id=session.interview_id
    )
    if interview.family_member_id != member_id:
        raise NotFoundException("Source message not found")
    if message.role != "user" or message.source not in ("text", "audio_transcript"):
        raise AppException("Source must be original user content", code="INVALID_SOURCE")
    try:
        memory = crud.create(db, family_member_id=member_id, **data.model_dump())
        db.commit()
        db.refresh(memory)
        return memory
    except Exception:
        db.rollback()
        raise


def update(db: Session, user_id: UUID, memory_id: UUID, data: MemoryUpdate) -> Memory:
    memory = get(db, user_id, memory_id)
    try:
        crud.update(db, memory, data.model_dump(exclude_unset=True))
        db.commit()
        db.refresh(memory)
        return memory
    except Exception:
        db.rollback()
        raise


def list_for_member(
    db: Session, user_id: UUID, member_id: UUID, page: int, page_size: int
) -> tuple[list[Memory], int]:
    authorize_member(db, user_id, member_id)
    return crud.list_for_member(db, member_id, page, page_size)
