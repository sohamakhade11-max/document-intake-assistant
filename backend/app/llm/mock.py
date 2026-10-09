"""Deterministic mock provider.

It is a small rule-based extractor that speaks the *same JSON contract* as a real
model, so the whole app (validation, conflicts, corrections, documents) can be
demoed without an API key. It is intentionally simple and English-only; a real
model handles far more phrasing.

Failure fixtures can be triggered by starting a message with a tag:
  [mock:malformed]    -> non-JSON text
  [mock:invalid-type] -> valid JSON whose update has the wrong type (full_name = 123456)
  [mock:missing-keys] -> valid JSON missing required keys
  [mock:timeout]      -> raises LLMTimeoutError
  [mock:error]        -> raises LLMUpstreamError
"""
from __future__ import annotations

import json
import re
from typing import Any

from .base import (
    Clarification,
    FieldUpdate,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUpstreamError,
)

NAME = r"[A-Z][a-zA-Z'’-]+(?:\s+[A-Z][a-zA-Z'’-]+)*"
NAME_LIST = rf"{NAME}(?:\s*(?:,|&|\band\b)\s*(?:and\s+)?{NAME})*"
REL = (
    r"brother|sister|wife|husband|partner|spouse|friend|son|daughter|mother|father|cousin|uncle|aunt|"
    r"nephew|niece|solicitor|lawyer|accountant|grandson|granddaughter|fianc[eé]e?|girlfriend|boyfriend"
)

TAG = re.compile(r"^\s*\[mock:([\w-]+)\]")
CORRECTION = re.compile(
    r"(?i)\b(actually|change|instead|correction|i meant|rather|no longer|update|should not|shouldn't)\b|, not "
)
YES = re.compile(r"(?i)^\s*(yes|yeah|yep|yup|sure|correct|of course|y)\b")
NO = re.compile(r"(?i)^\s*(no|nope|nah|n)\b")
NONE = re.compile(r"(?i)^\s*(no|none|nope|nothing|nothing else|not really|n/a|no thanks|that'?s all)\b[\s.!,]*$")
KEEP = re.compile(r"(?i)\b(keep|stick with|leave it|as it was|original|that'?s right|no change)\b")
NO_CHILDREN = re.compile(
    r"(?i)\b(i (?:do not|don't|dont) have (?:any )?(?:children|kids)|i have no (?:children|kids)|"
    r"no (?:children|kids)|without children)"
)
CHILD_PHRASE = re.compile(r"(?i)\b((?:i (?:do )?have|i've got|my|our)\s+(?:\w+\s+)?(?:children|kids|child))\b")
CHILD_NAMES = re.compile(rf"(?i:children|kids|child)(?:\s+(?:are|is|named|called))?\s*[,:–—-]*\s*({NAME_LIST})")
NAME_INTRO = re.compile(rf"(?i:my (?:full )?name is|i am|i'm|call me)\s+({NAME})")
ADDRESS_INTRO = re.compile(
    r"(?i:my (?:home )?address is|i (?:live|reside) (?:at|in|on))\s+(?P<v>[^.\n]+?)"
    r"(?=\s+(?i:and|but)\s+(?i:i|my)\b|[.!?]?\s*$|\.\s)"
)
WORLDWIDE = re.compile(r"(?i)\b(worldwide|world-wide|all over the world|anywhere in the world|global(?:ly)?)\b")
NEGATION = re.compile(r"(?i)\b(not|n't|no|never|only|just)\b")
EXEC_REL_NAME = re.compile(rf"(?i:my)\s+(?P<rel>{REL})\s+(?P<name>{NAME})")
EXEC_NAME = re.compile(
    rf"(?i:executor(?:\s+to|\s+is|\s+will be|\s+should be)?|appoint(?:ing)?)\s+(?:(?i:my)\s+)?(?P<name>{NAME})"
)
REL_AFTER = re.compile(rf"(?i)(?:,\s*my|is my|she is my|he is my|they are my)\s+(?P<rel>{REL})\b")
GIFT = re.compile(
    r"(?i)\b(?:leave|give|bequeath|gift)\s+(?P<what>.+?)\s+to\s+(?P<who>(?:my\s+)?[\w'’ -]+?)\s*(?:[.,;!?]|$)"
)
BROAD = re.compile(
    r"(?i)\b(everything|all (?:of )?my (?:assets|estate|belongings|possessions|money)|my (?:whole )?estate)\b"
    r"|\b(divide|split|share)\b.*\bbetween\b"
)
CHILD_COUNT = re.compile(r"(?i)\b(?:i have|i've got|my|our)\s+(\d+|one|two|three|four|five|six)\s+(?:children|kids)")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
EXTRA_WISH = re.compile(r"(?i)\b(additional wish|i also want|i also wish|please also|one more thing)\b")


