"""HTTP layer: routes, view-building and error mapping. No business logic here."""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .document import DocumentView, build_document
from .flow import field_statuses, is_complete, missing_required
from .llm.base import LLMConfigurationError, LLMError, LLMProvider, LLMTimeoutError
from .models import Conversation
from .schemas import (
    ConversationView,
    HealthResponse,
    SendMessageRequest,
    SendMessageResponse,
    StateView,
)
from .service import ConversationNotFound, ConversationService, InvalidMessage

logger = logging.getLogger(__name__)


def _state_view(c: Conversation) -> StateView:
    return StateView(
        state=c.state,
        field_statuses=field_statuses(c.state, c.pending_conflicts),
        missing_required=missing_required(c.state),
        pending_conflicts=c.pending_conflicts,
        is_complete=is_complete(c.state, c.pending_conflicts),
    )


def _document(c: Conversation) -> DocumentView:
    return build_document(c.state, is_complete(c.state, c.pending_conflicts))


def _view(c: Conversation) -> ConversationView:
    return ConversationView(id=c.id, messages=c.messages, document=_document(c), **_state_view(c).model_dump())


def build_router(service: ConversationService, provider: LLMProvider) -> APIRouter:
    router = APIRouter(prefix="/api")

    async def load(conversation_id: str) -> Conversation:
        return await service.get(conversation_id)

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", llm_provider=provider.name, llm_configured=provider.is_configured)

    @router.post("/conversations", response_model=ConversationView, status_code=201)
    async def create_conversation() -> ConversationView:
        return _view(await service.create())

    @router.get("/conversations/{conversation_id}", response_model=ConversationView)
    async def get_conversation(conversation_id: str) -> ConversationView:
        return _view(await load(conversation_id))

    @router.get("/conversations/{conversation_id}/state", response_model=StateView)
    async def get_state(conversation_id: str) -> StateView:
        return _state_view(await load(conversation_id))

    @router.get("/conversations/{conversation_id}/document", response_model=DocumentView)
    async def get_document(conversation_id: str) -> DocumentView:
        return _document(await load(conversation_id))

    @router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
    async def send_message(conversation_id: str, body: SendMessageRequest) -> SendMessageResponse:
        result = await service.send_message(conversation_id, body.message)
        return SendMessageResponse(
            assistant_message=result.assistant_message,
            warnings=result.warnings,
            conversation=_view(result.conversation),
        )

    return router


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ConversationNotFound)
    async def _not_found(_: Request, __: ConversationNotFound) -> JSONResponse:
        return _error(404, "conversation_not_found", "That conversation was not found. Please start a new one.")

    @app.exception_handler(InvalidMessage)
    async def _invalid(_: Request, exc: InvalidMessage) -> JSONResponse:
        return _error(422, "invalid_message", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error(422, "invalid_request", "The request was invalid. Messages must be 1–2000 characters.")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return _error(exc.status_code, code, "Request could not be completed.")

    @app.exception_handler(LLMError)
    async def _llm(_: Request, exc: LLMError) -> JSONResponse:
        logger.warning("LLM failure: %s", type(exc).__name__)
        if isinstance(exc, LLMConfigurationError):
            return _error(503, "llm_not_configured", str(exc))
        if isinstance(exc, LLMTimeoutError):
            return _error(504, "llm_timeout", "The AI service took too long to respond. Please try again.")
        return _error(502, "llm_unavailable", "The AI service is unavailable right now. Please try again.")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong. Please try again.")
