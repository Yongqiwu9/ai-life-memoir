"""Narrow Memory HTTP privacy boundary; business services own transactions."""

import logging
from uuid import UUID

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

SAFE_ERRORS = {
    "NOT_FOUND": (404, "Resource not found"),
    "INVALID_MEMORY_REQUEST": (422, "Invalid memory request"),
    "INVALID_SOURCE": (422, "Invalid source"),
    "SOURCE_TOO_LARGE": (422, "Source exceeds the supported size"),
    "INVALID_APPROVED_REVISION": (422, "Invalid approved memory revision"),
    "VERSION_CONFLICT": (409, "Memory version conflict"),
    "IDEMPOTENCY_CONFLICT": (409, "Idempotency key conflicts with another request"),
    "IDEMPOTENCY_IN_PROGRESS": (202, "Memory command is processing"),
    "PROPOSAL_STATE_CONFLICT": (409, "Proposal state conflict"),
    "PROPOSAL_STALE": (409, "Proposal is stale"),
    "CANDIDATE_ALREADY_PROMOTED": (409, "Candidate has already been promoted"),
    "BATCH_STATE_CONFLICT": (409, "Extraction batch state conflict"),
    "REVISION_WORKFLOW_REQUIRED": (409, "Use the memory revision workflow"),
    "RESOURCE_IN_USE": (409, "Resource is referenced and cannot be deleted"),
    "RESOURCE_DELETE_OUTCOME_UNKNOWN": (503, "Resource deletion outcome is unknown"),
    "CONTENT_RESTRICTED": (403, "Content is restricted"),
    "MEMORY_PROCESSING_UNAVAILABLE": (503, "Memory processing unavailable"),
    "MEMORY_INTEGRITY_UNAVAILABLE": (503, "Memory integrity unavailable"),
    "COMMAND_OUTCOME_UNKNOWN": (503, "Memory command outcome is unknown"),
    "AI_PROVIDER_TIMEOUT": (503, "Memory provider reported a timeout"),
    "AI_INVALID_RESPONSE": (502, "Invalid memory provider response"),
    "AI_UNAVAILABLE": (503, "Memory provider unavailable"),
    "MEMORY_STORAGE_UNAVAILABLE": (503, "Memory storage unavailable"),
    "MEMORY_INTERNAL_ERROR": (500, "Internal memory error"),
    "METHOD_NOT_ALLOWED": (405, "Method not allowed"),
}


def is_memory_path(path: str, method: str = "GET", api_prefix: str = "/api/v1") -> bool:
    """Recognize only contracted paths, before UUID validation; never normalize input."""
    prefix = api_prefix.rstrip("/") + "/"
    if not path.startswith(prefix):
        return False
    parts = path[len(prefix) :].split("/")
    if not all(parts):
        return False
    if method == "DELETE":
        return (len(parts) == 2 and parts[0] in {"interviews", "families"}) or (
            len(parts) == 4 and parts[0] == "families" and parts[2] == "members"
        )
    if parts[0] == "sessions":
        return len(parts) == 3 and parts[2] == "memory-extractions"
    if parts[0] == "family-members" and len(parts) >= 3:
        return (
            (len(parts) == 3 and parts[2] in {"memories", "memoirs", "memory-candidates"})
            or (len(parts) == 4 and parts[2:] == ["memory-candidates", "manual"])
            or (len(parts) == 5 and parts[2] == "memory-commands")
        )
    if parts[0] == "memory-extractions":
        return len(parts) == 2 or (len(parts) == 3 and parts[2] == "cancel")
    if parts[0] == "memory-candidates":
        return len(parts) == 2 or (len(parts) == 3 and parts[2] == "revisions")
    if parts[0] == "content-revisions":
        return len(parts) == 3 and parts[2] == "content"
    if parts[0] == "revision-proposals":
        return len(parts) == 2 or (
            len(parts) == 3 and parts[2] in {"submit", "approve", "reject", "withdraw"}
        )
    if parts[0] == "memories":
        return len(parts) == 2 or (len(parts) == 3 and parts[2] in {"revisions", "legacy-snapshot"})
    if parts[0] == "memoirs":
        return (
            len(parts) == 2
            or len(parts) == 3
            and parts[2] in {"sections", "content"}
            or len(parts) == 5
            and parts[2] == "sections"
            and parts[4] == "content"
        )
    return False


def memory_exception_response(exc: Exception) -> JSONResponse:
    """No raw errors, SQL parameters, validation inputs or request bodies."""
    if isinstance(exc, RequestValidationError):
        code = "INVALID_MEMORY_REQUEST"
    elif isinstance(exc, HTTPException) and exc.status_code == 401:
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif isinstance(exc, HTTPException) and exc.status_code == 404:
        code = "NOT_FOUND"
    elif isinstance(exc, HTTPException) and exc.status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif isinstance(exc, AppException) and type(exc.code) is str and exc.code in SAFE_ERRORS:
        code = exc.code
    else:
        code = "MEMORY_INTERNAL_ERROR"
    status_code, message = SAFE_ERRORS[code]
    if (
        code == "NOT_FOUND"
        and isinstance(exc, AppException)
        and exc.message in {"Interview not found", "Family member not found", "Family not found"}
    ):
        message = exc.message
    logger.warning("memory_boundary_error", extra={"memory_error_code": code})
    details = (
        _unknown_details(exc)
        if code in {"COMMAND_OUTCOME_UNKNOWN", "RESOURCE_DELETE_OUTCOME_UNKNOWN"}
        else None
    )
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message, "details": details}},
    )


def _unknown_details(exc: Exception) -> dict:
    """Only typed, current-actor command context; never copy arbitrary details."""
    result = {"outcome": "unknown"}
    if not isinstance(exc, AppException) or type(exc.details) is not dict:
        return result
    operations = {
        "memory.extract",
        "memory.extraction.cancel",
        "memory.candidate.manual",
        "memory.candidate.revise",
        "memory.revise",
        "memory.proposal.submit",
        "memory.proposal.approve",
        "memory.proposal.reject",
        "memory.proposal.withdraw",
        "memory.memoir.create",
    }
    operation = exc.details.get("operation")
    if type(operation) is str and operation in operations:
        result["operation"] = operation
    for field in ("command_id", "idempotency_key"):
        value = exc.details.get(field)
        if type(value) not in (str, UUID):
            continue
        try:
            result[field] = str(UUID(str(value)))
        except ValueError:
            continue
    return result


class MemorySafeRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def protected(request: Request) -> Response:
            try:
                return await original(request)
            except Exception as exc:  # noqa: BLE001 -- privacy boundary must cover all failures
                return memory_exception_response(exc)

        return protected


class MemoryPrivacyMiddleware:
    """Catch narrow-route errors before they reach DEBUG ServerErrorMiddleware."""

    def __init__(self, app: ASGIApp, *, api_prefix: str = "/api/v1") -> None:
        self.app = app
        self.api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_memory_path(
            scope.get("path", ""), scope.get("method", "GET"), self.api_prefix
        ):
            await self.app(scope, receive, send)
            return
        started = False

        async def protected_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, protected_send)
        except Exception as exc:  # noqa: BLE001 -- prevent DEBUG from exposing private material
            if started:
                # No second response and no error repr; stop this already-started stream.
                raise RuntimeError("Memory response could not be completed") from None
            await memory_exception_response(exc)(scope, receive, send)
