from __future__ import annotations

from sales_cockpit.db import connect, init_db
from sales_cockpit.services.front_import import (
    build_front_cutover_plan,
    classify_front_migration,
    extract_front_phone,
    list_front_import_records,
    preview_front_conversation,
    rematch_front_buffer,
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
    assert preview["migration_status"] == "manual_review"


def test_classify_front_active_inbound_recommends_reply() -> None:
    classification = classify_front_migration(
        {"status": "assigned"},
        [_front_message("msg_1", is_inbound=True)],
    )

    assert classification["migration_status"] == "active"
    assert classification["migration_action_type"] == "reply"


def test_classify_front_active_outbound_recommends_follow_up() -> None:
    classification = classify_front_migration(
        {"status": "assigned"},
        [_front_message("msg_1", is_inbound=False)],
    )

    assert classification["migration_status"] == "active"
    assert classification["migration_action_type"] == "follow_up"


def test_classify_front_archived_has_no_next_action() -> None:
    classification = classify_front_migration(
        {"status": "archived"},
        [_front_message("msg_1", is_inbound=True)],
    )

    assert classification["migration_status"] == "resolved"
    assert classification["migration_action_type"] is None


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
    assert records[0]["migration_status"] == "active"
    assert records[0]["migration_action_type"] == "follow_up"
    assert records[0]["front_message_count"] == 1


def test_list_front_import_records_filters_review_queue() -> None:
    _seed_lead_with_conversation("+41767270073")
    upsert_front_history(
        _front_conversation("cnv_matched", "+41767270073", status="assigned"),
        messages=[_front_message("msg_matched", is_inbound=True)],
    )
    upsert_front_history(
        _front_conversation("cnv_unmatched", "+41760000000", status="archived"),
        messages=[_front_message("msg_unmatched", is_inbound=False)],
    )

    matched = list_front_import_records(match_status="matched")
    resolved = list_front_import_records(migration_status="resolved")
    reply = list_front_import_records(migration_action_type="reply")
    no_action = list_front_import_records(migration_action_type="none")

    assert [item["front_conversation_id"] for item in matched] == ["cnv_matched"]
    assert [item["front_conversation_id"] for item in resolved] == ["cnv_unmatched"]
    assert [item["front_conversation_id"] for item in reply] == ["cnv_matched"]
    assert [item["front_conversation_id"] for item in no_action] == ["cnv_unmatched"]


def test_build_front_cutover_plan_is_read_only_and_conservative() -> None:
    _seed_lead_with_conversation("+41767270073")
    upsert_front_history(
        _front_conversation("cnv_ready", "+41767270073", status="assigned"),
        messages=[_front_message("msg_ready", is_inbound=True)],
    )
    upsert_front_history(
        _front_conversation("cnv_history", "+41767270073", status="archived"),
        messages=[_front_message("msg_history", is_inbound=False)],
    )
    upsert_front_history(
        _front_conversation("cnv_review", "+41760000000", status="assigned"),
        messages=[_front_message("msg_review", is_inbound=True)],
    )

    plan = build_front_cutover_plan()

    assert plan["counts"] == {
        "ready_to_convert": 1,
        "history_only": 1,
        "manual_review": 1,
    }
    ready = next(item for item in plan["rows"] if item["front_conversation_id"] == "cnv_ready")
    history = next(item for item in plan["rows"] if item["front_conversation_id"] == "cnv_history")
    review = next(item for item in plan["rows"] if item["front_conversation_id"] == "cnv_review")
    assert ready["recommended_action"] == "reply"
    assert ready["recommended_owner"] == "Mihary"
    assert history["recommended_action"] is None
    assert review["decision"] == "manual_review"

    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS total FROM tasks").fetchone()["total"] == 0


def test_rematch_front_buffer_matches_after_schooldrive_backfill() -> None:
    init_db()
    upsert_front_history(
        _front_conversation("cnv_late_match", "+41760000001", status="assigned"),
        messages=[_front_message("msg_late_match", is_inbound=True)],
    )
    before = list_front_import_records()
    assert before[0]["match_status"] == "unmatched"

    lead_id, conversation_id = _seed_lead_with_conversation("+41760000001")
    result = rematch_front_buffer()

    assert result["match_counts"] == {"matched": 1}
    after = list_front_import_records()
    assert after[0]["match_status"] == "matched"
    assert after[0]["lead_id"] == lead_id
    assert after[0]["conversation_id"] == conversation_id


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


def _front_conversation(
    conversation_id: str = "cnv_1",
    phone: str = "+41767270073",
    status: str = "assigned",
) -> dict:
    return {
        "id": conversation_id,
        "subject": f"WhatsApp thread with {phone}",
        "status": status,
        "assignee": {"name": "info@essr.ch"},
        "_links": {"self": f"https://essr.api.frontapp.com/conversations/{conversation_id}"},
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
