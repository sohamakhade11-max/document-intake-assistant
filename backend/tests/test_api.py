import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(Settings(llm_provider="mock")))


def new(client) -> str:
    response = client.post("/api/conversations")
    assert response.status_code == 201
    return response.json()["id"]


def test_create_conversation_returns_first_question_and_empty_state(client):
    body = client.post("/api/conversations").json()
    assert body["messages"][0]["role"] == "assistant"
    assert body["state"]["full_name"] is None and body["is_complete"] is False
    assert body["document"]["disclaimer"] == "Fictional — Not Legal Advice"


def test_send_message_updates_state_document_and_history(client):
    cid = new(client)
    body = client.post(f"/api/conversations/{cid}/messages", json={"message": "Jane Smith"}).json()
    assert body["conversation"]["state"]["full_name"] == "Jane Smith"
    assert "Jane Smith" in body["conversation"]["document"]["text"]
    assert [m["role"] for m in body["conversation"]["messages"]] == ["assistant", "user", "assistant"]


def test_get_state_and_document_endpoints(client):
    cid = new(client)
    client.post(f"/api/conversations/{cid}/messages", json={"message": "Jane Smith"})
    state = client.get(f"/api/conversations/{cid}/state").json()
    assert state["state"]["full_name"] == "Jane Smith"
    assert state["field_statuses"]["full_name"] == "confirmed"
    assert state["field_statuses"]["home_address"] == "unknown"
    assert "home_address" in state["missing_required"]
    doc = client.get(f"/api/conversations/{cid}/document").json()
    assert doc["title"] == "PERSONAL WISHES DOCUMENT" and doc["status"] == "draft"
    assert client.get(f"/api/conversations/{cid}").json()["id"] == cid


@pytest.mark.parametrize("path", ["", "/state", "/document"])
def test_unknown_conversation_returns_404_envelope(client, path):
    response = client.get(f"/api/conversations/nope{path}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "conversation_not_found"


def test_unknown_conversation_on_post(client):
    assert client.post("/api/conversations/nope/messages", json={"message": "hi"}).status_code == 404


@pytest.mark.parametrize("payload", [{"message": ""}, {"message": "   "}, {}, {"message": "x" * 2001}])
def test_invalid_messages_rejected(client, payload):
    cid = new(client)
    response = client.post(f"/api/conversations/{cid}/messages", json=payload)
    assert response.status_code == 422 and "error" in response.json()


def test_malformed_model_output_is_graceful_200(client):
    cid = new(client)
    body = client.post(f"/api/conversations/{cid}/messages", json={"message": "[mock:malformed] hi"}).json()
    assert body["warnings"] and body["conversation"]["state"]["full_name"] is None


def test_invalid_type_from_model_is_ignored(client):
    cid = new(client)
    body = client.post(f"/api/conversations/{cid}/messages", json={"message": "[mock:invalid-type]"}).json()
    assert body["conversation"]["state"]["full_name"] is None and body["warnings"]


@pytest.mark.parametrize("tag,status,code", [("timeout", 504, "llm_timeout"), ("error", 502, "llm_unavailable")])
def test_llm_failures_map_to_friendly_errors(client, tag, status, code):
    cid = new(client)
    response = client.post(f"/api/conversations/{cid}/messages", json={"message": f"[mock:{tag}]"})
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert len(client.get(f"/api/conversations/{cid}").json()["messages"]) == 1  # turn not recorded


def test_missing_api_key_is_reported_not_a_crash():
    client = TestClient(create_app(Settings(llm_provider="openai", openai_api_key=None)))
    assert client.get("/api/health").json() == {"status": "ok", "llm_provider": "openai", "llm_configured": False}
    cid = client.post("/api/conversations").json()["id"]
    response = client.post(f"/api/conversations/{cid}/messages", json={"message": "hi"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "llm_not_configured"
    assert "Traceback" not in response.text


def test_unexpected_exception_does_not_leak_details():
    class Boom:
        name, is_configured = "boom", True

        async def process_message(self, request):
            raise RuntimeError("secret-internal-detail")

    client = TestClient(create_app(Settings(), provider=Boom()), raise_server_exceptions=False)
    cid = client.post("/api/conversations").json()["id"]
    response = client.post(f"/api/conversations/{cid}/messages", json={"message": "hi"})
    assert response.status_code == 500 and "secret-internal-detail" not in response.text
