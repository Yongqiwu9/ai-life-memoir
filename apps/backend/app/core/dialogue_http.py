"""Local privacy boundary, including validation/dependency/serialization failures."""

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException

from app.core.exceptions import AppException

SAFE_CODES = frozenset(
    {
        "NOT_FOUND",
        "IDEMPOTENCY_CONFLICT",
        "LEGACY_AGENT_SESSION",
        "SESSION_NOT_ACTIVE",
        "SOURCE_UNAVAILABLE",
        "START_REQUIRED",
        "COMMAND_OUTCOME_UNKNOWN",
        "DIALOGUE_UNAVAILABLE",
        "DIALOGUE_INTEGRITY_UNAVAILABLE",
        "DIALOGUE_INTEGRITY_FAILURE",
        "DIALOGUE_VERSION_CONFLICT",
        "DIALOGUE_STATE_UNAVAILABLE",
        "DIALOGUE_INVALID_REQUEST",
        "DIALOGUE_INVALID_RESPONSE",
        "DIALOGUE_TRANSITION_PENDING",
        "DIALOGUE_GENERATION_UNKNOWN",
        "DIALOGUE_QUEUE_PENDING",
        "DIALOGUE_CHECKPOINT_UNAVAILABLE",
        "DIALOGUE_CONTEXT_UNAVAILABLE",
        "DIALOGUE_CONTEXT_CONFLICT",
        "DIALOGUE_EFFECT_CONFLICT",
        "DIALOGUE_EFFECT_NOT_DISPATCHABLE",
        "DIALOGUE_DELIVERY_UNAVAILABLE",
        "DIALOGUE_INPUT_LIMIT",
        "DIALOGUE_WRITE_REQUIRED",
        "DIALOGUE_TRANSPORT_UNKNOWN",
        "DIALOGUE_TRANSACTION_BOUNDARY",
    }
)


def safe_response(exc):
    if isinstance(exc, HTTPException) and exc.status_code == 401:
        return JSONResponse(
            {"detail": "Not authenticated"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
        )
    code, status = "DIALOGUE_INTERNAL_ERROR", 500
    if isinstance(exc, RequestValidationError):
        code, status = "DIALOGUE_INVALID_REQUEST", 422
    elif isinstance(exc, AppException) and type(exc.code) is str and exc.code in SAFE_CODES:
        code, status = exc.code, exc.status_code
    return JSONResponse(
        {
            "success": False,
            "error": {"code": code, "message": "Dialogue request unavailable", "details": None},
        },
        status_code=status,
    )


class DialogueRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def protected(request):
            try:
                return await original(request)
            except Exception as exc:  # noqa: BLE001 - source-bearing exceptions stay local
                return safe_response(exc)

        return protected
