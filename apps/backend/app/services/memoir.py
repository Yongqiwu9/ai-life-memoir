from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.crud import memoir as crud
from app.crud import memory_workflow as workflow_crud
from app.models.memory_workflow import ContentRevision, RevisionProposal
from app.schemas.memoir import MemoirCreate
from app.services import command_idempotency as commands
from app.services import memory_review as review
from app.services.memory_integrity import get_memory_integrity
from app.services.memory_policy import derive_required_purposes


def _owned(db, user_id, memoir_id):
    memoir = crud.get_owned(db, user_id, memoir_id)
    if memoir is None:
        raise NotFoundException()
    return memoir


def metadata(db, memoir):
    return {
        "id": memoir.id,
        "family_member_id": memoir.family_member_id,
        "status": memoir.status,
        "record_origin": memoir.record_origin,
        "created_at": memoir.created_at,
        "section_count": crud.section_count(db, memoir.id),
    }


def section_metadata(section):
    return {
        "id": section.id,
        "memory_id": section.memory_id,
        "position": section.position,
        "record_origin": section.record_origin,
        "memory_revision_id": section.memory_revision_id,
        "approval_proposal_id": section.approval_proposal_id,
    }


@review._atomic
def create(
    db: Session,
    user_id: UUID,
    member_id: UUID,
    data: MemoirCreate,
    idempotency_key,
    *,
    policy=None,
    integrity=None,
):
    review.member_scope(db, user_id, member_id)
    integrity = integrity or get_memory_integrity()
    record, replay = review._command(
        db,
        user_id,
        "memory.memoir.create",
        idempotency_key,
        scope={"member_id": str(member_id)},
        versions={},
        payload=data.model_dump(mode="json"),
        integrity=integrity,
    )
    if replay:
        return commands.replay_memory(record)
    memories = {}
    # Shared order with the synthetic purge fixture: command -> sorted Memory
    # -> sorted Proposal/proof -> sorted Revision, held until the single commit.
    # Owner-scoped metadata queries precede all proof/body reads.
    for memory_id in sorted({ref.memory_id for ref in data.sections}, key=str):
        memory = review.owned_memory(db, user_id, memory_id, lock=True)
        if memory.family_member_id != member_id:
            raise NotFoundException()
        memories[memory_id] = memory
    for proposal_id in sorted({ref.approval_proposal_id for ref in data.sections}, key=str):
        review.owned(db, RevisionProposal, user_id, proposal_id, lock=True)
    for revision_id in sorted({ref.memory_revision_id for ref in data.sections}, key=str):
        review.owned(db, ContentRevision, user_id, revision_id, lock=True)
    for ref in data.sections:
        _approved_gate(
            db,
            user_id,
            memories[ref.memory_id],
            ref.memory_revision_id,
            ref.approval_proposal_id,
            policy=policy,
            operation="memoir_use",
        )
    sections = []
    for position, ref in enumerate(data.sections, start=1):
        _, payload = review.approved_content(
            db,
            user_id,
            memories[ref.memory_id],
            ref.memory_revision_id,
            ref.approval_proposal_id,
            operation="memoir_use",
            policy=policy,
            integrity=integrity,
        )
        sections.append(
            {
                "memory_id": ref.memory_id,
                "memory_revision_id": ref.memory_revision_id,
                "approval_proposal_id": ref.approval_proposal_id,
                "position": position,
                "record_origin": "approved_revision_snapshot",
                "title": payload.title,
                "content": payload.content,
            }
        )
    memoir = crud.create(db, member_id, data.title, sections)
    snapshot = {
        "memoir_id": memoir.id,
        "section_ids": [section.id for section in memoir.sections],
        "record_origin": "versioned",
    }
    commands.complete_memory(
        record,
        resource_kind="memoir",
        resource_id=memoir.id,
        response_status=201,
        snapshot=snapshot,
    )
    review.commit(db, record)
    return snapshot, 201


