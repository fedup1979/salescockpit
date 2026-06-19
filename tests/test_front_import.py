from __future__ import annotations

from sales_cockpit.db import connect, init_db
from sales_cockpit.services.front_import import (
    extract_front_phone,
    list_front_import_records,
    preview_front_conversation,
    upsert_front_history,
)


def test_extract_front_phone_from_whatsapp_subject() -> None:
    conversation = {"subject": "WhatsApp thread with +41767270073"}

    assert extract_front_phone(conversation) == "+41767270073"


def test_preview_front_conversation_matches_existing_lead_by_phone() -> None:
    lead_id, conversation_id = _seed_lead_with_conversation("+41767270073")
    conversation = _front_conversation()

    preview = preview_front_conversation(conversation)

    assert preview["match_status"] == "matched"
    assert preview["lead_id"] == lead_id
    assert preview["conversation_id"] == conversation_id
    assert preview["phone_e164"] == "+41767270073"


def test_upsert_front_history_is_idempotent_without_attaching_messages() -> None:
    _seed_lead_with_conversation("+41767270073")
    conversation = _front_conversation()
    messages = [_front_message("msg_1", is_inbound=False, body="Bonjour depuis Front")]

    first = upsert_front_history(conversation, messages=messages)
    second = upsert_front_history(conversation, messages=messages)

    assert first["created"] is True
    assert first["messages_created"] == 1
    assert first["messages_attached"] == 0
    assert second["created"] is False
    assert second["messages_created"] == 0
    assert second["messages_attached"] == 0

    with connect() as conn:
        front_message_count = conn.execute("SELECT COUNT(*) AS count FROM front_messages").fetchone()["count"]
        attached_count = conn.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE channel = 'front_history'"
        ).fetchone()["count"]
    assert front_message_count == 1
    assert attached_count == 0


def test_upsert_front_history_can_attach_matched_messages_once() -> None:
    _seed_lead_with_conversation("+41767270073")
    conversation = _front_conversation()
    messages = [_front_message("msg_1", is_inbound=True, body="Je suis intéressée")]

    first = upsert_front_history(conversation, messages=messages, attach_history=True)
    second = upsert_front_history(conversation, messages=messages, attach_history=True)

    assert first["messages_created"] == 1
    assert first["messages_attached"] == 1
    assert second["messages_created"] == 0
    assert second["messages_attached"] == 0

    with connect() as conn:
        attached = conn.execute(
            """
            SELECT m.direction, m.body, fm.imported_message_id
            FROM front_messages fm
            JOIN messages m ON m.id = fm.imported_message_id
            WHERE fm.front_message_id = 'msg_1'
            """
        ).fetchone()
        attached_count = conn.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE channel = 'front_history'"
        ).fetchone()["count"]
    assert attached["direction"] == "inbound"
    assert attached["body"] == "Je suis intéressée"
    assert attached["imported_message_id"]
    assert attached_count == 1


def test_list_front_import_records_shows_matching_status() -> None:
    _seed_lead_with_conversation("+41767270073")
    upsert_front_history(_front_conversation(), messages=[_front_message("msg_1")])

    records = list_front_import_records()

    assert len(records) == 1
    assert records[0]["front_conversation_id"] == "cnv_1"
    assert records[0]["match_status"] == "matched"
    assert records[0]["front_message_count"] == 1


def _seed_lead_with_conversation(phone: str) -> tuple[int, int]:
    init_db()
    with connect() as conn:
        lead_cursor = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, phone_e164, phone_raw
            ) VALUES ('lead:front-test', 'Zarina', 'Test', ?, ?)
            """,
            (phone, phone),
        )
        lead_id = int(lead_cursor.lastrowid)
        conversation_cursor = conn.execute(
            """
            INSERT INTO conversations (lead_id, recipient_phone_e164, status)
            VALUES (?, ?, 'open')
            """,
            (lead_id, phone),
        )
    return lead_id, int(conversation_cursor.lastrowid)


def _front_conversation() -> dict:
    return {
        "id": "cnv_1",
        "subject": "WhatsApp thread with +41767270073",
        "status": "assigned",
        "assignee": {"name": "info@essr.ch"},
        "_links": {"self": "https://essr.api.frontapp.com/conversations/cnv_1"},
    }


def _front_message(
    message_id: str,
    is_inbound: bool = False,
    body: str = "Bonjour depuis Front",
) -> dict:
    return {
        "id": message_id,
        "type": "whatsapp",
        "is_inbound": is_inbound,
        "created_at": 1781157301,
        "text": body,
    }
