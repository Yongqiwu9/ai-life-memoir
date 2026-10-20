"""Factory-only internal ASGI application. No configured app or provider by default."""

import secrets
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.dialogue.service import execute
from app.dialogue.wire import WireRequest


def create_app(
    *,
    credential: str | None = None,
    provider=None,
    allocation: Callable[[WireRequest], bool] | None = None,
    max_request_bytes: int | None = None,
    max_response_bytes: int | None = None,
):
    app = FastAPI(debug=False, docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/internal/v1/dialogue/{operation}")
    async def handle(operation: str, request: Request):
        if not credential or allocation is None or not max_request_bytes or not max_response_bytes:
            return JSONResponse({"code": "INTERNAL_UNAVAILABLE"}, status_code=503)
        supplied = request.headers.get("authorization", "")
        if not secrets.compare_digest(supplied, "Bearer " + credential):
            return JSONResponse({"code": "INTERNAL_UNAUTHORIZED"}, status_code=401)
        if operation not in {"initialize", "transitions", "generations"}:
            return JSONResponse({"code": "INVALID_OPERATION"}, status_code=404)
        body = bytearray()
        try:
            async for chunk in request.stream():
                if len(body) + len(chunk) > max_request_bytes:
                    return JSONResponse({"code": "REQUEST_TOO_LARGE"}, status_code=413)
                body.extend(chunk)
            data = WireRequest.model_validate_json(bytes(body))
            if data.operation != {
                "initialize": "initialize",
                "transitions": "transition",
                "generations": "generate",
            }[operation] or not allocation(data):
                return JSONResponse({"code": "PROCESSING_DENIED"}, status_code=403)
            if data.operation == "generate" and provider is None:
                return JSONResponse({"code": "GENERATION_UNAVAILABLE"}, status_code=503)
            # This endpoint uses only bounded synchronous synthetic fixtures. No real provider.
            reply = execute(data, provider)
            encoded = reply.model_dump_json().encode("utf-8")
            if len(encoded) > max_response_bytes:
                return JSONResponse({"code": "RESPONSE_TOO_LARGE"}, status_code=502)
            from starlette.responses import Response

            return Response(encoded, media_type="application/json")
        except Exception:  # noqa: BLE001 - privacy boundary never serializes input/exception
            return JSONResponse({"code": "INVALID_INTERNAL_REQUEST"}, status_code=422)

    return app
