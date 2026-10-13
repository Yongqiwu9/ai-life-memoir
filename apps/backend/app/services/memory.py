from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.crud import memory as crud
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services import memory_review as review
from app.services.memory_integrity import get_memory_integrity
from app.services.memory_policy import derive_required_purposes


def authorize_member(db: Session, user_id: UUID, member_id: UUID) -> None:
    review.member_scope(db, user_id, member_id)


def metadata(memory):
    return {
        "id": memory.id,
        "family_member_id": memory.family_member_id,
        "source_message_id": memory.source_message_id,
        "record_origin": memory.record_origin,
        "version": memory.version,
        "revision_counter": memory.revision_counter,
        "origin_candidate_id": memory.origin_candidate_id,
        "current_revision_id": memory.current_revision_id,
        "current_approval_proposal_id": memory.current_approval_proposal_id,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def get(db: Session, user_id: UUID, memory_id: UUID, *, policy=None, integrity=None):
    memory = review.owned_memory(db, user_id, memory_id)
    result = metadata(memory)
    result["current_content"] = None
    result["approval_state"] = (
        "legacy_unreviewed" if memory.record_origin == "legacy" else "unapproved"
    )
    if memory.current_revision_id is not None:
        _, payload = review.approved_content(
            db,
            user_id,
            memory,
            memory.current_revision_id,
            memory.current_approval_proposal_id,
            policy=policy,
            integrity=integrity,
        )
        result["current_content"] = payload.model_dump(mode="json")
        result["approval_state"] = "approved"
    return result


def create(db: Session, user_id: UUID, member_id: UUID, data: MemoryCreate):
    authorize_member(db, user_id, member_id)
    raise AppException(
        "Use the revision workflow", code="REVISION_WORKFLOW_REQUIRED", status_code=409
    )


def update(db: Session, user_id: UUID, memory_id: UUID, data: MemoryUpdate):
    review.owned_memory(db, user_id, memory_id)
    raise AppException(
        "Use the revision workflow", code="REVISION_WORKFLOW_REQUIRED", status_code=409
    )


def list_for_member(db: Session, user_id: UUID, member_id: UUID, page: int, page_size: int):
    authorize_member(db, user_id, member_id)
    rows, total = crud.list_for_member(db, member_id, page, page_size)
    return [metadata(memory) for memory in rows], total


def legacy_snapshot(db: Session, user_id: UUID, memory_id: UUID, *, policy=None, integrity=None):
    memory = review.owned_memory(db, user_id, memory_id)
    if memory.record_origin != "legacy":
        raise review._error("INVALID_MEMORY_REQUEST", 422)
    reference = review.source(
        db, user_id, memory.source_message_id, member_id=memory.family_member_id
    )
    review.gate(
        db,
        user_id,
        reference,
        operation="read",
        purposes=derive_required_purposes(reference.source),
        policy=policy,
    )
    (integrity or get_memory_integrity()).require_available()
    body = crud.legacy_body(db, memory.id)
    if body is None or body.title is None or body.content is None:
        raise review._error("CONTENT_RESTRICTED", 403)
    return {
        "id": memory.id,
        "source_message_id": memory.source_message_id,
        "approved": False,
        "title": body.title,
        "content": body.content,
        "time_text": body.time_text,
        "place": body.place,
        "emotion": body.emotion,
    }
