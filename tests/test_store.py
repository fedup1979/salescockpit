from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import (
    authenticate,
    get_conversation,
    list_conversations,
    send_freeform_message,
    set_conversation_status,
)


def test_seeded_user_can_login() -> None:
    seed_initial_data()
    user = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    assert user is not None
    assert user["role"] == "admin"


def test_freeform_send_blocked_when_window_closed() -> None:
    seed_initial_data()
    conversations = list_conversations()
    closed = next(item for item in conversations if item["window_state"] == "closed")
    ok, message = send_freeform_message(closed["conversation_id"], 1, "Test")
    assert ok is False
    assert "fermée" in message


def test_conversation_can_be_resolved_and_reopened() -> None:
    seed_initial_data()
    conversation_id = list_conversations()[0]["conversation_id"]

    ok, _ = set_conversation_status(conversation_id, 1, "resolved")
    assert ok is True
    assert get_conversation(conversation_id)["status"] == "resolved"

    ok, _ = set_conversation_status(conversation_id, 1, "open")
    assert ok is True
    assert get_conversation(conversation_id)["status"] == "open"
