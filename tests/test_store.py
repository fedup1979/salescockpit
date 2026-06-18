from datetime import timedelta
from uuid import uuid4

from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import (
    authenticate,
    get_conversation,
    get_next_action_for_lead,
    handoff_to_closer,
    list_conversations,
    list_templates,
    list_users,
    record_inbound_message,
    schedule_followup,
    send_freeform_message,
    set_conversation_status,
    update_lead_qualification,
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


def test_inbound_message_creates_setter_reply_action() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour, je veux des informations.")

    action = get_next_action_for_lead(result["lead_id"])
    assert action is not None
    assert action["type"] == "reply"
    assert action["assigned_to_role"] == "setter"

    conversation = next(
        item for item in list_conversations(search=phone)
        if item["conversation_id"] == result["conversation_id"]
    )
    assert conversation["work_queue"] == "todo"


def test_followup_scheduled_moves_conversation_to_waiting() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Pouvez-vous me rappeler ?")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() + timedelta(days=2))

    ok, _ = schedule_followup(
        result["conversation_id"],
        admin["id"],
        action["assigned_to_user_id"],
        due_at,
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "follow_up"
    conversation = next(
        item for item in list_conversations()
        if item["conversation_id"] == result["conversation_id"]
    )
    assert conversation["work_queue"] == "waiting"


def test_handoff_to_closer_creates_closing_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un rendez-vous.")

    ok, _ = handoff_to_closer(
        result["conversation_id"],
        admin["id"],
        closer["id"],
        appointment_note="Disponible demain à 14h",
        notes="Prospect chaud.",
    )

    assert ok is True
    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "closing"
    assert conversation["lead_status"] == "neutral"
    assert conversation["closer_user_id"] == closer["id"]
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "closing_call"
    assert action["assigned_to_user_id"] == closer["id"]


def test_seed_includes_setter2_and_demo_templates() -> None:
    seed_initial_data()
    users = list_users(active_only=False)
    assert any(user["email"] == "setter2@essr.ch" for user in users)
    templates = list_templates("demo_")
    assert len(templates) >= 10


def test_seeded_conversations_include_schooldrive_lead_types() -> None:
    seed_initial_data()
    conversations = [
        item for item in list_conversations()
        if str(item.get("schooldrive_lead_id") or "").startswith("SD-DEMO-")
    ]
    assert any(item["lead_type"] == "lead" for item in conversations)
    assert any(item["lead_type"] == "presubscription" for item in conversations)
    assert all(item.get("course_category_short_title") for item in conversations)


def test_stop_status_blocks_followups_and_resolves_conversation() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Merci de ne plus me contacter.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "lost",
        "do_not_contact",
    )

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert get_next_action_for_lead(result["lead_id"]) is None
    ok, message = schedule_followup(
        result["conversation_id"],
        admin["id"],
        admin["id"],
        iso_utc(utc_now() + timedelta(days=1)),
    )
    assert ok is False
    assert "bloque" in message


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:8]
