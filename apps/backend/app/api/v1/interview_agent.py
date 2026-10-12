from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from app.core.exceptions import agent_exception_response
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.interview_agent import AgentStateRead, AgentTurnCreate, AgentTurnRead
from app.services import interview_agent as service
from app.services.ai_interview_client import (
    InterviewAIClient,
    ProcessingDecision,
    get_interview_client,
    get_processing_decision,
)


class AgentSafeRoute(APIRoute):
    """Catch before DEBUG middleware, including dependency/serialization failures."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def protected_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except Exception as exc:  # noqa: BLE001 - local privacy boundary must be exhaustive
                return agent_exception_response(exc)

        return protected_handler


router = APIRouter(tags=["interview-agent"], route_class=AgentSafeRoute)
SessionDep = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
DecisionDep = Annotated[ProcessingDecision, Depends(get_processing_decision)]
ClientDep = Annotated[InterviewAIClient, Depends(get_interview_client)]


@router.get("/sessions/{session_id}/agent-state", response_model=AgentStateRead)
def get_state(session_id: UUID, db: SessionDep, current_user: CurrentUser):
    return service.get_state(db, current_user.id, session_id)


@router.post(
    "/sessions/{session_id}/agent-turns",
    response_model=AgentTurnRead,
    status_code=status.HTTP_201_CREATED,
)
def advance(
    session_id: UUID,
    data: AgentTurnCreate,
    db: SessionDep,
    current_user: CurrentUser,
    decision: DecisionDep,
    client: ClientDep,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    response: Response,
):
    result, response.status_code = service.advance_with_status(
        db, current_user.id, session_id, data, idempotency_key, decision, client
    )
    return result


@router.get(
    "/sessions/{session_id}/agent-turns/{turn_id}",
    response_model=AgentTurnRead,
)
def get_turn(session_id: UUID, turn_id: UUID, db: SessionDep, current_user: CurrentUser):
    return service.get_turn(db, current_user.id, session_id, turn_id)