def get(db: Session, user_id: UUID, memoir_id: UUID):
    return metadata(db, _owned(db, user_id, memoir_id))


def list_sections(db, user_id, memoir_id, page=1, page_size=20):
    _owned(db, user_id, memoir_id)
    return (
        [section_metadata(section) for section in crud.sections(db, memoir_id, page, page_size)],
        crud.section_count(db, memoir_id),
    )


def _approved_gate(db, user_id, memory, revision_id, proposal_id, *, policy=None, operation="read"):
    revision = review.owned(db, ContentRevision, user_id, revision_id)
    proposal = review.owned(db, RevisionProposal, user_id, proposal_id)
    if (
        revision.memory_id != memory.id
        or revision.family_member_id != memory.family_member_id
        or proposal.state != "approved"
        or proposal.result_memory_id != memory.id
        or proposal.result_memory_revision_id != revision_id
    ):
        raise review._error("INVALID_APPROVED_REVISION", 422)
    proof = workflow_crud.proposal_proof(db, proposal.id)
    review.revision_gate(
        db,
        user_id,
        revision,
        operation=operation,
        policy=policy,
        previous_stamp=proof.approval_permission_stamp,
    )


def _section_gate(db, user_id, memoir, section, *, policy=None):
    memory = review.owned_memory(db, user_id, section.memory_id)
    if memory.family_member_id != memoir.family_member_id:
        raise NotFoundException()
    if section.record_origin == "approved_revision_snapshot":
        _approved_gate(
            db,
            user_id,
            memory,
            section.memory_revision_id,
            section.approval_proposal_id,
            policy=policy,
            operation="memoir_use",
        )
    elif section.record_origin == "legacy_snapshot":
        reference = review.source(
            db, user_id, memory.source_message_id, member_id=memoir.family_member_id
        )
        review.gate(
            db,
            user_id,
            reference,
            operation="memoir_use",
            purposes=derive_required_purposes(reference.source),
            policy=policy,
        )
    else:
        raise review._error("CONTENT_RESTRICTED", 403)
    return memory


def _section_content(db, user_id, memoir, section, *, policy=None, integrity=None):
    memory = _section_gate(db, user_id, memoir, section, policy=policy)
    if section.record_origin == "approved_revision_snapshot":
        _, payload = review.approved_content(
            db,
            user_id,
            memory,
            section.memory_revision_id,
            section.approval_proposal_id,
            operation="memoir_use",
            policy=policy,
            integrity=integrity,
        )
        body = crud.section_body(db, memoir.id, section.id)
        if body is None or body.title != payload.title or body.content != payload.content:
            raise review._error("CONTENT_RESTRICTED", 403)
    else:
        (integrity or get_memory_integrity()).require_available()
        body = crud.section_body(db, memoir.id, section.id)
        if body is None:
            raise review._error("CONTENT_RESTRICTED", 403)
    return {
        **section_metadata(section),
        "title": body.title,
        "content": body.content,
        "source_message_id": memory.source_message_id,
    }


def section_content(db, user_id, memoir_id, section_id, *, policy=None, integrity=None):
    memoir = _owned(db, user_id, memoir_id)
    section = crud.get_section(db, memoir.id, section_id)
    if section is None:
        raise NotFoundException()
    return _section_content(db, user_id, memoir, section, policy=policy, integrity=integrity)


def content(db, user_id, memoir_id, *, policy=None, integrity=None):
    memoir = _owned(db, user_id, memoir_id)
    sections = crud.sections(db, memoir.id)
    if not sections:
        raise review._error("CONTENT_RESTRICTED", 403)
    for section in sections:
        _section_gate(db, user_id, memoir, section, policy=policy)
    result = [
        _section_content(db, user_id, memoir, section, policy=policy, integrity=integrity)
        for section in sections
    ]
    return {**metadata(db, memoir), "title": crud.memoir_title(db, memoir.id), "sections": result}
