from __future__ import annotations

from pathlib import Path

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db, seed_initial_data
from sales_cockpit.services.front_import import (
    build_front_cutover_plan,
    classify_front_migration,
    extract_front_phone,
    import_front_message_attachments,
    import_front_transition_records,
    list_front_import_records,
    preview_front_conversation,
    purge_front_transition_import,
    reconcile_front_transition_names,
    rematch_front_buffer,
    repair_front_imported_message_bodies,
    upsert_front_history,
)
from sales_cockpit.store import get_attachment_download


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
    assert preview["migration_status"] == "active"
    assert preview["migration_action_type"] == "front_transition_review"


def test_classify_front_active_inbound_recommends_transition_review() -> None:
    classification = classify_front_migration(
        {"status": "assigned"},
        [_front_message("msg_1", is_inbound=True)],
    )

    assert classification["migration_status"] == "active"
    assert classification["migration_action_type"] == "front_transition_review"


def test_classify_front_active_outbound_recommends_transition_review() -> None:
    classification = classify_front_migration(
        {"status": "assigned"},
        [_front_message("msg_1", is_inbound=False)],
    )

    assert classification["migration_status"] == "active"
    assert classification["migration_action_type"] == "front_transition_review"


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


def test_front_import_preserves_line_breaks_and_removes_html() -> None:
    seed_initial_data()
    message = {
        "id": "msg_html_front",
        "type": "whatsapp",
        "is_inbound": False,
        "created_at": 1781157301,
        "text": "",
        "body": "<div>Bonjour Viera,<br><br>J'ai bien reçu votre demande.<br>1) Oui<br>2) Non</div>",
    }

    import_front_transition_records(
        [{"conversation": _front_conversation("cnv_html_front", "+41760000101"), "messages": [message]}],
        "front-transition-html",
    )

    with connect() as conn:
        row = conn.execute(
            """
            SELECT fm.body AS front_body, m.body AS message_body
            FROM front_messages fm
            JOIN messages m ON m.id = fm.imported_message_id
            WHERE fm.front_message_id = 'msg_html_front'
            """
        ).fetchone()

    assert row["front_body"] == "Bonjour Viera,\n\nJ'ai bien reçu votre demande.\n1) Oui\n2) Non"
    assert row["message_body"] == row["front_body"]
    assert "<div>" not in row["message_body"]
    assert "<br>" not in row["message_body"]


def test_front_body_repair_updates_existing_imported_messages() -> None:
    seed_initial_data()
    raw_body = "<div>Bonjour<br><br>Merci</div>"
    import_front_transition_records(
        [
            {
                "conversation": _front_conversation("cnv_repair_front", "+41760000102"),
                "messages": [
                    {
                        "id": "msg_repair_front",
                        "type": "whatsapp",
                        "is_inbound": True,
                        "created_at": 1781157301,
                        "text": "",
                        "body": raw_body,
                    }
                ],
            }
        ],
        "front-transition-repair",
    )
    with connect() as conn:
        conn.execute(
            """
            UPDATE front_messages
            SET body = ?
            WHERE front_message_id = 'msg_repair_front'
            """,
            (raw_body,),
        )
        conn.execute(
            """
            UPDATE messages
            SET body = ?
            WHERE id = (
                SELECT imported_message_id FROM front_messages WHERE front_message_id = 'msg_repair_front'
            )
            """,
            (raw_body,),
        )

    dry_run = repair_front_imported_message_bodies("front-transition-repair", dry_run=True)
    executed = repair_front_imported_message_bodies("front-transition-repair", dry_run=False)

    assert dry_run["would_update"] == 1
    assert executed["updated"] == 1
    with connect() as conn:
        row = conn.execute(
            """
            SELECT fm.body AS front_body, m.body AS message_body
            FROM front_messages fm
            JOIN messages m ON m.id = fm.imported_message_id
            WHERE fm.front_message_id = 'msg_repair_front'
            """
        ).fetchone()
    assert row["front_body"] == "Bonjour\n\nMerci"
    assert row["message_body"] == "Bonjour\n\nMerci"


