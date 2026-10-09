import pytest
from pydantic import ValidationError

from app.flow import field_statuses, is_complete, missing_required, next_field
from app.models import Conflict, PersonalWishesState

from .conftest import complete_state


def test_empty_state_is_valid_and_everything_unknown():
    state = PersonalWishesState()
    assert state.full_name is None
    assert missing_required(state) == [
        "full_name", "home_address", "covers_worldwide_assets", "has_children", "executor.name", "executor.relationship",
    ]
    assert not is_complete(state, [])


def test_explicit_false_is_an_answer_not_unknown():
    state = PersonalWishesState(covers_worldwide_assets=False, has_children=False)
    assert "covers_worldwide_assets" not in missing_required(state)
    assert "has_children" not in missing_required(state)
    statuses = field_statuses(state, [])
    assert statuses["covers_worldwide_assets"] == "confirmed"
    assert statuses["has_children"] == "confirmed"


def test_children_required_only_when_has_children_true():
    assert "children" not in missing_required(PersonalWishesState(has_children=False))
    state = PersonalWishesState(has_children=True)
    assert "children" in missing_required(state)
    assert field_statuses(state, [])["children"] == "incomplete"


def test_optional_fields_none_vs_explicitly_empty():
    state = complete_state()
    assert is_complete(state, [])            # optional fields don't block completion
    assert next_field(state) == "specific_gifts"
    answered = state.model_copy(update={"specific_gifts": [], "additional_wishes": []})
    assert next_field(answered) is None       # [] means "user said none"


def test_pending_conflict_blocks_completion_and_marks_field():
    conflict = Conflict(field="has_children", question="?")
    assert not is_complete(complete_state(), [conflict])
    assert field_statuses(complete_state(), [conflict])["has_children"] == "needs_clarification"


def test_state_rejects_children_when_has_children_false():
    with pytest.raises(ValidationError):
        PersonalWishesState(has_children=False, children=["Sarah"])


def test_state_rejects_wrong_types():
    with pytest.raises(ValidationError):
        PersonalWishesState(full_name=123456)
