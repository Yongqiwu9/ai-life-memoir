"""Offline provider abstraction; no network SDK is installed or imported."""

from app.providers.base import AIProvider
from app.providers.registry import get_provider

__all__ = ["AIProvider", "get_provider"]
