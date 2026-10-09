"""OpenAI-compatible chat-completions provider (works with any compatible base URL)."""
from __future__ import annotations

import logging

import httpx

from .base import (
    LLMConfigurationError,
    LLMOutputError,
    LLMRequest,
    LLMTimeoutError,
    LLMUpstreamError,
)
from .prompt import SYSTEM_PROMPT, build_user_content

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, api_key: str | None, model: str, base_url: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def process_message(self, request: LLMRequest) -> str:
        if not self._api_key:
            raise LLMConfigurationError(
                "The AI provider is not configured. Set OPENAI_API_KEY or use LLM_PROVIDER=mock."
            )
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_content(request)},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("LLM request timed out")
            raise LLMTimeoutError("The AI service took too long to respond.") from exc
        except httpx.HTTPError as exc:
            logger.warning("LLM request failed: %s", type(exc).__name__)
            raise LLMUpstreamError("The AI service could not be reached.") from exc

        if response.status_code != 200:
            logger.warning("LLM API returned HTTP %s", response.status_code)  # body not logged: may echo user data
            raise LLMUpstreamError("The AI service returned an error.")
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMOutputError("The AI service returned an unexpected response.") from exc