class MockLLMProvider:
    name = "mock"

    @property
    def is_configured(self) -> bool:
        return True

    async def process_message(self, request: LLMRequest) -> str:
        tag = TAG.match(request.user_message)
        if tag:
            return self._fixture(tag.group(1), request)
        return self._extract(request).model_dump_json()

    # ----- failure fixtures -----------------------------------------------
    def _fixture(self, kind: str, request: LLMRequest) -> str:
        if kind == "malformed":
            return 'Sure! Here is the JSON you asked for: {"acknowledgement": "ok", "updates": [ {'
        if kind == "invalid-type":
            return json.dumps(
                {
                    "acknowledgement": "Noted.",
                    "updates": [
                        {"field": "full_name", "value": 123456, "evidence": request.user_message.strip()}
                    ],
                }
            )
        if kind == "missing-keys":
            return json.dumps({"acknowledgement": "Noted."})
        if kind == "timeout":
            raise LLMTimeoutError("The AI service took too long to respond.")
        if kind == "error":
            raise LLMUpstreamError("The AI service returned an error.")
        return "{}"

    # ----- rule-based extraction ------------------------------------------
    def _extract(self, request: LLMRequest) -> LLMResponse:
        msg = request.user_message.strip()
        expected = request.expected_field
        state = request.state
        correction = bool(CORRECTION.search(msg))
        updates: list[FieldUpdate] = []
        clarifications: list[Clarification] = []
        notes: list[str] = []

        def add(field: str, value: Any, evidence: str, op: str = "set", corr: bool | None = None) -> None:
            updates.append(
                FieldUpdate(
                    field=field, value=value, operation=op, evidence=evidence.strip(),
                    is_correction=correction if corr is None else corr,
                )
            )

        if request.pending_conflicts and KEEP.search(msg):
            fields = [c["field"] for c in request.pending_conflicts]
            return LLMResponse(acknowledgement="No problem, I'll keep what I had.", updates=[], keep_existing_fields=fields)

        # --- name
        m = NAME_INTRO.search(msg)
        if m:
            add("full_name", m.group(1), m.group(0))
        elif expected == "full_name" and re.fullmatch(r"[A-Za-z'’. -]{2,60}", msg) and len(msg.split()) <= 5:
            add("full_name", msg.rstrip("."), msg)

        # --- address
        m = ADDRESS_INTRO.search(msg)
        if m:
            add("home_address", m.group("v").strip(), m.group(0))
        elif expected == "home_address" and (re.search(r"\d", msg) or "," in msg):
            add("home_address", msg.rstrip("."), msg)
        if re.search(r"(?i)\b(his|her|their) address\b", msg):
            notes.append("I don't record the executor's address.")

        # --- worldwide assets
        m = WORLDWIDE.search(msg)
        if m:
            add("covers_worldwide_assets", not NEGATION.search(msg), m.group(0))
        elif expected == "covers_worldwide_assets":
            if YES.match(msg):
                add("covers_worldwide_assets", True, msg)
            elif NO.match(msg):
                add("covers_worldwide_assets", False, msg)

        # --- children
        self._extract_children(msg, expected, add)
        count = CHILD_COUNT.search(msg)
        if count and not any(u.field == "children" for u in updates):
            n = int(count.group(1)) if count.group(1).isdigit() else NUMBER_WORDS[count.group(1).lower()]
            known = state.get("children") or []
            if n != len(known):
                clarifications.append(Clarification(
                    field="children",
                    question=f"You mentioned {n} children, but I have {len(known)} name(s) recorded. "
                             "What are all of their names?",
                ))

        # --- executor
        self._extract_executor(msg, expected, state, add)

        # --- gifts and wishes
        self._extract_gifts_and_wishes(msg, expected, add, clarifications, answered_other=bool(updates))

        ack = "Thanks." if updates else ""
        return LLMResponse(
            acknowledgement=" ".join(filter(None, [ack, *notes])),
            updates=updates,
            needs_clarification=clarifications,
        )

    def _extract_children(self, msg: str, expected: str | None, add) -> None:
        m = NO_CHILDREN.search(msg)
        if m:
            add("has_children", False, m.group(0))
            return
        phrase = CHILD_PHRASE.search(msg)
        names_match = CHILD_NAMES.search(msg)
        names: list[str] = []
        evidence = ""
        if names_match:
            names, evidence = _split_names(names_match.group(1)), names_match.group(1)
        elif expected == "children":
            found = re.search(NAME_LIST, msg)
            if found:
                names, evidence = _split_names(found.group(0)), found.group(0)
        elif expected == "has_children" and YES.match(msg):
            after_yes = re.search(NAME_LIST, msg)
            if after_yes:
                names, evidence = _split_names(after_yes.group(0)), after_yes.group(0)
            add("has_children", True, YES.match(msg).group(0))
        elif expected == "has_children" and NO.match(msg):
            add("has_children", False, msg)
            return
        if phrase:
            add("has_children", True, phrase.group(1))
        if names:
            add("children", names, evidence)

    def _extract_executor(self, msg: str, expected: str | None, state: dict[str, Any], add) -> None:
        in_context = bool(re.search(r"(?i)\b(executor|appoint)", msg)) or expected in (
            "executor.name",
            "executor.relationship",
        )
        if not in_context:
            return
        rel = name = None
        m = EXEC_REL_NAME.search(msg)
        if m:
            rel, name = m.group("rel"), m.group("name")
            add("executor.name", name, m.group("name"))
            add("executor.relationship", rel.lower(), m.group("rel"))
            return
        m = EXEC_NAME.search(msg)
        if m:
            name = m.group("name")
            add("executor.name", name, name)
        elif expected == "executor.name" and re.fullmatch(NAME, msg.rstrip(".")):
            name = msg.rstrip(".")
            add("executor.name", name, name)
        m = REL_AFTER.search(msg)
        if m:
            add("executor.relationship", m.group("rel").lower(), m.group("rel"))
        elif expected == "executor.relationship":
            found = re.search(rf"(?i)\b({REL})\b", msg)
            if found:
                add("executor.relationship", found.group(1).lower(), found.group(1))
            elif len(msg.split()) <= 3 and re.fullmatch(r"[A-Za-z' -]+", msg):
                add("executor.relationship", msg.lower(), msg)

    def _extract_gifts_and_wishes(
        self, msg: str, expected: str | None, add, clarifications: list[Clarification], answered_other: bool
    ) -> None:
        gift = GIFT.search(msg)
        if gift and not BROAD.search(gift.group("what")):
            add("specific_gifts", [{"description": gift.group("what").strip(), "recipient": gift.group("who").strip()}],
                gift.group(0).rstrip(".,;!? "), op="append")
            return
        if BROAD.search(msg):
            clarifications.append(
                Clarification(
                    field="specific_gifts",
                    question=(
                        "You mentioned how you'd like your estate shared. This tool only records specific gifts "
                        "(a particular item going to a named person). Would you like to add a specific gift, "
                        "or record this as an additional wish?"
                    ),
                )
            )
            return
        if answered_other:
            return  # the message answered something else; don't treat it as a reply to this question
        if expected == "specific_gifts":
            if NONE.match(msg):
                add("specific_gifts", [], msg)
            else:
                clarifications.append(
                    Clarification(field="specific_gifts", question="Which item should go to whom? For example: 'my watch to my nephew Tom'.")
                )
        elif expected == "additional_wishes":
            if NONE.match(msg):
                add("additional_wishes", [], msg)
            else:
                add("additional_wishes", [msg], msg, op="append")
        elif EXTRA_WISH.search(msg):
            add("additional_wishes", [msg], msg, op="append")


def _split_names(text: str) -> list[str]:
    parts = re.split(r"\s*(?:,|&|\band\b)\s*", text)
    return [p.strip() for p in parts if p.strip()]
