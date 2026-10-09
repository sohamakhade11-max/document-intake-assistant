"""API request/response models (the public contract)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .document import DocumentView
from .models import ChatMessage, Conflict, FieldStatus, PersonalWishesState


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class StateView(BaseModel):
    state: PersonalWishesState
    field_statuses: dict[str, FieldStatus]
    missing_required: list[str]
    pending_conflicts: list[Conflict]
    is_complete: bool


class ConversationView(StateView):
    id: str
    messages: list[ChatMessage]
    document: DocumentView


class SendMessageResponse(BaseModel):
    assistant_message: str
    warnings: list[str]
    conversation: ConversationView


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_configured: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
