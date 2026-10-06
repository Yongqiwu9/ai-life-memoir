"""Test-only opaque vault: NOT encryption and never a runtime provider.

Random handles stand in for ciphertext; plaintext lives only in this test fixture's
memory. This deliberately does not claim production encryption/key management.
"""

import secrets
from uuid import UUID, uuid4

from app.core.rights_auth_provider import RightsAuthProvider, keyed_digest
from app.schemas.privacy_policy import PolicyCapabilities, PolicyNotices, PolicyParameters
from app.schemas.rights_auth import RightsAuthConfiguration


class TestOnlyRightsProvider(RightsAuthProvider):
    __test__ = False

    def __init__(self):
        self.configuration = RightsAuthConfiguration.model_validate(
            {
                "challenge_ttl": {"seconds": 60},
                "token_ttl": {"seconds": 180},
                "attempt_limit": 3,
            }
        )
        self._lookup_secret = secrets.token_bytes(32)
        self._code_pepper = secrets.token_bytes(32)
        self._vault = {}
        self.deliveries = {}
        self.available = True
        self.delivery_fails = False
        self.rate_allowed = True

    def ready(self):
        return self.available

    def encrypt(self, value):
        handle = secrets.token_bytes(48)
        self._vault[handle] = value
        return handle

    def decrypt(self, value):
        return self._vault[value]

    def lookup(self, kind, channel):
        return keyed_digest(self._lookup_secret, b"contact:" + kind.encode(), channel.encode())

    def code_digest(self, challenge_id: UUID, code):
        return keyed_digest(self._code_pepper, b"rights-otp:" + challenge_id.bytes, code.encode())

    def reserve_challenge(self, channel_hash, now, expires_at):
        return self.rate_allowed

    def deliver(self, kind, channel, challenge_id, code):
        if self.delivery_fails:
            raise RuntimeError("test-only delivery failure")
        self.deliveries[challenge_id] = code


def policy_documents():
    """All values and notices here are synthetic fixtures, never production defaults."""
    parameters = {
        name: {"seconds": 120}
        for name in PolicyParameters.model_fields
        if name != "sanitization_retry_limit"
    }
    parameters["sanitization_retry_limit"] = 2
    parameters["sanitization_review_window"] = {"seconds": 60}
    notices = {name: "Synthetic test notice only" for name in PolicyNotices.model_fields}
    capabilities = {
        name: {"verified": True, "evidence_ref": str(uuid4())}
        for name in PolicyCapabilities.model_fields
    }
    return parameters, notices, capabilities