def test_front_attachment_import_is_idempotent_and_downloadable(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_PUBLIC_API_BASE_URL", "https://cockpit.example.test")
    get_settings.cache_clear()
    seed_initial_data()
    message = {
        "id": "msg_attachment_front",
        "type": "whatsapp",
        "is_inbound": True,
        "created_at": 1781157301,
        "text": "",
        "body": '<div></div><div><img class="front-inline-img" src="/cell-00032/api/attachment"></div>',
        "attachments": [
            {
                "id": "att_front_1",
                "filename": "qr code.png",
                "content_type": "image/png",
                "size": 7,
                "_links": {"download": "https://front.example.test/attachments/att_front_1"},
            }
        ],
    }
    import_front_transition_records(
        [{"conversation": _front_conversation("cnv_attachment_front", "+41760000103"), "messages": [message]}],
        "front-transition-attachment",
    )

    dry_run = import_front_message_attachments("front-transition-attachment", dry_run=True)
    executed = import_front_message_attachments(
        "front-transition-attachment",
        dry_run=False,
        client=_FakeAttachmentClient(),
    )
    second = import_front_message_attachments(
        "front-transition-attachment",
        dry_run=False,
        client=_FakeAttachmentClient(),
    )

    assert dry_run["candidate_attachments"] == 1
    assert dry_run["would_import"] == 1
    assert executed["imported"] == 1
    assert second["already_imported"] == 1
    assert second["imported"] == 0
    with connect() as conn:
        attachment = conn.execute("SELECT * FROM attachments WHERE source LIKE 'front:%'").fetchone()
        message_body = conn.execute(
            "SELECT body FROM messages WHERE id = ?",
            (attachment["message_id"],),
        ).fetchone()["body"]
    assert attachment["file_name"] == "qr code.png"
    assert attachment["mime_type"] == "image/png"
    assert message_body == "Pièce jointe Front"
    download = get_attachment_download(attachment["id"], Path(attachment["storage_url_or_path"]).name)
    assert download is not None
    assert download["path"].read_bytes() == b"PNGDATA"
    get_settings.cache_clear()


def test_front_name_reconciliation_updates_generic_contact_from_existing_phone_match() -> None:
    _seed_lead_with_conversation("+41760000104")
    import_front_transition_records(
        [
            {
                "conversation": _front_conversation("cnv_name_front", "+41760000104"),
                "messages": [_front_message("msg_name_front", is_inbound=True)],
            }
        ],
        "front-transition-names",
    )

    dry_run = reconcile_front_transition_names("front-transition-names", dry_run=True)
    executed = reconcile_front_transition_names("front-transition-names", dry_run=False)

    assert dry_run["counts"]["update"] == 1
    assert executed["counts"]["update"] == 1
    with connect() as conn:
        lead = conn.execute(
            """
            SELECT first_name, last_name, identity_status
            FROM leads
            WHERE source = 'front_transition'
              AND front_import_run_id = 'front-transition-names'
            """
        ).fetchone()
    assert lead["first_name"] == "Zarina"
    assert lead["last_name"] == "Test"
    assert lead["identity_status"] == "verified"


def test_list_front_import_records_shows_matching_status() -> None:
    _seed_lead_with_conversation("+41767270073")
    upsert_front_history(_front_conversation(), messages=[_front_message("msg_1")])

    records = list_front_import_records()

    assert len(records) == 1
    assert records[0]["front_conversation_id"] == "cnv_1"
    assert records[0]["match_status"] == "matched"
    assert records[0]["migration_status"] == "active"
    assert records[0]["migration_action_type"] == "front_transition_review"
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
    transition = list_front_import_records(migration_action_type="front_transition_review")
    no_action = list_front_import_records(migration_action_type="none")

    assert [item["front_conversation_id"] for item in matched] == ["cnv_matched"]
    assert [item["front_conversation_id"] for item in resolved] == ["cnv_unmatched"]
    assert [item["front_conversation_id"] for item in transition] == ["cnv_matched"]
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
    assert ready["recommended_action"] == "front_transition_review"
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


def test_front_transition_import_groups_same_phone_and_creates_review_action() -> None:
    seed_initial_data()
    records = [
        {
            "conversation": _front_conversation("cnv_front_a", "+41760000010", status="assigned"),
            "messages": [_front_message("msg_front_a", is_inbound=False, body="Message envoyé depuis Front")],
        },
        {
            "conversation": _front_conversation("cnv_front_b", "+41760000010", status="assigned"),
            "messages": [_front_message("msg_front_b", is_inbound=True, body="Réponse prospect Front")],
        },
    ]

    result = import_front_transition_records(records, "front-transition-test")

    assert result["group_count"] == 1
    assert result["conversation_count"] == 2
    assert result["created_leads"] == 1
    assert result["created_actions"] == 1
    assert result["attached_messages"] == 2
    with connect() as conn:
        lead = conn.execute(
            """
            SELECT id, source, lead_type, front_import_run_id, front_transition_key
            FROM leads
            WHERE source = 'front_transition'
            """
        ).fetchone()
        conversation = conn.execute(
            "SELECT status, channel, front_import_run_id FROM conversations WHERE lead_id = ?",
            (lead["id"],),
        ).fetchone()
        task = conn.execute(
            """
            SELECT type, urgency, status, sequence_code, front_import_run_id
            FROM tasks
            WHERE lead_id = ? AND type = 'front_transition_review'
            """,
            (lead["id"],),
        ).fetchone()
        front_rows = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM front_conversations
            WHERE import_run_id = 'front-transition-test'
              AND front_group_key = 'phone:+41760000010'
            """
        ).fetchone()["count"]
        history_rows = conn.execute(
            "SELECT COUNT(*) AS count FROM messages WHERE lead_id = ? AND channel = 'front_history'",
            (lead["id"],),
        ).fetchone()["count"]

    assert lead["lead_type"] == "front_transition"
    assert lead["front_transition_key"] == "phone:+41760000010"
    assert conversation["status"] == "open"
    assert conversation["channel"] == "whatsapp_front_transition"
    assert task["status"] == "open"
    assert task["urgency"] == "urgent"
    assert task["sequence_code"] is None
    assert task["front_import_run_id"] == "front-transition-test"
    assert front_rows == 2
    assert history_rows == 2


def test_front_transition_import_archived_conversation_is_history_only() -> None:
    seed_initial_data()
    records = [
        {
            "conversation": _front_conversation("cnv_front_archived", "+41760000011", status="archived"),
            "messages": [_front_message("msg_front_archived", is_inbound=False, body="Ancien message")],
        }
    ]

    result = import_front_transition_records(records, "front-transition-archived")

    assert result["group_count"] == 1
    assert result["created_actions"] == 0
    with connect() as conn:
        lead = conn.execute(
            "SELECT id FROM leads WHERE source = 'front_transition' AND front_import_run_id = ?",
            ("front-transition-archived",),
        ).fetchone()
        conversation = conn.execute(
            "SELECT status, resolution_reason FROM conversations WHERE lead_id = ?",
            (lead["id"],),
        ).fetchone()
        action_count = conn.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE lead_id = ?",
            (lead["id"],),
        ).fetchone()["count"]

    assert conversation["status"] == "resolved"
    assert conversation["resolution_reason"] == "front_import_archived"
    assert action_count == 0


def test_front_transition_reimport_archived_cancels_open_transition_action() -> None:
    seed_initial_data()
    active_record = {
        "conversation": _front_conversation("cnv_front_reimport", "+41760000014", status="assigned"),
        "messages": [_front_message("msg_front_reimport", is_inbound=True, body="Message actif")],
    }
    archived_record = {
        "conversation": _front_conversation("cnv_front_reimport", "+41760000014", status="archived"),
        "messages": [_front_message("msg_front_reimport", is_inbound=True, body="Message actif")],
    }

    import_front_transition_records([active_record], "front-transition-reimport")
    import_front_transition_records([archived_record], "front-transition-reimport")

    with connect() as conn:
        lead = conn.execute(
            "SELECT id FROM leads WHERE source = 'front_transition' AND front_import_run_id = ?",
            ("front-transition-reimport",),
        ).fetchone()
        conversation = conn.execute(
            "SELECT status, resolution_reason FROM conversations WHERE lead_id = ?",
            (lead["id"],),
        ).fetchone()
        action = conn.execute(
            "SELECT status, outcome FROM tasks WHERE lead_id = ? AND type = 'front_transition_review'",
            (lead["id"],),
        ).fetchone()

    assert conversation["status"] == "resolved"
    assert conversation["resolution_reason"] == "front_import_archived"
    assert action["status"] == "cancelled"
    assert action["outcome"] == "Conversation Front terminée avant reprise"


def test_front_transition_purge_removes_only_selected_run() -> None:
    seed_initial_data()
    import_front_transition_records(
        [
            {
                "conversation": _front_conversation("cnv_front_purge_a", "+41760000012", status="assigned"),
                "messages": [_front_message("msg_front_purge_a", is_inbound=True)],
            }
        ],
        "front-transition-purge-a",
    )
    import_front_transition_records(
        [
            {
                "conversation": _front_conversation("cnv_front_purge_b", "+41760000013", status="assigned"),
                "messages": [_front_message("msg_front_purge_b", is_inbound=True)],
            }
        ],
        "front-transition-purge-b",
    )

    result = purge_front_transition_import("front-transition-purge-a")

    assert result["deleted_leads"] == 1
    assert result["deleted_front_conversations"] == 1
    assert result["deleted_front_messages"] == 1
    with connect() as conn:
        deleted_run_leads = conn.execute(
            "SELECT COUNT(*) AS count FROM leads WHERE source = 'front_transition' AND front_import_run_id = ?",
            ("front-transition-purge-a",),
        ).fetchone()["count"]
        remaining_run_leads = conn.execute(
            "SELECT COUNT(*) AS count FROM leads WHERE source = 'front_transition' AND front_import_run_id = ?",
            ("front-transition-purge-b",),
        ).fetchone()["count"]
        remaining_front_rows = conn.execute(
            "SELECT COUNT(*) AS count FROM front_conversations WHERE import_run_id = ?",
            ("front-transition-purge-b",),
        ).fetchone()["count"]

    assert deleted_run_leads == 0
    assert remaining_run_leads == 1
    assert remaining_front_rows == 1


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


class _FakeAttachmentClient:
    def download_attachment(self, url: str) -> dict:
        assert url == "https://front.example.test/attachments/att_front_1"
        return {
            "content": b"PNGDATA",
            "mime_type": "image/png",
            "file_name": "qr code.png",
        }
