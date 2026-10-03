import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.transcript import TranscriptRead
from app.schemas.transcript_segment import (
    TranscriptSegmentCreate,
    TranscriptSegmentList,
    TranscriptSegmentRead,
)
from app.services import transcript as transcript_service
from app.services import transcript_segment as segment_service

router = APIRouter(tags=["transcripts"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/transcripts/{transcript_id}", response_model=TranscriptRead)
def get_transcript(
    transcript_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptRead:
    transcript = transcript_service.get_owned_transcript(
        db,
        user_id=current_user.id,
        transcript_id=transcript_id,
    )
    return TranscriptRead.model_validate(transcript)


@router.post(
    "/transcripts/{transcript_id}/segments",
    response_model=TranscriptSegmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_segment(
    transcript_id: uuid.UUID,
    data: TranscriptSegmentCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptSegmentRead:
    segment = segment_service.create_segment(
        db,
        user_id=current_user.id,
        transcript_id=transcript_id,
        data=data,
    )
    return TranscriptSegmentRead.model_validate(segment)


@router.get("/transcripts/{transcript_id}/segments", response_model=TranscriptSegmentList)
def list_segments(
    transcript_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptSegmentList:
    segments = segment_service.list_segments(
        db,
        user_id=current_user.id,
        transcript_id=transcript_id,
    )
    return TranscriptSegmentList(items=segments, total=len(segments))


@router.get("/segments/{segment_id}", response_model=TranscriptSegmentRead)
def get_segment(
    segment_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptSegmentRead:
    segment = segment_service.get_owned_segment(
        db,
        user_id=current_user.id,
        segment_id=segment_id,
    )
    return TranscriptSegmentRead.model_validate(segment)
