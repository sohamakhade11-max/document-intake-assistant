import json
from pathlib import Path

import pytest

from app.llm.base import LLMError, LLMRequest
from app.llm.mock import MockLLMProvider
from app.models import PersonalWishesState
from app.service import ConversationService
from app.store import InMemoryConversationStore

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "llm_responses.json").read_text())


def fixture_raw(name: str) -> str:
    item = FIXTURES[name]
    return item["raw_text"] if "raw_text" in item else json.dumps(item["raw"])


class ScriptedProvider:
    """Test double: returns queued raw strings (or raises queued errors)."""

    name = "scripted"
    is_configured = True

    def __init__(self, *responses: str | LLMError) -> None:
        self.responses = list(responses)
        self.requests: list[LLMRequest] = []

    async def process_message(self, request: LLMRequest) -> str:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def mock_service() -> ConversationService:
    return ConversationService(InMemoryConversationStore(), MockLLMProvider())


def make_service(provider) -> ConversationService:
    return ConversationService(InMemoryConversationStore(), provider)


def complete_state() -> PersonalWishesState:
    return PersonalWishesState.model_validate(
        {
            "full_name": "Jane Smith",
            "home_address": "12 Oak Road",
            "covers_worldwide_assets": True,
            "has_children": False,
            "executor": {"name": "James Smith", "relationship": "brother"},
        }
    )
