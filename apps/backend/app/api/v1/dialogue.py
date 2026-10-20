"""Public commands never accept kernel State, scope, clock or generation callbacks."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.core.dialogue_http import DialogueRoute
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.dialogue import (
    ApplyCreate,
    CommandCreate,
    CommandRead,
    DeliveryCreate,
    DeliveryRead,
    StateRead,
    TextCreate,
)
from app.services import dialogue as service
from app.services.dialogue_client import DialogueClient, get_client
from app.services.dialogue_policy import Runtime, get_runtime

router = APIRouter(
    prefix="/sessions/{session_id}/dialogue", tags=["synthetic-dialogue"], route_class=DialogueRoute
)
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_user)]
Policy = Annotated[Runtime, Depends(get_runtime)]
Client = Annotated[DialogueClient, Depends(get_client)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def _status(result, response):
    response.status_code = 202 if result.execution_status in {"queued", "preparing"} else 201
    return result


@router.get("/state", response_model=StateRead)
def state(session_id: UUID, db: DB, actor: Actor, runtime: Policy):
    return service.read_state(db, actor.id, session_id, runtime)


@router.post("/commands", response_model=CommandRead)
def command(
    session_id: UUID,
    data: CommandCreate,
    db: DB,
    actor: Actor,
    runtime: Policy,
    key: Key,
    response: Response,
):
    return _status(service.submit(db, actor.id, session_id, data, key, runtime), response)


@router.post("/messages", response_model=CommandRead)
def message(
    session_id: UUID,
    data: TextCreate,
    db: DB,
    actor: Actor,
    runtime: Policy,
    key: Key,
    response: Response,
):
    return _status(service.save_text(db, actor.id, session_id, data, key, runtime), response)


@router.get("/commands/{command_id}", response_model=CommandRead)
def get_command(session_id: UUID, command_id: UUID, db: DB, actor: Actor):
    return service.read_command(db, actor.id, session_id, command_id)


@router.post("/commands/{command_id}/apply", response_model=CommandRead)
def apply(
    session_id: UUID,
    command_id: UUID,
    data: ApplyCreate,
    db: DB,
    actor: Actor,
    runtime: Policy,
    client: Client,
    key: Key,
    response: Response,
):
    # The original durable command is the operation identity; no new command on retry.
    result = service.apply_command(db, actor.id, session_id, command_id, data, key, runtime, client)
    return _status(result, response)


@router.post("/deliveries/{response_id}/start", response_model=DeliveryRead)
def start_delivery(
    session_id: UUID,
    response_id: UUID,
    data: DeliveryCreate,
    db: DB,
    actor: Actor,
    runtime: Policy,
    client: Client,
    key: Key,
):
    return service.deliver(db, actor.id, session_id, response_id, data, key, runtime, client)


@router.post("/deliveries/{response_id}/complete", response_model=DeliveryRead)
def complete_delivery(
    session_id: UUID,
    response_id: UUID,
    data: DeliveryCreate,
    db: DB,
    actor: Actor,
    runtime: Policy,
    client: Client,
    key: Key,
):
    return service.deliver(
        db, actor.id, session_id, response_id, data, key, runtime, client, complete=True
    )
