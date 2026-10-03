import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.audio_recording import AudioRecordingCreate, AudioRecordingList, AudioRecordingRead
from app.schemas.transcript import TranscriptCreate, TranscriptList, TranscriptRead
from app.services import audio_recording as audio_service
from app.services import transcript as transcript_service

router = APIRouter(tags=["audios"])

SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/sessions/{session_id}/audios",
    response_model=AudioRecordingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_audio(
    session_id: uuid.UUID,
    data: AudioRecordingCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> AudioRecordingRead:
    audio = audio_service.create_audio(
        db,
        user_id=current_user.id,
        session_id=session_id,
        data=data,
    )
    return AudioRecordingRead.model_validate(audio)


@router.get("/sessions/{session_id}/audios", response_model=AudioRecordingList)
def list_audios(
    session_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> AudioRecordingList:
    audios = audio_service.list_audios(db, user_id=current_user.id, session_id=session_id)
    return AudioRecordingList(items=audios, total=len(audios))


@router.get("/audios/{audio_id}", response_model=AudioRecordingRead)
def get_audio(
    audio_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> AudioRecordingRead:
    audio = audio_service.get_owned_audio(db, user_id=current_user.id, audio_id=audio_id)
    return AudioRecordingRead.model_validate(audio)


@router.post(
    "/audios/{audio_id}/transcripts",
    response_model=TranscriptRead,
    status_code=status.HTTP_201_CREATED,
)
def create_transcript(
    audio_id: uuid.UUID,
    data: TranscriptCreate,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptRead:
    transcript = transcript_service.create_transcript(
        db,
        user_id=current_user.id,
        audio_id=audio_id,
        data=data,
    )
    return TranscriptRead.model_validate(transcript)


@router.get("/audios/{audio_id}/transcripts", response_model=TranscriptList)
def list_transcripts(
    audio_id: uuid.UUID,
    db: SessionDep,
    current_user: CurrentUser,
) -> TranscriptList:
    transcripts = transcript_service.list_transcripts(
        db,
        user_id=current_user.id,
        audio_id=audio_id,
    )
    return TranscriptList(items=transcripts, total=len(transcripts))
