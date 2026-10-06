import uuid

import jwt
from fastapi import HTTPException

from app.core.security import decode_rights_token
from app.crud import identity_foundation as crud
from app.dependencies.auth import CredentialsDep, SessionDep


def get_rights_user(credentials: CredentialsDep, db: SessionDep):
    def denied():
        return HTTPException(
            status_code=401,
            detail="Invalid rights authentication",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None:
        raise denied()
    try:
        payload = decode_rights_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
        contact_id = uuid.UUID(payload["contact_id"])
        challenge_id = uuid.UUID(payload["verification_ref"])
    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, AttributeError):
        raise denied() from None
    user = crud.locked_user(db, user_id)
    contact = crud.get_contact(db, contact_id)
    challenge = crud.get_challenge(db, challenge_id)
    if (
        user is None
        or user.principal_kind not in ("account", "rights_only")
        or payload.get("principal_kind") != user.principal_kind
        or payload.get("token_type") != "rights"
        or payload.get("scope") != ["rights:identity"]
        or type(payload.get("auth_generation")) is not int
        or payload["auth_generation"] != user.auth_generation
        or contact is None
        or contact.state != "verified"
        or contact.user_id != user.id
        or challenge is None
        or challenge.state != "consumed"
        or challenge.user_id != user.id
        or challenge.context_kind != "rights_auth"
        or contact.lookup_hash != challenge.channel_hash
    ):
        raise denied()
    # Account is_active is deliberately not a substitute for Speaker-rights revocation.
    return user
