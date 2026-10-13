"""Explicit offline registry; unknown providers cannot silently select mock."""

from app.providers.memory_base import MemoryProvider
from app.providers.memory_mock import MockMemoryProvider

_FACTORIES = {"mock": MockMemoryProvider}


def get_memory_provider(provider_id: str = "mock") -> MemoryProvider:
    if type(provider_id) is not str or provider_id not in _FACTORIES:
        raise ValueError("Memory provider is unavailable")
    return _FACTORIES[provider_id]()
