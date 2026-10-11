from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import family_member as member_crud
from app.crud import memoir as crud
from app.models.memoir import Memoir
from app.models.memory import Memory
from app.schemas.memoir import MemoirCreate
from app.services import memory as memory_service


def assemble_sections(memories: list[Memory]) -> list[dict[str, object]]:
    """Deterministic snapshot assembly; no AI or inferred original evidence."""
    return [
        {
            "memory_id": memory.id,
            "position": position,
            "title": memory.title,
            "content": memory.content,
        }
        for position, memory in enumerate(memories, start=1)
    ]


def create(db: Session, user_id: UUID, member_id: UUID, data: MemoirCreate) -> Memoir:
    memory_service.authorize_member(db, user_id, member_id)
    memories = [memory_service.get(db, user_id, memory_id) for memory_id in data.memory_ids]
    if any(memory.family_member_id != member_id for memory in memories):
        raise NotFoundException("Memory not found")
    try:
        memoir = crud.create(db, member_id, data.title, assemble_sections(memories))
        db.commit()
        return get(db, user_id, memoir.id)
    except Exception:
        db.rollback()
        raise


def get(db: Session, user_id: UUID, memoir_id: UUID) -> Memoir:
    memoir = member_crud.get_owned_memoir(db, owner_id=user_id, memoir_id=memoir_id)
    if memoir is None:
        raise NotFoundException("Memoir not found")
    return memoir
