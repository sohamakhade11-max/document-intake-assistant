"""Document generation: a pure function from structured state to a draft document.

It never sees conversation history, so it cannot include anything the user did
not confirm. Unknown required values are shown as an explicit placeholder.
"""
from __future__ import annotations

from pydantic import BaseModel

from .models import PersonalWishesState

TITLE = "PERSONAL WISHES DOCUMENT"
DISCLAIMER = "Fictional — Not Legal Advice"
PLACEHOLDER = "[Not yet provided]"


class DocumentSection(BaseModel):
    heading: str
    lines: list[str]


class DocumentView(BaseModel):
    title: str
    disclaimer: str
    status: str  # "complete" | "draft"
    sections: list[DocumentSection]
    text: str  # plain-text rendering of the same content


def _value(v: str | None) -> str:
    return v if v else PLACEHOLDER


def build_document(state: PersonalWishesState, is_complete: bool) -> DocumentView:
    sections: list[DocumentSection] = []

    sections.append(DocumentSection(
        heading="1. Personal Information",
        lines=[f"Full name: {_value(state.full_name)}", f"Home address: {_value(state.home_address)}"],
    ))

    if state.covers_worldwide_assets is None:
        scope = PLACEHOLDER
    elif state.covers_worldwide_assets:
        scope = "This document covers assets worldwide."
    else:
        scope = "This document does not cover assets worldwide."
    sections.append(DocumentSection(heading="2. Scope", lines=[scope]))

    if state.has_children is None:
        children = [PLACEHOLDER]
    elif state.has_children is False:
        children = ["I have no children."]
    elif state.children:
        children = [f"I have {len(state.children)} child(ren):"] + [f"- {c}" for c in state.children]
    else:
        children = ["I have children. Names: " + PLACEHOLDER]
    sections.append(DocumentSection(heading="3. Children", lines=children))

    sections.append(DocumentSection(
        heading="4. Executor",
        lines=[f"Name: {_value(state.executor.name)}", f"Relationship to me: {_value(state.executor.relationship)}"],
    ))

    if state.specific_gifts is None:
        gifts = [PLACEHOLDER]
    elif not state.specific_gifts:
        gifts = ["No specific gifts were specified."]
    else:
        gifts = [
            f"- {g.description} — to {g.recipient}" if g.recipient else f"- {g.description} — recipient not specified"
            for g in state.specific_gifts
        ]
    sections.append(DocumentSection(heading="5. Specific Gifts", lines=gifts))

    if state.additional_wishes is None:
        wishes = [PLACEHOLDER]
    elif not state.additional_wishes:
        wishes = ["No additional wishes were specified."]
    else:
        wishes = [f"- {w}" for w in state.additional_wishes]
    sections.append(DocumentSection(heading="6. Additional Wishes", lines=wishes))

    status = "complete" if is_complete else "draft"
    header = [TITLE, DISCLAIMER, "Status: " + ("complete draft" if is_complete else "INCOMPLETE DRAFT"), ""]
    body: list[str] = []
    for s in sections:
        body += [s.heading, *s.lines, ""]
    text = "\n".join(header + body + [DISCLAIMER + ". For demonstration only."])
    return DocumentView(title=TITLE, disclaimer=DISCLAIMER, status=status, sections=sections, text=text)
