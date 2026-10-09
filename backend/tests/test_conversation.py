"""Behavioural tests of the whole turn pipeline using the deterministic mock provider
(real extraction rules) or a scripted provider (fixtures / failures)."""
import pytest

from app.llm.base import LLMTimeoutError, LLMUpstreamError
from app.models import PersonalWishesState

from .conftest import ScriptedProvider, fixture_raw, make_service


async def say(service, conv, *messages):
    result = None
    for m in messages:
        result = await service.send_message(conv.id, m)
    return result


async def start(service, *messages):
    conv = await service.create()
    return conv, await say(service, conv, *messages)


async def test_single_field_update_then_asks_next_missing(mock_service):
    conv, result = await start(mock_service, "Jane Smith")
    assert result.conversation.state.full_name == "Jane Smith"
    assert "home address" in result.assistant_message


async def test_multiple_fields_in_one_message(mock_service):
    # Position the interview at the executor question (the spec's example), then answer
    # with executor + relationship + children + an out-of-schema fact in one message.
    conv = await mock_service.create()
    stored = await mock_service.get(conv.id)
    stored.state = PersonalWishesState(full_name="Jane Smith", home_address="12 Oak Road", covers_worldwide_assets=True)
    stored.expected_field = "executor.name"
    await mock_service._store.save(stored)
    result = await say(
        mock_service, conv,
        "My brother James. His address is 123 High Street and I have two children, Sarah and Daniel.",
    )
    state = result.conversation.state
    assert (state.executor.name, state.executor.relationship) == ("James", "brother")
    assert state.has_children is True and state.children == ["Sarah", "Daniel"]
    assert state.home_address == "12 Oak Road"          # executor's address did NOT overwrite it
    assert "executor" not in result.assistant_message.lower().replace("executor's address", "")
    assert "specific gifts" in result.assistant_message  # moved on to the next missing field
    assert "relationship" not in result.assistant_message


async def test_executor_name_only_asks_relationship_and_does_not_invent_one(mock_service):
    conv, result = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "no", "My executor is James")
    assert result.conversation.state.executor.name == "James"
    assert result.conversation.state.executor.relationship is None
    assert "What is James's relationship to you?" in result.assistant_message


async def test_captured_fields_are_never_asked_again(mock_service):
    conv, result = await start(mock_service, "My name is Jane Smith and I live at 12 Oak Road")
    assert result.conversation.state.full_name == "Jane Smith"
    assert result.conversation.state.home_address == "12 Oak Road"
    assert "full name" not in result.assistant_message and "home address" not in result.assistant_message
    assert "worldwide" in result.assistant_message


async def test_correction_overwrites_and_is_reflected_in_document(mock_service):
    conv, result = await start(mock_service, "My name is Jane Smith", "I live at 12 Oak Road")
    result = await say(mock_service, conv, "Actually my address is 22 Main Street.")
    assert result.conversation.state.home_address == "22 Main Street"
    assert not result.conversation.pending_conflicts


async def test_contradiction_asks_instead_of_overwriting_then_allows_correction(mock_service):
    conv, _ = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "I don't have children")
    assert (await mock_service.get(conv.id)).state.has_children is False

    result = await say(mock_service, conv, "I want everything divided between my two children")
    assert result.conversation.state.has_children is False          # not silently overwritten
    assert result.conversation.pending_conflicts[0].field == "has_children"
    assert "Which is correct?" in result.assistant_message

    result = await say(mock_service, conv, "I actually do have children — Sarah and Daniel")
    assert result.conversation.state.has_children is True
    assert result.conversation.state.children == ["Sarah", "Daniel"]
    assert result.conversation.pending_conflicts == []


async def test_user_can_resolve_contradiction_by_keeping_old_value(mock_service):
    conv, _ = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "I don't have children")
    await say(mock_service, conv, "divide everything between my two children")
    result = await say(mock_service, conv, "No, keep it as it was")
    assert result.conversation.state.has_children is False
    assert result.conversation.pending_conflicts == []


