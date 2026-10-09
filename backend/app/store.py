"""Conversation storage behind a small interface (swap for Redis/Postgres later)."""
from __future__ import annotations

import asyncio
import uuid
from typing import Protocol

from .models import Conversation


class ConversationStore(Protocol):
    async def create(self) -> Conversation: ...
    async def get(self, conversation_id: str) -> Conversation | None: ...
    async def save(self, conversation: Conversation) -> None: ...


class InMemoryConversationStore:
    """Process-local, non-persistent. Returns deep copies so callers can't mutate stored state
    by accident; a turn only takes effect when ``save`` is called."""

    def __init__(self, max_conversations: int = 1000) -> None:
        self._items: dict[str, Conversation] = {}
        self._max = max_conversations
        self._lock = asyncio.Lock()

    async def create(self) -> Conversation:
        async with self._lock:
            if len(self._items) >= self._max:
                self._items.pop(next(iter(self._items)))  # evict oldest
            conversation = Conversation(id=uuid.uuid4().hex)
            self._items[conversation.id] = conversation.model_copy(deep=True)
            return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        item = self._items.get(conversation_id)
        return item.model_copy(deep=True) if item else None

    async def save(self, conversation: Conversation) -> None:
        self._items[conversation.id] = conversation.model_copy(deep=True)
