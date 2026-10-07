import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException

from app.core.security import decode_rights_token
from app.dependencies.auth import CredentialsDep, SessionDep, get_current_user
from app.dependencies.rights_auth import get_rights_user
from app.models.user import User


@dataclass(frozen=True)
class ParticipantActor:
    user: User
    authentication: Literal["account", "rights"]
    contact_id: uuid.UUID | None


def get_participant_actor(credentials: CredentialsDep, db: SessionDep) -> ParticipantActor:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        unverified = jwt.decode(credentials.credentials, options={"verify_signature": False})
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication") from None
    if unverified.get("token_type") == "account":
        return ParticipantActor(get_current_user(credentials, db), "account", None)
    if unverified.get("token_type") == "rights":
        user = get_rights_user(credentials, db)
        try:
            contact_id = uuid.UUID(decode_rights_token(credentials.credentials)["contact_id"])
        except (jwt.InvalidTokenError, KeyError, TypeError, ValueError, AttributeError):
            raise HTTPException(status_code=401, detail="Invalid authentication") from None
        return ParticipantActor(user, "rights", contact_id)
    raise HTTPException(status_code=401, detail="Invalid authentication")


ParticipantActorDep = Annotated[ParticipantActor, Depends(get_participant_actor)]
