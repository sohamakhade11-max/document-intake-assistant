import pytest

from app.llm.base import FieldUpdate, LLMOutputError
from app.llm.parsing import parse_llm_output
from app.state_updates import apply_updates
from app.models import PersonalWishesState

from .conftest import FIXTURES, fixture_raw

JANE = PersonalWishesState(full_name="Jane Smith")


def apply_fixture(name, state=JANE, pending=None):
    llm = parse_llm_output(fixture_raw(name))
    return apply_updates(state, llm.updates, FIXTURES[name]["user_message"], pending or [], llm.keep_existing_fields)


def test_valid_response_parses_and_applies():
    result = apply_fixture("valid_single", PersonalWishesState())
    assert result.state.full_name == "Jane Smith"
    assert result.applied == ["full_name"]


@pytest.mark.parametrize("name", ["malformed_text", "not_an_object", "missing_keys", "wrong_shape"])
def test_malformed_or_incomplete_responses_raise(name):
    with pytest.raises(LLMOutputError):
        parse_llm_output(fixture_raw(name))


def test_fenced_json_is_accepted():
    assert parse_llm_output(fixture_raw("fenced_json")).updates == []


def test_invalid_field_type_is_rejected_and_state_preserved():
    result = apply_fixture("invalid_type")
    assert result.state.full_name == "Jane Smith"
    assert result.rejected[0].field == "full_name"


def test_string_is_not_accepted_as_boolean():
    result = apply_fixture("string_boolean", PersonalWishesState())
    assert result.state.covers_worldwide_assets is None
    assert result.rejected


def test_update_without_supporting_text_is_rejected():
    result = apply_fixture("invented_fact", PersonalWishesState())
    assert result.state.executor.name == "James"
    assert result.state.executor.relationship is None  # "brother" was invented -> dropped
    assert [r.field for r in result.rejected] == ["executor.relationship"]


def test_unknown_field_is_rejected():
    result = apply_fixture("unknown_field")
    assert result.rejected[0].reason == "unknown field"
    assert result.state == JANE


def test_one_bad_update_does_not_block_valid_ones():
    updates = [
        FieldUpdate(field="full_name", value=42, evidence="Jane"),
        FieldUpdate(field="home_address", value="1 High St", evidence="1 High St"),
    ]
    result = apply_updates(PersonalWishesState(), updates, "Jane, 1 High St", [], [])
    assert result.state.home_address == "1 High St" and result.state.full_name is None
