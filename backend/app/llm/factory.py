from __future__ import annotations

import logging

from ..config import Settings
from .base import LLMProvider
from .mock import MockLLMProvider
from .openai_provider import OpenAICompatibleProvider

logger = logging.getLogger(__name__)


def create_provider(settings: Settings) -> LLMProvider:
    """Select a provider from configuration. Never raises for missing keys: an
    unconfigured provider reports ``is_configured=False`` and fails per-request."""
    if settings.llm_provider == "openai":
        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout=settings.llm_timeout_seconds,
        )
    if settings.llm_provider != "mock":
        logger.warning("Unknown LLM_PROVIDER %r; falling back to mock", settings.llm_provider)
    return MockLLMProvider()
