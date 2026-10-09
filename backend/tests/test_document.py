from app.document import DISCLAIMER, PLACEHOLDER, build_document
from app.models import Gift, PersonalWishesState

from .conftest import complete_state


def test_document_contains_confirmed_values_and_disclaimer():
    doc = build_document(complete_state(), is_complete=True)
    assert DISCLAIMER == "Fictional — Not Legal Advice"
    assert doc.disclaimer in doc.text and doc.text.count(DISCLAIMER) >= 2
    for expected in ("Jane Smith", "12 Oak Road", "James Smith", "brother", "I have no children."):
        assert expected in doc.text
    assert doc.status == "complete"


def test_unknown_values_are_placeholders_not_invented():
    doc = build_document(PersonalWishesState(full_name="Jane Smith"), is_complete=False)
    assert doc.status == "draft" and "INCOMPLETE" in doc.text
    assert doc.text.count(PLACEHOLDER) >= 5
    assert "James" not in doc.text and "brother" not in doc.text


def test_optional_sections_distinguish_none_provided_from_not_asked():
    unanswered = build_document(complete_state(), True)
    gifts = next(s for s in unanswered.sections if "Gifts" in s.heading)
    assert gifts.lines == [PLACEHOLDER]

    answered = build_document(complete_state().model_copy(update={"specific_gifts": [], "additional_wishes": []}), True)
    assert next(s for s in answered.sections if "Gifts" in s.heading).lines == ["No specific gifts were specified."]


def test_gifts_and_children_listed():
    state = complete_state().model_copy(update={
        "has_children": True, "children": ["Sarah", "Daniel"],
        "specific_gifts": [Gift(description="my watch", recipient="Tom"), Gift(description="my piano")],
    })
    text = build_document(state, True).text
    assert "- Sarah" in text and "- Daniel" in text
    assert "my watch — to Tom" in text and "recipient not specified" in text
