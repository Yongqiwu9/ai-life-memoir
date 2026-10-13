"""Owner-only offline Memory workflow API. Production capabilities default closed."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.memory_http import MemorySafeRoute
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.memory_workflow import (
    CandidateList,
    CandidateRead,
    ExtractionBatchList,
    ExtractionBatchRead,
    ExtractionCommandResult,
    ExtractionCreate,
    ManualCandidateCreate,
    MemoryCommandResult,
    ProcessingCommandResult,
    ProposalApprove,
    ProposalCommandResult,
    ProposalRead,
    ProposalReject,
    ProposalSubmit,
    RevisionContent,
    RevisionCreate,
    RevisionCreated,
    RevisionList,
    VersionCommand,
)
from app.services import memory_extraction as extraction
from app.services import memory_review as review
from app.services.ai_memory_client import MemoryAIClient, get_memory_client
from app.services.memory_integrity import MemoryIntegrity, get_memory_integrity
from app.services.memory_policy import MemoryPolicy, get_memory_policy

router = APIRouter(tags=["memory-workflow"], route_class=MemorySafeRoute)
Db = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_user)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]
Policy = Annotated[MemoryPolicy, Depends(get_memory_policy)]
Integrity = Annotated[MemoryIntegrity, Depends(get_memory_integrity)]
Client = Annotated[MemoryAIClient, Depends(get_memory_client)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _write(result, response: Response):
    value, response.status_code = result
    return value


def _list(result, page, page_size):
    items, total = result
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post(
    "/sessions/{session_id}/memory-extractions",
    status_code=201,
    response_model=ExtractionCommandResult,
    response_model_exclude_unset=True,
)
def extract(
    session_id: UUID,
    data: ExtractionCreate,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    client: Client,
    response: Response,
):
    return _write(
        extraction.start(
            db, actor.id, session_id, data, key, policy=policy, integrity=integrity, client=client
        ),
        response,
    )


@router.get("/memory-extractions/{batch_id}", response_model=ExtractionBatchRead)
def get_batch(batch_id: UUID, db: Db, actor: Actor):
    return extraction.get_batch(db, actor.id, batch_id)


@router.get("/sessions/{session_id}/memory-extractions", response_model=ExtractionBatchList)
def list_batches(session_id: UUID, db: Db, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    return _list(
        extraction.list_batches(db, actor.id, session_id, page, page_size), page, page_size
    )


@router.post(
    "/memory-extractions/{batch_id}/cancel",
    response_model=ExtractionCommandResult | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def cancel(
    batch_id: UUID, data: VersionCommand, db: Db, actor: Actor, key: Key, response: Response
):
    return _write(extraction.cancel_batch(db, actor.id, batch_id, data, key), response)


@router.post(
    "/family-members/{member_id}/memory-candidates/manual",
    status_code=201,
    response_model=RevisionCreated | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def manual(
    member_id: UUID,
    data: ManualCandidateCreate,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    response: Response,
):
    return _write(
        review.manual_candidate(
            db, actor.id, member_id, data, key, policy=policy, integrity=integrity
        ),
        response,
    )


@router.get("/family-members/{member_id}/memory-candidates", response_model=CandidateList)
def candidates(member_id: UUID, db: Db, actor: Actor, page: Page = 1, page_size: PageSize = 20):
    return _list(review.list_candidates(db, actor.id, member_id, page, page_size), page, page_size)


@router.get("/memory-candidates/{candidate_id}", response_model=CandidateRead)
def candidate(candidate_id: UUID, db: Db, actor: Actor):
    return review.get_candidate(db, actor.id, candidate_id)


@router.get("/memory-candidates/{candidate_id}/revisions", response_model=RevisionList)
def candidate_revisions(
    candidate_id: UUID, db: Db, actor: Actor, page: Page = 1, page_size: PageSize = 20
):
    return _list(
        review.list_revisions(db, actor.id, candidate_id, page, page_size), page, page_size
    )


@router.post(
    "/memory-candidates/{candidate_id}/revisions",
    status_code=201,
    response_model=RevisionCreated | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def revise_candidate(
    candidate_id: UUID,
    data: RevisionCreate,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    response: Response,
):
    return _write(
        review.create_candidate_revision(
            db, actor.id, candidate_id, data, key, policy=policy, integrity=integrity
        ),
        response,
    )


@router.post(
    "/memories/{memory_id}/revisions",
    status_code=201,
    response_model=RevisionCreated | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def revise_memory(
    memory_id: UUID,
    data: RevisionCreate,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    response: Response,
):
    return _write(
        review.create_memory_revision(
            db, actor.id, memory_id, data, key, policy=policy, integrity=integrity
        ),
        response,
    )


@router.get("/memories/{memory_id}/revisions", response_model=RevisionList)
def memory_revisions(
    memory_id: UUID, db: Db, actor: Actor, page: Page = 1, page_size: PageSize = 20
):
    return _list(
        review.list_revisions(db, actor.id, memory_id, page, page_size, candidate=False),
        page,
        page_size,
    )


@router.get("/content-revisions/{revision_id}/content", response_model=RevisionContent)
def revision_content(revision_id: UUID, db: Db, actor: Actor, policy: Policy, integrity: Integrity):
    return review.get_revision_content(
        db, actor.id, revision_id, policy=policy, integrity=integrity
    )


@router.get("/revision-proposals/{proposal_id}", response_model=ProposalRead)
def proposal(proposal_id: UUID, db: Db, actor: Actor):
    return review.get_proposal(db, actor.id, proposal_id)


@router.post(
    "/revision-proposals/{proposal_id}/submit",
    response_model=ProposalCommandResult | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def submit(
    proposal_id: UUID,
    data: ProposalSubmit,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    response: Response,
):
    return _write(
        review.submit(db, actor.id, proposal_id, data, key, policy=policy, integrity=integrity),
        response,
    )


@router.post(
    "/revision-proposals/{proposal_id}/approve",
    response_model=ProposalCommandResult | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def approve(
    proposal_id: UUID,
    data: ProposalApprove,
    db: Db,
    actor: Actor,
    key: Key,
    policy: Policy,
    integrity: Integrity,
    response: Response,
):
    return _write(
        review.approve(db, actor.id, proposal_id, data, key, policy=policy, integrity=integrity),
        response,
    )


@router.post(
    "/revision-proposals/{proposal_id}/reject",
    response_model=ProposalCommandResult | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def reject(
    proposal_id: UUID, data: ProposalReject, db: Db, actor: Actor, key: Key, response: Response
):
    return _write(review.reject(db, actor.id, proposal_id, data, key), response)


@router.post(
    "/revision-proposals/{proposal_id}/withdraw",
    response_model=ProposalCommandResult | ProcessingCommandResult,
    response_model_exclude_unset=True,
)
def withdraw(
    proposal_id: UUID, data: VersionCommand, db: Db, actor: Actor, key: Key, response: Response
):
    return _write(review.withdraw(db, actor.id, proposal_id, data, key), response)


@router.get(
    "/family-members/{member_id}/memory-commands/{operation}/{idempotency_key}",
    response_model=MemoryCommandResult,
    response_model_exclude_unset=True,
)
def command_status(
    member_id: UUID, operation: str, idempotency_key: UUID, db: Db, actor: Actor, response: Response
):
    return _write(
        review.command_status(db, actor.id, member_id, operation, idempotency_key), response
    )