async def test_ambiguous_estate_wish_is_not_recorded_as_a_gift(mock_service):
    conv, result = await start(mock_service, "I want everything to go to my wife")
    assert result.conversation.state.specific_gifts is None
    assert "specific gift" in result.assistant_message


async def test_scripted_ambiguous_fixture_asks_model_clarification():
    service = make_service(ScriptedProvider(fixture_raw("ambiguous")))
    conv, result = await start(service, "I want everything to go to my wife.")
    assert result.assistant_message == "Which item should go to your wife?"


async def test_malformed_model_output_preserves_state_and_apologises():
    service = make_service(ScriptedProvider(fixture_raw("valid_single"), fixture_raw("malformed_text")))
    conv, _ = await start(service, "My name is Jane Smith")
    result = await say(service, conv, "hello")
    assert result.conversation.state.full_name == "Jane Smith"
    assert result.warnings and "trouble understanding" in result.assistant_message


async def test_invalid_type_from_model_cannot_corrupt_state():
    service = make_service(ScriptedProvider(fixture_raw("valid_single"), fixture_raw("invalid_type")))
    conv, _ = await start(service, "My name is Jane Smith")
    result = await say(service, conv, "Jane")
    assert result.conversation.state.full_name == "Jane Smith"
    assert any("full_name" in w for w in result.warnings)


@pytest.mark.parametrize("error", [LLMTimeoutError("slow"), LLMUpstreamError("down")])
async def test_llm_failure_raises_and_leaves_conversation_untouched(error):
    service = make_service(ScriptedProvider(error))
    conv = await service.create()
    with pytest.raises(type(error)):
        await service.send_message(conv.id, "Jane Smith")
    after = await service.get(conv.id)
    assert after.state == PersonalWishesState() and len(after.messages) == 1


async def test_completion_is_decided_by_backend_not_model(mock_service):
    conv, result = await start(
        mock_service, "Jane Smith", "12 Oak Road", "yes", "no", "My executor is James", "brother"
    )
    assert result.conversation.state.executor.relationship == "brother"
    assert not result.conversation.pending_conflicts
    result = await say(mock_service, conv, "no", "no")
    assert "everything I need" in result.assistant_message
    assert result.conversation.state.specific_gifts == [] and result.conversation.state.additional_wishes == []


async def test_gift_is_captured_with_recipient(mock_service):
    conv, result = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "no", "My executor is James", "brother",
                               "I'd like to leave my watch to my nephew Tom.")
    gift = result.conversation.state.specific_gifts[0]
    assert gift.description == "my watch" and gift.recipient == "my nephew Tom"


async def test_empty_message_rejected(mock_service):
    from app.service import InvalidMessage
    conv = await mock_service.create()
    with pytest.raises(InvalidMessage):
        await mock_service.send_message(conv.id, "   ")


async def test_changing_executor_clears_old_relationship_and_asks_again(mock_service):
    conv, _ = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "no", "My brother James is my executor")
    state = (await mock_service.get(conv.id)).state
    assert (state.executor.name, state.executor.relationship) == ("James", "brother")
    result = await say(mock_service, conv, "Change my executor to Sarah")
    assert result.conversation.state.executor.name == "Sarah"
    assert result.conversation.state.executor.relationship is None
    assert "What is Sarah's relationship to you?" in result.assistant_message


async def test_child_count_mismatch_asks_for_names_instead_of_guessing(mock_service):
    conv, _ = await start(mock_service, "Jane Smith", "12 Oak Road", "yes", "I have two children, Sarah and Daniel")
    result = await say(mock_service, conv, "I have three children, not two")
    assert result.conversation.state.children == ["Sarah", "Daniel"]   # nothing invented
    assert "3 children" in result.assistant_message
    result = await say(mock_service, conv, "Actually my children are Sarah, Daniel and Emma")
    assert result.conversation.state.children == ["Sarah", "Daniel", "Emma"]
