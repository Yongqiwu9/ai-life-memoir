"""
Import every ORM model here so Alembic can discover metadata.
"""

from app.models.audio_recording import AudioRecording  # noqa: F401
from app.models.family import Family  # noqa: F401
from app.models.family_member import FamilyMember  # noqa: F401
from app.models.interview import Interview  # noqa: F401
from app.models.interview_message import InterviewMessage  # noqa: F401
from app.models.interview_session import InterviewSession  # noqa: F401
from app.models.transcript import Transcript  # noqa: F401
from app.models.transcript_segment import TranscriptSegment  # noqa: F401
from app.models.user import User  # noqa: F401
