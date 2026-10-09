"""Validate LLM-proposed updates and apply only the valid ones.

The LLM never writes to state. It proposes ``FieldUpdate`` items; each is checked
independently and applied to a *copy* of the state. Rejected updates are reported
and have no effect. Updates that contradict known values (without the model
flagging an intentional correction) become ``Conflict`` items instead of silently
overwriting.
"""
from __future__ import annotations

import logging
import re
import copy
from dataclasses import dataclass, field as dc_field
from typing import Any

from pydantic import StrictBool, TypeAdapter, ValidationError

from .flow import get_field, is_known
from .llm.base import FieldUpdate
from .models import (
    FIELD_NAMES,
    LIST_FIELDS,
    Conflict,
    Gift,
    PersonalWishesState,
    Text50,
    Text100,
    Text300,
    Text500,
)

logger = logging.getLogger(__name__)

# Per-field value validators. StrictBool means the string "yes" is NOT a boolean.
_ADAPTERS: dict[str, TypeAdapter] = {
    "full_name": TypeAdapter(Text100),
    "home_address": TypeAdapter(Text300),
    "covers_worldwide_assets": TypeAdapter(StrictBool),
    "has_children": TypeAdapter(StrictBool),
    "children": TypeAdapter(list[Text100]),
    "executor.name": TypeAdapter(Text100),
    "executor.relationship": TypeAdapter(Text50),
    "specific_gifts": TypeAdapter(list[Gift]),
    "additional_wishes": TypeAdapter(list[Text500]),
}


@dataclass
class RejectedUpdate:
    field: str
    reason: str


@dataclass
class ApplyResult:
    state: PersonalWishesState
    applied: list[str] = dc_field(default_factory=list)
    rejected: list[RejectedUpdate] = dc_field(default_factory=list)
    conflicts: list[Conflict] = dc_field(default_factory=list)
    resolved: list[str] = dc_field(default_factory=list)  # pending conflicts closed this turn


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip().lower()


def _same(a: Any, b: Any) -> bool:
    def canon(v: Any) -> Any:
        if isinstance(v, str):
            return _norm(v)
        if isinstance(v, list):
            return [canon(x) for x in v]
        if isinstance(v, Gift):
            return (_norm(v.description), _norm(v.recipient or ""))
        return v

    return canon(a) == canon(b)


def describe(field: str, value: Any) -> str:
    """Human phrase used in conflict questions."""
    if field == "covers_worldwide_assets":
        return "this document covers worldwide assets" if value else "this document does not cover worldwide assets"
    if field == "has_children":
        return "you have children" if value else "you have no children"
    if field == "children":
        return f"your children are {', '.join(value)}"
    if field == "specific_gifts":
        if not value:
            return "you have no specific gifts"
        return "your specific gifts are " + "; ".join(
            f"{g.description}" + (f" to {g.recipient}" if g.recipient else "") for g in value
        )
    if field == "additional_wishes":
        return "your additional wishes are: " + "; ".join(value) if value else "you have no additional wishes"
    labels = {
        "full_name": "your full name is",
        "home_address": "your home address is",
        "executor.name": "your executor is",
        "executor.relationship": "your executor's relationship to you is",
    }
    return f"{labels[field]} {value}"


def _conflict(field: str, current: Any, proposed: Any) -> Conflict:
    return Conflict(
        field=field,
        question=(
            f"Earlier I recorded that {describe(field, current)}, but your latest message "
            f"suggests that {describe(field, proposed)}. Which is correct?"
        ),
    )


def _validate_value(field: str, value: Any, operation: str) -> Any:
    if operation == "append" and field in LIST_FIELDS and not isinstance(value, list):
        value = [value]
    return _ADAPTERS[field].validate_python(value)


def _set(data: dict[str, Any], field: str, value: Any) -> None:
    if field.startswith("executor."):
        data["executor"][field.split(".", 1)[1]] = value
    else:
        data[field] = value


def apply_updates(
    state: PersonalWishesState,
    updates: list[FieldUpdate],
    user_message: str,
    pending: list[Conflict],
    keep_existing: list[str],
) -> ApplyResult:
    pending_fields = {c.field for c in pending}
    message_norm = _norm(user_message)
    result = ApplyResult(state=state)
    working = state.model_dump()
    conflicts: dict[str, Conflict] = {}

    def current_state() -> PersonalWishesState:
        return PersonalWishesState.model_validate(working)

    for update in updates:
        name = update.field
        if name not in FIELD_NAMES:
            result.rejected.append(RejectedUpdate(name, "unknown field"))
            continue
        if update.operation not in ("set", "append") or (update.operation == "append" and name not in LIST_FIELDS):
            result.rejected.append(RejectedUpdate(name, "invalid operation"))
            continue
        evidence = _norm(update.evidence)
        if not evidence or evidence not in message_norm:
            # Guards against invented facts: every update must quote the user's message.
            result.rejected.append(RejectedUpdate(name, "no supporting text in the user's message"))
            continue
        try:
            value = _validate_value(name, update.value, update.operation)
        except (ValidationError, ValueError, TypeError):
            result.rejected.append(RejectedUpdate(name, "invalid value"))
            continue

        now = current_state()
        existing = get_field(now, name)
        if update.operation == "append":
            merged = list(existing or [])
            for item in value:
                if not any(_same(item, m) for m in merged):
                    merged.append(item)
            value = merged

        # The user answering a pending question counts as an intentional correction.
        is_correction = update.is_correction or name in pending_fields

        if is_known(name, existing) and _same(existing, value):
            if name in pending_fields:
                result.resolved.append(name)  # user confirmed the existing value
            continue
        if is_known(name, existing) and not is_correction:
            conflicts[name] = _conflict(name, existing, value)
            continue

        # Cross-field consistency between has_children and children.
        child_authority = is_correction or "has_children" in pending_fields
        if name == "children" and value and now.has_children is False and not child_authority:
            conflicts["has_children"] = _conflict("has_children", False, True)
            continue
        if name == "has_children" and value is False and now.children and not is_correction:
            conflicts[name] = _conflict(name, True, False)
            continue

        snapshot = copy.deepcopy(working)
        _set(working, name, _dump(value))
        if name == "children" and value:
            working["has_children"] = True
        if name == "has_children" and value is False:
            working["children"] = []
        if name == "executor.name" and is_known(name, existing):
            # A different person: the old relationship no longer applies. Keep it only if
            # this same message also supplies one.
            if not any(u.field == "executor.relationship" for u in updates):
                working["executor"]["relationship"] = None
        try:
            current_state()
        except ValidationError:
            working = snapshot
            result.rejected.append(RejectedUpdate(name, "inconsistent with existing information"))
            continue
        result.applied.append(name)
        if name == "children" and value:
            result.applied.append("has_children")

    for field_name in keep_existing:
        if field_name in pending_fields:
            result.resolved.append(field_name)

    result.state = current_state()
    result.conflicts = list(conflicts.values())
    return result


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [v.model_dump() if hasattr(v, "model_dump") else v for v in value]
    return value
