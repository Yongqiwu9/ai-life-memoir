"""Injected synthetic integrity capability; production key provisioning is unavailable."""

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from app.core.exceptions import AppException
from app.schemas.memory_workflow import RevisionPayload

CONTENT_SCHEME = "memory-content.v1"
COMMAND_SCHEME = "memory-command.v1"
CONTROL_SCHEME = "control-sha256.v1"


def _unavailable():
    return AppException(
        "Memory integrity unavailable", code="MEMORY_INTEGRITY_UNAVAILABLE", status_code=503
    )


def _normalize(value):
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, UUID):
        return str(value)
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("Canonical object keys must be strings")
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    raise ValueError("Unsupported canonical value")


def canonical_bytes(value) -> bytes:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class Fingerprint:
    digest: bytes
    scheme: str
    key_id: str | None


class MemoryKeyProvider(Protocol):
    def current_key(self) -> tuple[str, bytes]: ...

    def get_key(self, key_id: str) -> bytes | None: ...


class SyntheticKeyProvider:
    """Explicit fixture injection; does not load settings, files or environment keys."""

    def __init__(self, keys: Mapping[str, bytes], current_key_id: str):
        self.keys = dict(keys)
        self.current_key_id = current_key_id

    def current_key(self) -> tuple[str, bytes]:
        return self.current_key_id, self.keys.get(self.current_key_id)

    def get_key(self, key_id: str) -> bytes | None:
        return self.keys.get(key_id)


class MemoryIntegrity:
    def __init__(self, key_provider: MemoryKeyProvider | None = None):
        self.key_provider = key_provider

    def _key(self, key_id: str | None) -> tuple[str, bytes]:
        if self.key_provider is None:
            raise _unavailable()
        try:
            if key_id is None:
                identifier, key = self.key_provider.current_key()
            else:
                identifier, key = key_id, self.key_provider.get_key(key_id)
        except Exception:  # noqa: BLE001 -- key-provider failures must not disclose details
            raise _unavailable() from None
        if type(identifier) is not str or not identifier or type(key) is not bytes or len(key) < 32:
            raise _unavailable()
        return identifier, key

    def require_available(self, key_id: str | None = None) -> None:
        """Check capability before any private body query; old revisions use their old key."""
        self._key(key_id)

    def fingerprint(
        self,
        *,
        actor_user_id: UUID,
        operation: str,
        idempotency_key: UUID,
        target_scope: Mapping,
        expected_versions: Mapping,
        payload=None,
        scheme: str | None = None,
        key_id: str | None = None,
    ) -> Fingerprint:
        sensitive = payload is not None
        expected_scheme = COMMAND_SCHEME if sensitive else CONTROL_SCHEME
        if scheme is not None and scheme != expected_scheme:
            raise _unavailable()
        if sensitive and scheme is not None and (type(key_id) is not str or not key_id):
            # An explicit stored scheme denotes replay; missing historical key is not a new key.
            raise _unavailable()
        envelope = {
            "actor_user_id": actor_user_id,
            "operation": operation,
            "idempotency_key": idempotency_key,
            "target_scope": target_scope,
            "expected_versions": expected_versions,
            "payload": payload,
        }
        message = expected_scheme.encode("ascii") + b"\x00" + canonical_bytes(envelope)
        if not sensitive:
            if key_id is not None:
                raise _unavailable()
            return Fingerprint(hashlib.sha256(message).digest(), CONTROL_SCHEME, None)
        identifier, key = self._key(key_id)
        return Fingerprint(hmac.digest(key, message, "sha256"), COMMAND_SCHEME, identifier)

    def content_digest(
        self,
        payload: RevisionPayload | Mapping,
        *,
        source_scope_id: UUID,
        family_member_id: UUID,
        derivation_profile: str,
        required_purposes,
        key_id: str | None = None,
    ) -> Fingerprint:
        validated = RevisionPayload.model_validate(payload)
        envelope = {
            "payload": validated,
            "source_scope_id": source_scope_id,
            "family_member_id": family_member_id,
            "derivation_profile": derivation_profile,
            "required_purposes": sorted(set(required_purposes)),
        }
        identifier, key = self._key(key_id)
        message = CONTENT_SCHEME.encode("ascii") + b"\x00" + canonical_bytes(envelope)
        return Fingerprint(hmac.digest(key, message, "sha256"), CONTENT_SCHEME, identifier)

    def verify_content(
        self,
        payload: RevisionPayload | Mapping,
        *,
        source_scope_id: UUID,
        family_member_id: UUID,
        derivation_profile: str,
        required_purposes,
        digest: bytes,
        scheme: str,
        key_id: str,
    ) -> None:
        if scheme != CONTENT_SCHEME or type(digest) is not bytes or len(digest) != 32:
            raise AppException(
                "Invalid content integrity", code="CONTENT_RESTRICTED", status_code=403
            )
        if type(key_id) is not str or not key_id:
            raise _unavailable()
        actual = self.content_digest(
            payload,
            source_scope_id=source_scope_id,
            family_member_id=family_member_id,
            derivation_profile=derivation_profile,
            required_purposes=required_purposes,
            key_id=key_id,
        )
        if not hmac.compare_digest(actual.digest, digest):
            raise AppException(
                "Invalid content integrity", code="CONTENT_RESTRICTED", status_code=403
            )


def get_memory_integrity() -> MemoryIntegrity:
    return MemoryIntegrity()
