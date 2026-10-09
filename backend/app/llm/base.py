"""LLM contract: request/response models, errors, and the provider interface.

Providers return the model's *raw text*. Parsing and validation happen outside the
provider (parsing.py, state_updates.py), so every provider -- real, mock, or test
double -- is subject to exactly the same checks.
"""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMError(Exception):
    """Base class for failures talking to a model. Messages are safe to show users."""


class LLMConfigurationError(LLMError):
    """Provider selected but not usable (e.g. missing API key)."""


class LLMTimeoutError(LLMError):
    """The model did not answer in time."""


class LLMUpstreamError(LLMError):
    """The model API returned an error or was unreachable."""


class LLMOutputError(LLMError):
    """The model answered, but not in the required structure."""


# ----- Request ---------------------------------------------------------------

class HistoryItem(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    """Everything the model is allowed to see for one turn."""

    user_message: str
    state: dict[str, Any]  # current structured state (source of truth)
    expected_field: str | None = None  # field the assistant's last question was about
    pending_conflicts: list[dict[str, str]] = Field(default_factory=list)
    recent_messages: list[HistoryItem] = Field(default_factory=list)  # context only, short


# ----- Response --------------------------------------------------------------

class FieldUpdate(BaseModel):
    """One proposed change. Deliberately lenient in types: strict checks happen in
    state_updates.py so one bad item cannot invalidate the others."""

    model_config = ConfigDict(extra="ignore")
    field: str
    value: Any
    operation: str = "set"  # "set" | "append" (list fields only)
    is_correction: bool = False  # user is deliberately changing an earlier answer
    evidence: str = ""  # exact words from the user's message supporting this value


class Clarification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    field: str = ""
    question: str


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    acknowledgement: str  # short, neutral; the backend appends the next question
    updates: list[FieldUpdate]
    needs_clarification: list[Clarification] = Field(default_factory=list)
    keep_existing_fields: list[str] = Field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    @property
    def is_configured(self) -> bool: ...

    async def process_message(self, request: LLMRequest) -> str:
        """Return the model's raw JSON text for this turn. May raise LLMError."""
        ...
