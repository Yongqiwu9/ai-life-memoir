"""Explicit static registry: unsupported providers never fall back to mock."""

from app.providers.base import AIProvider
from app.providers.mock import MockAIProvider

_FACTORIES = {"mock": MockAIProvider}


def get_provider(provider_id: str = "mock") -> AIProvider:
    if not isinstance(provider_id, str) or provider_id not in _FACTORIES:
        raise ValueError("Provider is unavailable")
    return _FACTORIES[provider_id]()
