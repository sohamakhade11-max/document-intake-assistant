"""Domain models: the explicit structured state that is the source of truth.

Conventions for "unknown" vs "known":
  * scalar fields: ``None`` = unknown / not yet provided.
  * booleans: ``False`` is an explicit answer ("no"), distinct from ``None``.
  * ``children``: only meaningful when ``has_children`` is true.
  * ``specific_gifts`` / ``additional_wishes``: ``None`` = not yet asked/answered,
    ``[]`` = the user explicitly said there are none.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text50 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Text300 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Gift(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Text300
    recipient: Text100 | None = None


class Executor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text100 | None = None
    relationship: Text50 | None = None


class PersonalWishesState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Text100 | None = None
    home_address: Text300 | None = None
    covers_worldwide_assets: bool | None = None
    has_children: bool | None = None
    children: list[Text100] = Field(default_factory=list, max_length=20)
    executor: Executor = Field(default_factory=Executor)
    specific_gifts: list[Gift] | None = Field(default=None, max_length=20)
    additional_wishes: list[Text500] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def _children_consistent_with_flag(self) -> "PersonalWishesState":
        if self.has_children is False and self.children:
            raise ValueError("children must be empty when has_children is false")
        return self


# Fields the LLM may propose updates for (dotted path for nested values).
FIELD_NAMES: tuple[str, ...] = (
    "full_name",
    "home_address",
    "covers_worldwide_assets",
    "has_children",
    "children",
    "executor.name",
    "executor.relationship",
    "specific_gifts",
    "additional_wishes",
)

LIST_FIELDS = frozenset({"children", "specific_gifts", "additional_wishes"})

FieldStatus = Literal["unknown", "confirmed", "incomplete", "needs_clarification"]


class Conflict(BaseModel):
    """A proposed change that contradicts known state and awaits the user's decision."""

    field: str
    question: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Conversation(BaseModel):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: PersonalWishesState = Field(default_factory=PersonalWishesState)
    messages: list[ChatMessage] = Field(default_factory=list)
    pending_conflicts: list[Conflict] = Field(default_factory=list)
    expected_field: str | None = None  # the field the last question was about
