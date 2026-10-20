"""Explicit synthetic allocation, keyring and logical clock; defaults grant nothing."""

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.exceptions import AppException
from app.schemas.dialogue import Policy


def error(code: str, status: int = 409):
    return AppException("Dialogue operation unavailable", code=code, status_code=status)


class Allocation(Protocol):
    def require(self, actor: UUID, session: UUID) -> None: ...
    def elapsed_ms(self, session: UUID) -> int: ...


class UnavailableAllocation:
    def require(self, actor, session):
        raise error("DIALOGUE_UNAVAILABLE", 503)

    def elapsed_ms(self, session):
        raise error("DIALOGUE_UNAVAILABLE", 503)


class Integrity:
    def __init__(self, keys: dict[str, bytes], current: str):
        if current not in keys or any(len(value) < 32 for value in keys.values()):
            raise error("DIALOGUE_INTEGRITY_UNAVAILABLE", 503)
        self._keys = dict(keys)
        self.current = current

    def sign(self, value, key_id=None) -> bytes:
        key = self._keys.get(key_id or self.current)
        if key is None:
            raise error("DIALOGUE_INTEGRITY_UNAVAILABLE", 503)
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hmac.digest(key, raw, "sha256")

    def verify(self, value, signature: bytes, key_id: str):
        if not hmac.compare_digest(self.sign(value, key_id), signature):
            raise error("DIALOGUE_INTEGRITY_FAILURE")

    def token(self, actor, session, response, fence, expires):
        return self.sign([str(actor), str(session), str(response), fence, expires]).hex()


@dataclass(frozen=True)
class Runtime:
    allocation: Allocation
    policy: Policy | None = None
    integrity: Integrity | None = None
    delivery_token_ttl_ms: int | None = None

    def require(self, actor, session):
        self.allocation.require(actor, session)
        if self.policy is None or self.integrity is None or not self.delivery_token_ttl_ms:
            raise error("DIALOGUE_UNAVAILABLE", 503)

    def digest_token(self, value: str):
        return hashlib.sha256(value.encode()).digest()


def get_runtime() -> Runtime:
    return Runtime(UnavailableAllocation())
