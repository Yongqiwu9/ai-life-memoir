from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status


def get_current_user_id(
    x_user_id: str | None = Header(default=None),
) -> uuid.UUID:
    """
    TEMPLATE ONLY.

    Replace this implementation with the project's real JWT
    authentication dependency before production.

    Never trust a user_id supplied by the request body.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        return uuid.UUID(x_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id",
        ) from exc
