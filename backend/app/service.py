"""Conversation service: orchestrates one turn.

  user message -> LLM (propose) -> parse -> validate/apply (state) -> deterministic
  next question -> save.  The model never decides completeness or writes state.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .flow import FINISHED_MESSAGE, next_field, question_for
from .llm.base import HistoryItem, LLMOutputError, LLMProvider, LLMRequest, LLMResponse
from .llm.parsing import parse_llm_output
from .models import ChatMessage, Conflict, Conversation
from .state_updates import apply_updates
from .store import ConversationStore

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 2000
MAX_ACK_CHARS = 300
HISTORY_WINDOW = 6

FALLBACK_NOTICE = "Sorry, I had trouble understanding that, so I haven't changed anything. Could you rephrase?"
INTRO = (
    "Hello! I'll help you draft a fictional Personal Wishes Document. "
    "This is a demo and not legal advice. "
)


class ConversationNotFound(Exception):
    pass


class InvalidMessage(Exception):
    pass


@dataclass
class TurnResult:
    conversation: Conversation
    assistant_message: str
    warnings: list[str]


class ConversationService:
    def __init__(self, store: ConversationStore, provider: LLMProvider) -> None:
        self._store = store
        self._provider = provider
        self._locks: dict[str, asyncio.Lock] = {}

    async def create(self) -> Conversation:
        conversation = await self._store.create()
        field = next_field(conversation.state)
        conversation.expected_field = field
        conversation.messages.append(
            ChatMessage(role="assistant", content=INTRO + question_for(field, conversation.state))
        )
        await self._store.save(conversation)
        return conversation

    async def get(self, conversation_id: str) -> Conversation:
        conversation = await self._store.get(conversation_id)
        if conversation is None:
            raise ConversationNotFound(conversation_id)
        return conversation

    async def send_message(self, conversation_id: str, text: str) -> TurnResult:
        message = (text or "").strip()
        if not message:
            raise InvalidMessage("Please enter a message.")
        if len(message) > MAX_MESSAGE_CHARS:
            raise InvalidMessage(f"Messages are limited to {MAX_MESSAGE_CHARS} characters.")

        lock = self._locks.setdefault(conversation_id, asyncio.Lock())
        async with lock:
            conversation = await self.get(conversation_id)  # a deep copy: safe to mutate
            request = LLMRequest(
                user_message=message,
                state=conversation.state.model_dump(),
                expected_field=conversation.expected_field,
                pending_conflicts=[c.model_dump() for c in conversation.pending_conflicts],
                recent_messages=[HistoryItem(**m.model_dump()) for m in conversation.messages[-HISTORY_WINDOW:]],
            )

            # LLMError subclasses other than LLMOutputError propagate: nothing is saved.
            warnings: list[str] = []
            llm: LLMResponse | None = None
            try:
                llm = parse_llm_output(await self._provider.process_message(request))
            except LLMOutputError:
                warnings.append("The AI response could not be validated; your information was not changed.")

            conversation.messages.append(ChatMessage(role="user", content=message))
            if llm is None:
                reply = FALLBACK_NOTICE + " " + self._current_question(conversation)
            else:
                reply = self._apply_turn(conversation, llm, message, warnings)
            conversation.messages.append(ChatMessage(role="assistant", content=reply))
            await self._store.save(conversation)
            logger.info("turn handled: conversation=%s warnings=%d", conversation_id, len(warnings))
            return TurnResult(conversation, reply, warnings)

    # ----- helpers -----------------------------------------------------------
    def _apply_turn(self, conversation: Conversation, llm: LLMResponse, message: str, warnings: list[str]) -> str:
        result = apply_updates(
            conversation.state, llm.updates, message, conversation.pending_conflicts, llm.keep_existing_fields
        )
        conversation.state = result.state
        for rejected in result.rejected:
            logger.info("update rejected: field=%s reason=%s", rejected.field, rejected.reason)
            warnings.append(f"Ignored an update to '{rejected.field}': {rejected.reason}.")

        # Conflicts: drop those resolved this turn (applied or kept), add newly detected ones.
        closed = set(result.resolved) | set(result.applied)
        remaining = [c for c in conversation.pending_conflicts if c.field not in closed]
        by_field = {c.field: c for c in remaining}
        by_field.update({c.field: c for c in result.conflicts})
        conversation.pending_conflicts = list(by_field.values())

        ack = (llm.acknowledgement or "").strip()[:MAX_ACK_CHARS]
        if not ack and (result.applied or result.resolved):
            ack = "Got it."
        question = self._current_question(conversation, llm)
        return f"{ack} {question}".strip()

    def _current_question(self, conversation: Conversation, llm: LLMResponse | None = None) -> str:
        """Priority: unresolved contradiction > model clarification > next missing field."""
        if conversation.pending_conflicts:
            conflict: Conflict = conversation.pending_conflicts[0]
            conversation.expected_field = conflict.field
            return conflict.question
        if llm is not None:
            for clarification in llm.needs_clarification:
                question = clarification.question.strip()[:MAX_ACK_CHARS * 2]
                if question:
                    conversation.expected_field = clarification.field or None
                    return question
        field = next_field(conversation.state)
        conversation.expected_field = field
        return question_for(field, conversation.state) if field else FINISHED_MESSAGE
