"""Wire-only client. No imports of the independent AI application."""

import asyncio
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.schemas.dialogue import WireReply, WireRequest
from app.services.dialogue_policy import error


class DialogueClient(Protocol):
    def call(self, request: WireRequest) -> WireReply: ...


class UnavailableClient:
    def call(self, request):
        raise error("DIALOGUE_UNAVAILABLE", 503)


def checked_reply(request: WireRequest, value) -> WireReply:
    try:
        reply = WireReply.model_validate_json(
            value.model_dump_json() if isinstance(value, WireReply) else value
        )
        for name in (
            "profile",
            "kernel_version",
            "operation",
            "call_id",
            "scope",
            "persistence_version",
            "stop_fence",
            "input_digest",
        ):
            if getattr(reply, name) != getattr(request, name):
                raise ValueError("binding")
        if (
            reply.context_id != request.context.id
            or reply.context_revision != request.context.context_revision
        ):
            raise ValueError("context")
        return reply
    except Exception:  # noqa: BLE001 - never expose source-bearing validation errors
        raise error("DIALOGUE_INVALID_RESPONSE", 502) from None


class HTTPDialogueClient:
    """Opt-in authenticated internal transport; never constructed by default dependencies."""

    def __init__(
        self,
        *,
        endpoint: str,
        allowed_endpoints: frozenset[str],
        credential: str,
        timeout_seconds: float,
        max_request_bytes: int,
        max_response_bytes: int,
    ):
        parts = urlsplit(endpoint)
        if (
            endpoint not in allowed_endpoints
            or parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or not credential
            or timeout_seconds <= 0
            or min(max_request_bytes, max_response_bytes) <= 0
        ):
            raise error("DIALOGUE_UNAVAILABLE", 503)
        self.endpoint = endpoint.rstrip("/")
        self.credential = credential
        self.timeout = timeout_seconds
        self.request_limit = max_request_bytes
        self.response_limit = max_response_bytes

    def call(self, request):
        body = request.model_dump_json().encode()
        if len(body) > self.request_limit:
            raise error("DIALOGUE_INPUT_LIMIT", 413)
        path = {"initialize": "initialize", "transition": "transitions", "generate": "generations"}[
            request.operation
        ]
        try:
            return asyncio.run(self._exchange(request, body, path))
        except Exception:  # noqa: BLE001 - no request, credential or upstream error text
            raise error("DIALOGUE_TRANSPORT_UNKNOWN", 503) from None

    async def _exchange(self, request, body, path):
        # Absolute deadline includes connect, headers, streaming and cleanup.
        # Cancellation never authorizes a generation resend; caller records UNKNOWN.
        async with (
            asyncio.timeout(self.timeout),
            httpx.AsyncClient(
                timeout=self.timeout, trust_env=False, follow_redirects=False
            ) as client,
            client.stream(
                "POST",
                self.endpoint + "/internal/v1/dialogue/" + path,
                content=body,
                headers={
                    "Authorization": "Bearer " + self.credential,
                    "Content-Type": "application/json",
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise ValueError("upstream")
            result = bytearray()
            async for chunk in response.aiter_bytes():
                if len(result) + len(chunk) > self.response_limit:
                    raise ValueError("limit")
                result.extend(chunk)
            return checked_reply(request, bytes(result))


def get_client() -> DialogueClient:
    return UnavailableClient()
