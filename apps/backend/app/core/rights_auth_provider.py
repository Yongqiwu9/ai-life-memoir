"""No production crypto/delivery fallback. Deployments must supply a vetted adapter."""

import hashlib
import hmac
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.core.exceptions import AppException
from app.schemas.rights_auth import RightsAuthConfiguration


def keyed_digest(secret: bytes, domain: bytes, value: bytes) -> bytes:
    if len(secret) < 32:
        raise ValueError("A server-controlled secret of at least 32 bytes is required")
    return hmac.new(secret, domain + b"\x00" + value, hashlib.sha256).digest()


class RightsAuthProvider(ABC):
    """Crypto, key lifecycle, secure delivery and creation rate limiting capability.

    Ready adapters must provide all four; client payloads cannot install adapters.
    Test adapters belong exclusively in tests, never in runtime configuration.
    """

    configuration: RightsAuthConfiguration

    @abstractmethod
    def ready(self) -> bool: ...

    @abstractmethod
    def encrypt(self, value: bytes) -> bytes: ...

    @abstractmethod
    def decrypt(self, value: bytes) -> bytes: ...

    @abstractmethod
    def lookup(self, kind: str, channel: str) -> bytes: ...

    @abstractmethod
    def code_digest(self, challenge_id: UUID, code: str) -> bytes: ...

    @abstractmethod
    def reserve_challenge(
        self, channel_hash: bytes, now: datetime, expires_at: datetime
    ) -> bool: ...

    @abstractmethod
    def deliver(self, kind: str, channel: str, challenge_id: UUID, code: str) -> None: ...


def unavailable() -> AppException:
    return AppException(
        "Rights authentication capability unavailable",
        code="RIGHTS_AUTH_UNAVAILABLE",
        status_code=503,
    )


def get_rights_auth_provider() -> RightsAuthProvider:
    """Production integration intentionally gated until a vetted adapter is installed."""
    raise unavailable()
