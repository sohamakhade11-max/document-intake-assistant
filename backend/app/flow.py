"""Deterministic interview logic: completeness, field statuses, next question.

Nothing here depends on the LLM. The model proposes values; this module decides
what is still missing and what to ask next.
"""
from __future__ import annotations

from typing import Any

from .models import FIELD_NAMES, Conflict, FieldStatus, PersonalWishesState

# Required fields in the order we ask about them.
REQUIRED_ORDER: tuple[str, ...] = (
    "full_name",
    "home_address",
    "covers_worldwide_assets",
    "has_children",
    "children",
    "executor.name",
    "executor.relationship",
)
OPTIONAL_ORDER: tuple[str, ...] = ("specific_gifts", "additional_wishes")


def get_field(state: PersonalWishesState, field: str) -> Any:
    if field == "executor.name":
        return state.executor.name
    if field == "executor.relationship":
        return state.executor.relationship
    return getattr(state, field)


def is_known(field: str, value: Any) -> bool:
    """children == [] is the default, not an answer; for other fields only None is unknown."""
    if field == "children":
        return bool(value)
    return value is not None


def _is_missing(state: PersonalWishesState, field: str) -> bool:
    if field == "children":
        return state.has_children is True and not state.children
    return get_field(state, field) is None


def missing_required(state: PersonalWishesState) -> list[str]:
    """Required fields still unknown. ``children`` only counts when has_children is true."""
    return [f for f in REQUIRED_ORDER if _is_missing(state, f)]


def is_complete(state: PersonalWishesState, conflicts: list[Conflict]) -> bool:
    """A draft is final-ready when all required data is present and nothing is contested."""
    return not missing_required(state) and not conflicts


def field_statuses(state: PersonalWishesState, conflicts: list[Conflict]) -> dict[str, FieldStatus]:
    contested = {c.field for c in conflicts}
    statuses: dict[str, FieldStatus] = {}
    for field in FIELD_NAMES:
        if field in contested:
            statuses[field] = "needs_clarification"
        elif field == "children":
            if state.has_children is True and not state.children:
                statuses[field] = "incomplete"
            elif state.has_children is None:
                statuses[field] = "unknown"
            else:
                statuses[field] = "confirmed"
        elif get_field(state, field) is None:
            statuses[field] = "unknown"
        else:
            statuses[field] = "confirmed"
    return statuses


def question_for(field: str, state: PersonalWishesState) -> str:
    if field == "executor.relationship":
        return f"What is {state.executor.name or 'your executor'}'s relationship to you?"
    return {
        "full_name": "What is your full name?",
        "home_address": "What is your home address?",
        "covers_worldwide_assets": "Should this document cover your assets worldwide? (yes or no)",
        "has_children": "Do you have any children?",
        "children": "What are your children's names?",
        "executor.name": "Who would you like to appoint as your executor?",
        "specific_gifts": "Would you like to leave any specific gifts to anyone? If not, just say no.",
        "additional_wishes": "Do you have any additional wishes you'd like included? If not, just say no.",
    }[field]


def next_field(state: PersonalWishesState) -> str | None:
    """First required field missing, then unanswered optional fields, then None (finished)."""
    missing = missing_required(state)
    if missing:
        return missing[0]
    for field in OPTIONAL_ORDER:
        if get_field(state, field) is None:
            return field
    return None


FINISHED_MESSAGE = (
    "That's everything I need. Your draft is shown in the preview — "
    "tell me if anything needs changing."
)
