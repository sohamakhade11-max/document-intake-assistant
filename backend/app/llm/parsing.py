"""Parse raw model text into a validated LLMResponse."""
from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from .base import LLMOutputError, LLMResponse

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def parse_llm_output(raw: str) -> LLMResponse:
    text = (raw or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("LLM output is not valid JSON (%s)", exc.msg)
        raise LLMOutputError("The model response was not valid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMOutputError("The model response was not a JSON object.")
    try:
        return LLMResponse.model_validate(data)
    except ValidationError as exc:
        locations = [".".join(str(p) for p in e["loc"]) for e in exc.errors()]
        logger.warning("LLM output failed schema validation at: %s", locations)
        raise LLMOutputError("The model response did not match the required structure.") from exc
