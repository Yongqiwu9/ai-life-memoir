import logging

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "APP_ERROR",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: object | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(
            message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


# Agent failures contain source material in validation/SQL/provider exceptions. These
# controlled messages are deliberately independent of the supplied exception text.
AGENT_SAFE_ERRORS = {
    "NOT_FOUND": (404, "Resource not found"),
    "INVALID_AGENT_REQUEST": (422, "Invalid interview agent request"),
    "AGENT_VERSION_CONFLICT": (409, "Interview agent version conflict"),
    "AGENT_STATE_CONFLICT": (409, "Interview agent state conflict"),
    "SESSION_NOT_ACTIVE": (409, "Interview session is not active"),
    "LEGACY_AGENT_SESSION": (409, "Legacy interview agent session"),
    "AGENT_STATE_UNAVAILABLE": (409, "Interview agent state unavailable"),
    "AGENT_GENERATION_PENDING": (409, "Interview agent generation pending"),
    "AGENT_QUESTION_LIMIT": (409, "Interview agent question limit reached"),
    "IDEMPOTENCY_CONFLICT": (409, "Interview agent idempotency conflict"),
    "IDEMPOTENCY_RESULT_UNAVAILABLE": (409, "Interview agent result unavailable"),
    "AGENT_RESULT_DISCARDED": (409, "Interview agent result discarded"),
    "SOURCE_UNAVAILABLE": (409, "Interview agent source unavailable"),
    "PROCESSING_DENIED": (403, "Interview AI processing denied"),
    "POLICY_UNAVAILABLE": (503, "Interview AI processing unavailable"),
    "AI_INVALID_RESPONSE": (502, "Invalid interview AI response"),
    "AI_PROVIDER_TIMEOUT": (503, "Interview AI provider timed out"),
    "AI_UNAVAILABLE": (503, "Interview AI unavailable"),
    "AGENT_STORAGE_UNAVAILABLE": (503, "Interview agent storage unavailable"),
    "AGENT_COMMIT_UNCERTAIN": (503, "Interview agent commit outcome uncertain"),
    "AGENT_INTERNAL_ERROR": (500, "Interview agent internal error"),
}


def is_interview_agent_path(path: str, api_prefix: str = "/api/v1") -> bool:
    """Recognize protected routes before UUID parsing, without normalizing input."""
    prefix = api_prefix.rstrip("/") + "/sessions/"
    if not path.startswith(prefix):
        return False
    parts = path[len(prefix) :].split("/")
    if len(parts) == 2:
        return bool(parts[0]) and parts[1] in {"agent-state", "agent-turns"}
    return len(parts) == 3 and bool(parts[0]) and parts[1] == "agent-turns" and bool(parts[2])


def agent_exception_response(exc: Exception) -> JSONResponse:
    """Pure local serializer; never log or expose exception/request payloads."""
    if isinstance(exc, RequestValidationError):
        logger.warning("interview_agent_validation_error")
        code = "INVALID_AGENT_REQUEST"
    elif isinstance(exc, AppException):
        logger.warning("interview_agent_application_error")
        code = (
            exc.code
            if type(exc.code) is str and exc.code in AGENT_SAFE_ERRORS
            else "AGENT_INTERNAL_ERROR"
        )
    elif isinstance(exc, StarletteHTTPException) and exc.status_code == 401:
        logger.warning("interview_agent_authentication_error")
        detail = (
            exc.detail
            if type(exc.detail) is str
            and exc.detail in {"Not authenticated", "Token expired", "Invalid token"}
            else "Not authenticated"
        )
        return JSONResponse(
            status_code=401,
            content={"detail": detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        logger.warning("interview_agent_internal_error")
        code = "AGENT_INTERNAL_ERROR"
    status_code, message = AGENT_SAFE_ERRORS[code]
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": code, "message": message, "details": None},
        },
    )


def _is_agent_request(request: Request | None) -> bool:
    if request is None:
        return False
    from app.core.config import settings

    return is_interview_agent_path(request.url.path, settings.API_V1_PREFIX)


async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
    if _is_memory_request(_):
        from app.core.memory_http import memory_exception_response

        return memory_exception_response(exc)
    if _is_agent_request(_):
        return agent_exception_response(exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if _is_memory_request(request):
        from app.core.memory_http import memory_exception_response

        return memory_exception_response(exc)
    if _is_agent_request(request):
        return agent_exception_response(exc)
    logger.exception("Unhandled exception: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Internal server error",
            },
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(RequestValidationError, privacy_validation_exception_handler)


async def privacy_validation_exception_handler(request: Request, exc: RequestValidationError):
    from app.core.config import settings

    if _is_memory_request(request):
        from app.core.memory_http import memory_exception_response

        return memory_exception_response(exc)
    if is_interview_agent_path(request.url.path, settings.API_V1_PREFIX):
        return agent_exception_response(exc)
    privacy_paths = (
        settings.API_V1_PREFIX + "/rights-auth/",
        settings.API_V1_PREFIX + "/identity-verifications/",
        settings.API_V1_PREFIX + "/participants/",
    )
    if request.url.path.startswith(privacy_paths) or "/invitations" in request.url.path:
        # Pydantic's default `input` can disclose a raw channel or verification code.
        return JSONResponse(status_code=422, content={"detail": "Invalid rights-auth request"})
    return await request_validation_exception_handler(request, exc)


def _is_memory_request(request: Request | None) -> bool:
    if request is None:
        return False
    from app.core.config import settings
    from app.core.memory_http import is_memory_path

    return is_memory_path(request.url.path, request.method, settings.API_V1_PREFIX)
