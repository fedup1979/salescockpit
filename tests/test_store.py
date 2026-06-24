from datetime import UTC, datetime, timedelta
from urllib.parse import unquote
from uuid import uuid4

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db, seed_initial_data
from sales_cockpit.services.twilio_content import TwilioContentTemplate
from sales_cockpit.services.twilio_client import TwilioMessageError
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import (
    assign_standard_next_action,
    authenticate,
    cancel_call_action_without_replacement,
    complete_admin_action,
    complete_action_with_workflow,
    create_and_submit_twilio_template,
    create_bug_report,
    create_next_action,
    create_template,
    create_template_request,
    add_sequence_step,
    deactivate_sequence_step,
    deactivate_course_default_session,
    get_conversation,
    get_attachment_download,
    get_integration_readiness,
    get_next_action_for_lead,
    get_outbound_safeguards,
    get_recommended_template_for_action,
    ingest_schooldrive_snapshot,
    handoff_to_closer,
    list_actions_for_lead,
    list_admin_actions,
    list_conversations,
    list_course_default_sessions,
    list_sequence_steps,
    list_messages,
    list_sequence_template_mappings,
    list_template_requests,
    list_templates,
    list_bug_reports,
    list_user_activity_log,
    list_users,
    record_inbound_message,
    reschedule_call_action,
    schedule_followup,
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    sync_twilio_templates,
    upsert_course_default_session,
    update_lead_qualification,
    update_outbound_safeguards,
    update_template_request_status,
    update_temporary_identity,
    upsert_sequence_step,
    upsert_sequence_template_mapping,
)
from sales_cockpit.services.front_import import upsert_front_history
from scripts.schooldrive_smoke import build_smoke_steps


def test_seeded_user_can_login() -> None:
    seed_initial_data()
    user = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    assert user is not None
    assert user["role"] == "admin"
    assert any(item["event_type"] == "login" for item in list_user_activity_log())


def test_bug_report_is_stored_with_activity_log() -> None:
    seed_initial_data()
    user = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    ok, message = create_bug_report(
        user["id"],
        "Inbox",
        "Carte incorrecte",
        "La prochaine action semble incohÃ©rente.",
        expected_behavior="Voir une relance.",
        actual_behavior="Voir un appel.",
        severity="high",
    )

    assert ok is True
    assert "Signalement" in message
    reports = list_bug_reports()
    assert reports[0]["title"] == "Carte incorrecte"
    assert reports[0]["severity"] == "high"
    admin_actions = list_admin_actions()
    bug_actions = [action for action in admin_actions if action["type"] == "bug_report"]
    assert bug_actions
    assert bug_actions[0]["bug_report_id"] == reports[0]["id"]
    ok, message = complete_admin_action(admin_actions[0]["id"], user["id"], "Bug revu")
    assert ok is True
    assert "termin" in message
    assert any(item["event_type"] == "bug_report_created" for item in list_user_activity_log())


def test_integration_readiness_summary_exposes_core_sections() -> None:
    seed_initial_data()
    upsert_front_history(
        {
            "id": "cnv_readiness",
            "subject": "WhatsApp thread with +41790004001",
            "status": "assigned",
        },
        messages=[
            {
                "id": "msg_readiness",
                "type": "whatsapp",
                "is_inbound": False,
                "created_at": 1781157301,
                "text": "Bonjour depuis Front.",
            }
        ],
    )

    readiness = get_integration_readiness()

    assert {item["name"] for item in readiness["checks"]} == {
        "SchoolDrive",
        "Front",
        "Twilio",
        "Backup",
        "Workflow",
        "API security",
        "Seed data",
    }
    assert readiness["front"]["message_count"] == 1
    assert readiness["front"]["migration_counts"]["active"] == 1
    assert "open_conversations_without_action" in readiness["workflow"]
    assert "api_token_configured" in readiness["security"]


def test_integration_readiness_accepts_mock_twilio_without_sender(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_MODE", "mock")
    monkeypatch.delenv("SALES_COCKPIT_TWILIO_WHATSAPP_SENDER", raising=False)
    get_settings.cache_clear()
    seed_initial_data()

    readiness = get_integration_readiness()

    twilio = next(item for item in readiness["checks"] if item["name"] == "Twilio")
    assert twilio["state"] == "ready"
    assert "mock" in twilio["detail"]


def test_readiness_allows_schooldrive_waiting_for_first_sent_autoresponder() -> None:
    seed_initial_data()
    queued_payload = build_smoke_steps(
        run_id="readiness-queued",
        environment="staging",
        base_time=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )[5].payload

    result = ingest_schooldrive_snapshot(queued_payload)

    assert get_next_action_for_lead(result["lead_id"]) is None
    readiness = get_integration_readiness()
    assert readiness["workflow"]["schooldrive_waiting_first_autoresponder_count"] == 1
    assert readiness["workflow"]["open_conversations_without_action"] == 0


def test_freeform_send_blocked_when_window_closed() -> None:
    seed_initial_data()
    conversations = list_conversations()
    closed = next(item for item in conversations if item["window_state"] == "closed")
    ok, message = send_freeform_message(closed["conversation_id"], 1, "Test")
    assert ok is False
    assert "WhatsApp" in message


def test_conversation_can_be_resolved_and_reopened() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Conversation de test.")
    conversation_id = result["conversation_id"]

    ok, _ = set_conversation_status(
        conversation_id,
        1,
        "resolved",
        resolution_reason="sequence_completed_no_reply",
        resolution_note="Fin de sÃ©quence de test.",
    )
    assert ok is True
    assert get_conversation(conversation_id)["status"] == "resolved"
    assert any(
        "conversation" in item["body"].lower()
        for item in list_messages(conversation_id)
        if item["direction"] == "manual_note"
    )

    ok, _ = set_conversation_status(
        conversation_id,
        1,
        "open",
        reopen_action_type="reply",
        reopen_assigned_to_user_id=1,
        reopen_reason="Test reopen",
    )
    assert ok is True
    assert get_conversation(conversation_id)["status"] == "open"
    assert any(
        "conversation" in item["body"].lower()
        for item in list_messages(conversation_id)
        if item["direction"] == "manual_note"
    )


def test_resolve_and_reopen_keep_sales_stage_coherent() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Conversation sans suite.")

    ok, message = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "resolved",
        resolution_reason="sequence_completed_no_reply",
        resolution_note="Fin de suivi sans réponse.",
    )
    assert ok is True, message
    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["sales_stage"] == "lost"
    assert conversation["lead_status"] == "eligible"

    ok, message = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "open",
        reopen_action_type="reply",
        reopen_assigned_to_user_id=admin["id"],
        reopen_reason="Le prospect a réécrit.",
    )
    assert ok is True, message
    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "open"
    assert conversation["sales_stage"] == "setting"
    assert get_next_action_for_lead(result["lead_id"])["type"] == "reply"


def test_init_db_normalizes_existing_terminal_workflow_states() -> None:
    seed_initial_data()
    phone = unique_phone()
    with connect() as conn:
        signed_id = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, phone_e164,
                source, lead_status, contact_status, sales_stage,
                temperature, identity_status
            ) VALUES ('lead:terminal-signed', 'Test', 'Signé', ?, 'schooldrive_webhook',
                'signed', 'contact_allowed', 'setting', 'warm', 'verified')
            """,
            (phone,),
        ).lastrowid
        not_relevant_id = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, phone_e164,
                source, lead_status, contact_status, sales_stage,
                temperature, identity_status
            ) VALUES ('lead:terminal-not-relevant', 'Test', 'Non pertinent', ?, 'schooldrive_webhook',
                'not_relevant', 'contact_allowed', 'setting', 'warm', 'verified')
            """,
            (unique_phone(),),
        ).lastrowid
        dnc_id = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, phone_e164,
                source, lead_status, contact_status, sales_stage,
                temperature, identity_status
            ) VALUES ('lead:terminal-dnc', 'Test', 'DNC', ?, 'schooldrive_webhook',
                'eligible', 'do_not_contact', 'setting', 'warm', 'verified')
            """,
            (unique_phone(),),
        ).lastrowid
        lost_id = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, phone_e164,
                source, lead_status, contact_status, sales_stage,
                temperature, identity_status
            ) VALUES ('lead:terminal-lost', 'Test', 'Lost', ?, 'schooldrive_webhook',
                'eligible', 'contact_allowed', 'setting', 'warm', 'verified')
            """,
            (unique_phone(),),
        ).lastrowid
        conn.execute(
            """
            INSERT INTO conversations (lead_id, recipient_phone_e164, status, resolution_reason)
            VALUES (?, ?, 'resolved', 'sequence_completed_no_reply')
            """,
            (lost_id, unique_phone()),
        )

    init_db()

    with connect() as conn:
        rows = {
            row["id"]: row
            for row in conn.execute(
                """
                SELECT id, lead_status, contact_status, sales_stage
                FROM leads
                WHERE id IN (?, ?, ?, ?)
                """,
                (signed_id, not_relevant_id, dnc_id, lost_id),
            ).fetchall()
        }

    assert rows[signed_id]["sales_stage"] == "won"
    assert rows[not_relevant_id]["sales_stage"] == "not_interesting"
    assert rows[dnc_id]["sales_stage"] == "blacklist"
    assert rows[lost_id]["sales_stage"] == "lost"


def test_resolution_requires_reason_and_reopen_requires_action() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Conversation de test.")
    conversation_id = result["conversation_id"]

    ok, message = set_conversation_status(conversation_id, 1, "resolved")
    assert ok is False
    assert "motif" in message

    ok, _ = set_conversation_status(
        conversation_id,
        1,
        "resolved",
        resolution_reason="sequence_completed_no_reply",
    )
    assert ok is False
    assert "note" in _

    ok, _ = set_conversation_status(
        conversation_id,
        1,
        "resolved",
        resolution_reason="other",
        resolution_note="Cas traitÃ© manuellement.",
    )
    assert ok is True

    ok, message = set_conversation_status(conversation_id, 1, "open")
    assert ok is False
    assert "prochaine action" in message

    ok, message = set_conversation_status(
        conversation_id,
        1,
        "open",
        reopen_action_type="reply",
        reopen_assigned_to_user_id=1,
    )
    assert ok is False
    assert "note" in message


def test_reopen_refuses_terminal_lead_status() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Conversation de test.")
    update_lead_qualification(result["lead_id"], admin["id"], "won", "signed")

    ok, message = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "open",
        reopen_action_type="reply",
        reopen_assigned_to_user_id=admin["id"],
        reopen_reason="Test reopen",
    )

    assert ok is False
    assert "qualification" in message.lower()


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


def test_unknown_inbound_message_uses_french_fallback_name() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour, je veux des informations.")

    conversation = next(
        item for item in list_conversations(search=phone)
        if item["conversation_id"] == result["conversation_id"]
    )
    action = get_next_action_for_lead(result["lead_id"])

    assert conversation["first_name"] == "Inconnu(e)"
    assert conversation["last_name"] == ""
    assert "WhatsApp Unknown" not in action["title"]
    assert "Inconnu(e)" in action["title"]


def test_unknown_inbound_message_is_marked_for_identity_review() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour, je veux des informations.")

    conversation = get_conversation(result["conversation_id"])

    assert conversation["identity_status"] == "needs_identification"
    assert conversation["schooldrive_lead_id"] is None


def test_ambiguous_inbound_phone_creates_temporary_review_record() -> None:
    seed_initial_data()
    phone = unique_phone()
    with connect() as conn:
        for index in range(2):
            lead_id = conn.execute(
                """
                INSERT INTO leads (
                    schooldrive_lead_id, first_name, last_name, phone_e164,
                    source, lead_status, contact_status, sales_stage,
                    temperature, identity_status
                ) VALUES (?, ?, ?, ?, 'schooldrive_webhook', 'eligible',
                    'contact_allowed', 'new', 'warm', 'verified')
                """,
                (f"lead:test-{index}", f"Test{index}", "Ambigu", phone),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO conversations (lead_id, recipient_phone_e164, status)
                VALUES (?, ?, 'open')
                """,
                (lead_id, phone),
            )

    result = record_inbound_message(phone, "Je ne sais pas quelle fiche utiliser.")
    conversation = get_conversation(result["conversation_id"])

    assert conversation["identity_status"] == "ambiguous_identity"
    assert conversation["first_name"] == "Inconnu(e)"
    assert conversation["identity_candidates_json"]
    assert "lead:test-0" in conversation["identity_candidates_json"]
    assert "lead:test-1" in conversation["identity_candidates_json"]


def test_inbound_reuses_existing_temporary_identity_record() -> None:
    seed_initial_data()
    phone = unique_phone()
    first = record_inbound_message(phone, "Premier message.")
    second = record_inbound_message(phone, "DeuxiÃ¨me message.")

    assert second["lead_id"] == first["lead_id"]
    assert second["conversation_id"] == first["conversation_id"]


def test_temporary_identity_can_be_completed_manually() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Bonjour.")

    ok, message = update_temporary_identity(
        result["conversation_id"],
        admin["id"],
        "Samira",
        "Essai",
        "APP",
        "APP GE P26",
        "Ã€ vÃ©rifier dans SchoolDrive.",
    )

    conversation = get_conversation(result["conversation_id"])
    messages = list_messages(result["conversation_id"])

    assert ok is True
    assert "Identification" in message
    assert conversation["first_name"] == "Samira"
    assert conversation["last_name"] == "Essai"
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["course_title"] == "APP GE P26"
    assert conversation["identity_status"] == "needs_identification"
    assert any("Identification" in item["body"] for item in messages)


def test_do_not_contact_inbound_creates_contact_review() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Ne me contactez plus.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "lost",
        "eligible",
        contact_status="do_not_contact",
    )

    result = record_inbound_message(
        get_conversation(result["conversation_id"])["recipient_phone_e164"],
        "Finalement j'ai une question.",
    )

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "contact_review"
    assert action["assigned_to_role"] == "setter"


def test_manual_contact_status_lift_replaces_contact_review_with_reply() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Ne me contactez plus.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "lost",
        "eligible",
        contact_status="do_not_contact",
    )
    record_inbound_message(phone, "Finalement, je veux une réponse.")
    assert get_next_action_for_lead(result["lead_id"])["type"] == "contact_review"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "setting",
        "eligible",
        contact_status="contact_allowed",
    )

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "reply"
    active_reviews = [
        item for item in list_actions_for_lead(result["lead_id"], "all")
        if item["type"] == "contact_review" and item["status"] in {"open", "in_progress", "planned", "blocked"}
    ]
    assert active_reviews == []


def test_inbound_on_terminal_qualification_creates_review_not_reply() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour.")
    update_lead_qualification(result["lead_id"], admin["id"], "won", "signed")

    result = record_inbound_message(phone, "J'ai une autre question.")

    action = get_next_action_for_lead(result["lead_id"])
    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "open"
    assert conversation["resolved_at"] is None
    assert action["type"] == "contact_review"
    assert action["lead_status"] == "signed"
    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")
    assert ok is False
    assert "Qualification" in message


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


def test_due_followup_is_todo_not_separate_followup_queue() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Pouvez-vous me rappeler ?")
    action = get_next_action_for_lead(result["lead_id"])

    ok, _ = schedule_followup(
        result["conversation_id"],
        admin["id"],
        action["assigned_to_user_id"],
        iso_utc(utc_now() - timedelta(minutes=5)),
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "follow_up"
    conversation = next(
        item for item in list_conversations()
        if item["conversation_id"] == result["conversation_id"]
    )
    assert conversation["work_queue"] == "todo"


def test_reply_send_closes_reply_and_schedules_followup() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Bonjour, je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "reply"

    ok, _ = send_freeform_message(result["conversation_id"], action["assigned_to_user_id"], "Bonjour.")

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "follow_up"
    assert next_action["sequence_code"] == "setter_no_next_step"


def test_freeform_message_can_store_attachment(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_PUBLIC_API_BASE_URL", "https://cockpit.example.test")
    get_settings.cache_clear()
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Bonjour, je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])

    ok, message = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Voici le document.",
        attachments=[
            {
                "file_name": "brochure commerciale.pdf",
                "mime_type": "application/pdf",
                "content": b"%PDF-test",
            }
        ],
    )

    assert ok, message
    outbound = [item for item in list_messages(result["conversation_id"]) if item["direction"] == "outbound"][-1]
    assert outbound["attachments"][0]["file_name"] == "brochure commerciale.pdf"
    assert outbound["attachments"][0]["public_url"].startswith("https://cockpit.example.test/media/attachments/")
    assert " " not in outbound["attachments"][0]["public_url"]
    token_name = outbound["attachments"][0]["public_url"].rsplit("/", 1)[-1]
    download = get_attachment_download(outbound["attachments"][0]["id"], unquote(token_name))
    assert download is not None
    assert download["path"].read_bytes() == b"%PDF-test"


def test_live_freeform_attachment_requires_public_media_base(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_MODE", "live")
    monkeypatch.delenv("SALES_COCKPIT_PUBLIC_API_BASE_URL", raising=False)
    monkeypatch.delenv("SALES_COCKPIT_TWILIO_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Bonjour.")
    action = get_next_action_for_lead(result["lead_id"])

    ok, message = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Document.",
        attachments=[{"file_name": "a.txt", "mime_type": "text/plain", "content": b"test"}],
    )

    assert ok is False
    assert "PUBLIC_API_BASE_URL" in message


def test_reply_send_with_setting_booked_creates_setting_call_with_proof() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() + timedelta(hours=2))

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Parfait, mon collÃ¨gue vous appelle.",
        action_outcome="setting_booked",
        next_due_at=due_at,
        assigned_to_user_id=action["assigned_to_user_id"],
        note="RDV setting confirmÃ©.",
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"
    assert next_action["due_at"] == due_at
    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "appointment_booked"
    assert conversation["lead_status"] == "eligible"
    actions = list_actions_for_lead(result["lead_id"], "all")
    completed_reply = next(item for item in actions if item["type"] == "reply")
    assert completed_reply["outcome"] == "setting_booked"
    assert completed_reply["proof_message_id"] is not None


def test_inbound_during_planned_call_preserves_call_and_creates_reply() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() + timedelta(days=1))

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Parfait, Mihary vous appelle demain.",
        action_outcome="setting_booked",
        next_due_at=due_at,
        assigned_to_user_id=action["assigned_to_user_id"],
        note="RDV setting confirmÃ©.",
    )
    assert ok is True
    planned_call = get_next_action_for_lead(result["lead_id"])
    assert planned_call["type"] == "setting_call"

    record_inbound_message(phone, "Merci, je voulais juste confirmer.")

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"
    actions = list_actions_for_lead(result["lead_id"], "all")
    active_calls = [
        item for item in actions
        if item["type"] == "setting_call"
        and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert len(active_calls) == 1
    assert active_calls[0]["due_at"] == due_at

    ok, _ = send_freeform_message(
        result["conversation_id"],
        next_action["assigned_to_user_id"],
        "Merci, le rendez-vous reste bien confirmÃ©.",
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"
    actions = list_actions_for_lead(result["lead_id"], "all")
    active_followups = [
        item for item in actions
        if item["type"] == "follow_up"
        and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert active_followups == []


def test_reply_setting_booked_replaces_existing_closing_call() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Je veux finaliser.")
    reply = get_next_action_for_lead(result["lead_id"])
    closing_due_at = iso_utc(utc_now() + timedelta(days=1))
    ok, message = send_freeform_message(
        result["conversation_id"],
        reply["assigned_to_user_id"],
        "Yasmine vous appelle demain.",
        action_outcome="closing_booked",
        next_due_at=closing_due_at,
        note="RDV closing.",
    )
    assert ok is True, message
    assert get_next_action_for_lead(result["lead_id"])["type"] == "closing_call"

    record_inbound_message(phone, "Je préfère refaire un point avant.")
    reply = get_next_action_for_lead(result["lead_id"])
    setting_due_at = iso_utc(utc_now() + timedelta(hours=2))
    ok, message = send_freeform_message(
        result["conversation_id"],
        reply["assigned_to_user_id"],
        "Très bien, Mihary vous appelle d'abord.",
        action_outcome="setting_booked",
        next_due_at=setting_due_at,
        assigned_to_user_id=reply["assigned_to_user_id"],
        note="Retour au setting.",
    )

    assert ok is True, message
    active_calls = [
        item for item in list_actions_for_lead(result["lead_id"], "all")
        if item["type"] in {"setting_call", "closing_call"}
        and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert len(active_calls) == 1
    assert active_calls[0]["type"] == "setting_call"
    assert active_calls[0]["due_at"] == setting_due_at


def test_overdue_planned_call_does_not_hide_urgent_reply() -> None:
    seed_initial_data()
    phone = unique_phone()
    result = record_inbound_message(phone, "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() - timedelta(hours=1))

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Parfait, Mihary vous appelle.",
        action_outcome="setting_booked",
        next_due_at=due_at,
        assigned_to_user_id=action["assigned_to_user_id"],
        note="RDV setting confirmÃ©.",
    )
    assert ok is True

    record_inbound_message(phone, "Je dois prÃ©ciser quelque chose avant l'appel.")

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"
    conversation = next(
        item for item in list_conversations(search=phone)
        if item["conversation_id"] == result["conversation_id"]
    )
    assert conversation["next_action_type"] == "reply"


def test_standard_reply_assignment_preserves_planned_call_and_blocks_parallel_followup() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() + timedelta(days=1))

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Parfait, Mihary vous appelle demain.",
        action_outcome="setting_booked",
        next_due_at=due_at,
        assigned_to_user_id=action["assigned_to_user_id"],
        note="RDV setting confirmÃ©.",
    )
    assert ok is True

    users = list_users()
    setter_1 = next(item for item in users if item["email"] == "service.etudiants@essr.ch")
    tanjona = next(item for item in users if item["email"] == "setter2@essr.ch")

    ok, message = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "reply",
        setter_1["id"],
        iso_utc(utc_now()),
        "Le prospect a posÃ© une question avant l'appel.",
    )
    assert ok is True, message
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"

    actions = list_actions_for_lead(result["lead_id"], "all")
    active_calls = [
        item for item in actions
        if item["type"] == "setting_call"
        and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert len(active_calls) == 1
    assert active_calls[0]["due_at"] == due_at

    ok, message = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "follow_up",
        tanjona["id"],
        iso_utc(utc_now() + timedelta(days=3)),
        "Relance test alors qu'un appel est dÃ©jÃ  prÃ©vu.",
    )
    assert ok is False
    assert "appel" in message.lower()


def test_reply_send_with_do_not_contact_resolves_without_followup() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Ne me contactez plus.")
    action = get_next_action_for_lead(result["lead_id"])

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Bien reÃ§u, nous ne vous recontacterons plus.",
        action_outcome="do_not_contact",
        note="Demande explicite du prospect.",
    )

    assert ok is True
    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["contact_status"] == "do_not_contact"
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_followup_send_closes_with_proof_and_creates_next_sequence_step() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Bonjour.")
    action = get_next_action_for_lead(result["lead_id"])
    send_freeform_message(result["conversation_id"], action["assigned_to_user_id"], "Bonjour.")
    followup = get_next_action_for_lead(result["lead_id"])
    old_sent_at = iso_utc(utc_now() - timedelta(days=3))
    with connect() as conn:
        conn.execute(
            "UPDATE messages SET sent_at = ?, created_at = ? WHERE lead_id = ? AND direction = 'outbound'",
            (old_sent_at, old_sent_at, result["lead_id"]),
        )

    ok, _ = send_freeform_message(
        result["conversation_id"],
        followup["assigned_to_user_id"],
        "Je reviens vers vous.",
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "follow_up"
    assert next_action["sequence_step_index"] == 2
    actions = list_actions_for_lead(result["lead_id"], "all")
    completed_followup = next(
        item for item in actions
        if item["type"] == "follow_up" and item["sequence_step_index"] == 1
    )
    assert completed_followup["proof_message_id"] is not None


def test_followup_sequence_completion_sets_lost_sales_stage() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Bonjour.")
    reply = get_next_action_for_lead(result["lead_id"])
    ok, _ = send_freeform_message(result["conversation_id"], reply["assigned_to_user_id"], "Bonjour.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    ok, message = complete_action_with_workflow(
        followup["id"],
        admin["id"],
        "sequence_completed_no_reply",
        note="Fin de flux test.",
    )
    assert ok is True, message

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["sales_stage"] == "lost"
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_call_completion_requires_note() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    complete_action_with_workflow(
        action["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixÃ©.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=action["assigned_to_user_id"],
    )
    setting_action = get_next_action_for_lead(result["lead_id"])

    ok, message = complete_action_with_workflow(
        setting_action["id"],
        admin["id"],
        "not_reached",
        note="",
    )

    assert ok is False
    assert "mini note" in message


def test_template_request_blocks_followup_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux un cas trÃ¨s spÃ©cifique.")
    due_at = iso_utc(utc_now() + timedelta(hours=1))
    schedule_followup(result["conversation_id"], admin["id"], admin["id"], due_at)
    action = get_next_action_for_lead(result["lead_id"])

    ok, message = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Aucun modÃ¨le ne correspond au cas spÃ©cifique.",
        "Contexte de test",
        task_id=action["id"],
    )

    assert ok is True
    assert "mod" in message.lower()
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["status"] == "blocked"
    requests = list_template_requests()
    assert any(item["task_id"] == action["id"] for item in requests)


def test_template_request_without_followup_does_not_block_reply_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux un modÃ¨le spÃ©cifique.")
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "reply"

    ok, message = create_template_request(
        result["conversation_id"],
        admin["id"],
        "CrÃ©er un modÃ¨le de clarification.",
        "Contexte de test",
    )

    assert ok is True
    assert "relance bloquÃ©e" not in message
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["id"] == action["id"]
    assert next_action["status"] == "open"
    requests = list_template_requests()
    assert any(item["task_id"] is None for item in requests)


def test_handoff_to_closer_creates_closing_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un rendez-vous.")

    ok, _ = handoff_to_closer(
        result["conversation_id"],
        admin["id"],
        closer["id"],
        appointment_note="Disponible demain Ã  14h",
        notes="Prospect chaud.",
    )

    assert ok is True
    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "closing"
    assert conversation["lead_status"] == "eligible"
    assert conversation["closer_user_id"] == closer["id"]
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "closing_call"
    assert action["assigned_to_user_id"] == closer["id"]


def test_standard_action_assignment_creates_setting_call() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    setter = next(
        user for user in list_users()
        if user["role"] == "setter" and user["email"] != "setter2@essr.ch"
    )
    result = record_inbound_message(unique_phone(), "Je veux un appel setting.")

    ok, message = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "setting_call",
        setter["id"],
        iso_utc(utc_now()),
        "RDV setting confirme.",
    )

    assert ok is True
    assert "Action" in message
    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "appointment_booked"
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "setting_call"
    assert action["assigned_to_user_id"] == setter["id"]
    assert action["trigger_reason"] == "standard_setting_call_scheduled"


def test_standard_action_assignment_rejects_wrong_role_for_setting_call() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je veux un appel setting.")

    ok, message = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "setting_call",
        closer["id"],
        iso_utc(utc_now()),
        "Mauvais responsable de test.",
    )

    assert ok is False
    assert "Setter I" in message
    assert get_next_action_for_lead(result["lead_id"])["type"] == "reply"


def test_standard_action_assignment_creates_closing_call() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je veux parler a Yasmine.")

    ok, _ = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "closing_call",
        closer["id"],
        iso_utc(utc_now()),
        "RDV closing confirme.",
    )

    assert ok is True
    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "closing"
    assert conversation["closer_user_id"] == closer["id"]
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "closing_call"
    assert action["assigned_to_user_id"] == closer["id"]


def test_setting_call_not_reached_creates_call_retry_before_followup() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        action["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixÃ©.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=action["assigned_to_user_id"],
    )
    assert ok is True
    setting_action = get_next_action_for_lead(result["lead_id"])
    assert setting_action["type"] == "setting_call"

    ok, _ = complete_action_with_workflow(
        setting_action["id"],
        admin["id"],
        "not_reached",
        note="Pas de rÃ©ponse au tÃ©lÃ©phone.",
    )

    assert ok is True
    retry = get_next_action_for_lead(result["lead_id"])
    assert retry["type"] == "setting_call"
    assert retry["sequence_code"] == "setting_call_not_reached"
    assert retry["sequence_step_index"] == 1


def test_new_setting_appointment_after_no_show_starts_new_call_cycle() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    reply = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "setting_booked",
        note="Premier RDV setting fixé.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=reply["assigned_to_user_id"],
    )
    assert ok is True
    first_call = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        first_call["id"],
        admin["id"],
        "not_reached",
        note="Pas de réponse au premier RDV.",
    )
    assert ok is True
    first_retry = get_next_action_for_lead(result["lead_id"])
    assert first_retry["sequence_step_index"] == 1
    old_cycle_id = first_retry["call_cycle_id"]

    setter_1 = next(user for user in list_users() if user["email"] == "service.etudiants@essr.ch")
    ok, message = assign_standard_next_action(
        result["conversation_id"],
        admin["id"],
        "setting_call",
        setter_1["id"],
        iso_utc(utc_now() + timedelta(days=1)),
        "Nouveau RDV fixé après reprise de contact.",
    )
    assert ok is True, message
    new_call = get_next_action_for_lead(result["lead_id"])
    assert new_call["type"] == "setting_call"
    assert new_call["call_attempt_index"] == 1
    assert new_call["call_cycle_id"] != old_cycle_id

    ok, _ = complete_action_with_workflow(
        new_call["id"],
        admin["id"],
        "not_reached",
        note="Pas de réponse sur le nouveau RDV.",
    )
    assert ok is True
    new_retry = get_next_action_for_lead(result["lead_id"])
    assert new_retry["sequence_code"] == "setting_call_not_reached"
    assert new_retry["sequence_step_index"] == 1
    assert new_retry["call_attempt_index"] == 2
    assert new_retry["call_cycle_id"] == new_call["call_cycle_id"]


def test_seed_includes_setter2_and_demo_templates() -> None:
    seed_initial_data()
    users = list_users(active_only=False)
    assert any(
        user["email"] == "setter2@essr.ch" and user["full_name"] == "Tanjona"
        for user in users
    )
    templates = list_templates("demo_")
    assert len(templates) >= 10


def test_only_admin_can_create_template() -> None:
    seed_initial_data()
    setter = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")

    try:
        create_template(
            setter["id"],
            "setter_should_not_create",
            "Bonjour {{first_name}}",
            placeholders={"first_name": "Camille"},
        )
    except PermissionError as exc:
        assert "admins" in str(exc)
    else:
        raise AssertionError("Non-admin template creation should fail.")


def test_sync_twilio_templates_upserts_content_sid(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_ACCOUNT_SID", "TWILIO_TEST_ACCOUNT_FOR_MASKING")
    get_settings.cache_clear()
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    remote = TwilioContentTemplate(
        content_sid="HX1234567890abcdef1234567890abcdef",
        name="twilio_relance_test",
        language="fr",
        category="utility",
        body="Bonjour {{first_name}}, ceci est un test.",
        status="approved",
        content_type="twilio/text",
        variables={"first_name": "Camille"},
        payload={"sid": "HX1234567890abcdef1234567890abcdef"},
    )
    monkeypatch.setattr("sales_cockpit.store.list_twilio_templates", lambda: [remote])

    ok, message = sync_twilio_templates(admin["id"])

    assert ok is True
    assert "Synchronisation" in message
    templates = list_templates("twilio_relance_test")
    assert len(templates) == 1
    assert templates[0]["twilio_content_sid"] == "HX1234567890abcdef1234567890abcdef"
    assert templates[0]["status"] == "approved"

    ok, message = sync_twilio_templates(admin["id"])

    assert ok is True
    assert "0 créé(s), 0 modifié(s), 1 inchangé(s)" in message
    assert "TWILIO...KING" in message


def test_business_rule_seed_migrates_existing_sequence_rows() -> None:
    seed_initial_data()
    with connect() as conn:
        conn.execute(
            "UPDATE sequence_steps SET delay = '+999h', offset_amount = 999 WHERE sequence_code = 'lead_no_reply' AND step_index = 2"
        )
        conn.execute(
            """
            INSERT INTO sequences (code, label, timeline, trigger, owner, stop_when, active)
            VALUES (
                'post_call_undecided',
                'Ancien post-appel indécis',
                'Legacy',
                'Legacy',
                'Setter II',
                'Legacy',
                1
            )
            ON CONFLICT(code) DO NOTHING
            """
        )
        sequence_id = conn.execute(
            "SELECT id FROM sequences WHERE code = 'post_call_undecided'"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO sequence_steps (
                sequence_id, sequence_code, step_index, delay, action_type,
                offset_direction, offset_amount, offset_unit, requires_template, meaning, active
            ) VALUES (?, 'post_call_undecided', 1, '+72h', 'follow_up', 'after', 72, 'hours', 1, 'Legacy', 1)
            ON CONFLICT(sequence_code, step_index) DO UPDATE SET active = 1
            """,
            (sequence_id,),
        )
        template_id = conn.execute(
            "SELECT id FROM whatsapp_templates WHERE status = 'approved' ORDER BY id LIMIT 1"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO sequence_template_mappings (
                sequence_code, sequence_step_index, lead_type, course_category,
                template_id, note, active
            ) VALUES ('post_call_undecided', 1, 'all', 'APP', ?, 'Legacy mapping', 1)
            ON CONFLICT(sequence_code, sequence_step_index, lead_type, course_category)
            DO UPDATE SET active = 1
            """,
            (template_id,),
        )
        conn.execute(
            "UPDATE app_metadata SET value = 'old-version' WHERE key = 'business_rules_version'"
        )

    seed_initial_data()

    lead_steps = list_sequence_steps("lead_no_reply", active_only=False)
    step_2 = next(step for step in lead_steps if step["step_index"] == 2)
    assert step_2["delay"] == "T+6j"
    assert step_2["offset_amount"] == 6
    assert step_2["offset_unit"] == "days"
    old_steps = list_sequence_steps("post_call_undecided", active_only=False)
    assert old_steps
    assert all(step["active"] == 0 for step in old_steps)
    with connect() as conn:
        old_mapping_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sequence_template_mappings WHERE sequence_code = 'post_call_undecided' AND active = 1"
        ).fetchone()["count"]
        migrated_mapping_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM sequence_template_mappings
            WHERE sequence_code IN ('post_setting_undecided', 'post_closing_undecided')
              AND sequence_step_index = 1
              AND course_category = 'APP'
              AND active = 1
            """
        ).fetchone()["count"]
    assert old_mapping_count == 0
    assert migrated_mapping_count == 2


def test_sync_twilio_templates_auto_unblocks_linked_template_request(monkeypatch) -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux une réponse précise.")
    ok, _ = send_freeform_message(result["conversation_id"], admin["id"], "Je reviens vers vous.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    ok, _ = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Créer twilio_template_special",
        "twilio_template_special pour ce cas.",
        task_id=followup["id"],
    )
    assert ok is True
    request = next(item for item in list_template_requests() if item["task_id"] == followup["id"])
    assert get_next_action_for_lead(result["lead_id"])["status"] == "blocked"

    remote = TwilioContentTemplate(
        content_sid="HXcccccccccccccccccccccccccccccccc",
        name="twilio_template_special",
        language="fr",
        category="utility",
        body="Bonjour {{first_name}}, voici la réponse.",
        status="approved",
        content_type="twilio/text",
        variables={"first_name": "Camille"},
        payload={"sid": "HXcccccccccccccccccccccccccccccccc"},
    )
    monkeypatch.setattr("sales_cockpit.store.list_twilio_templates", lambda: [remote])

    ok, message = sync_twilio_templates(admin["id"])

    assert ok is True
    assert "1 demande" in message
    unblocked = get_next_action_for_lead(result["lead_id"])
    assert unblocked["id"] == followup["id"]
    assert unblocked["status"] == "open"
    updated_request = next(item for item in list_template_requests() if item["id"] == request["id"])
    assert updated_request["status"] == "approved"
    assert not [
        item for item in list_admin_actions()
        if item.get("template_request_id") == request["id"]
    ]


def test_other_review_completion_creates_fallback_reply_when_no_action_remains() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Cas à revoir.")
    reply = get_next_action_for_lead(result["lead_id"])
    with connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', outcome = 'test setup' WHERE id = ?",
            (reply["id"],),
        )
    other_id = create_next_action(
        result["lead_id"],
        result["conversation_id"],
        "other",
        "Revoir catégorie non renseignée",
        admin["id"],
        admin["id"],
        due_at=iso_utc(),
        description="Revue humaine.",
        trigger_reason="test_review",
    )

    ok, message = complete_action_with_workflow(other_id, admin["id"], "done", note="Revue faite.")

    assert ok is True, message
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"
    assert next_action["trigger_reason"] == "human_review_completed_requires_next_action"


def test_twilio_content_read_only_blocks_remote_template_creation(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_CONTENT_READ_ONLY", "true")
    get_settings.cache_clear()
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    ok, message, template_id = create_and_submit_twilio_template(
        admin["id"],
        "should_not_touch_twilio",
        "Bonjour {{first_name}}",
        placeholders={"first_name": "Camille"},
    )

    assert ok is False
    assert template_id is None
    assert "lecture seule" in message


def test_sequence_template_mapping_recommends_matching_twilio_template(monkeypatch) -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    remote = TwilioContentTemplate(
        content_sid="HXaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        name="app_relance_1",
        language="fr",
        category="utility",
        body="Bonjour {{first_name}}, relance APP.",
        status="approved",
        content_type="twilio/text",
        variables={"first_name": "Camille"},
        payload={"sid": "HXaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    )
    monkeypatch.setattr("sales_cockpit.store.list_twilio_templates", lambda: [remote])
    sync_twilio_templates(admin["id"])
    template = list_templates("app_relance_1")[0]

    result = record_inbound_message(unique_phone(), "Bonjour, je veux des infos APP.")
    action = get_next_action_for_lead(result["lead_id"])
    ok, _ = schedule_followup(
        result["conversation_id"],
        admin["id"],
        action["assigned_to_user_id"],
        iso_utc(utc_now() + timedelta(hours=72)),
    )
    assert ok is True
    action = get_next_action_for_lead(result["lead_id"])
    with connect() as conn:
        conn.execute(
            """
            UPDATE leads
            SET lead_type = 'lead', course_category_short_title = 'APP'
            WHERE id = ?
            """,
            (result["lead_id"],),
        )
        conn.execute(
            """
            UPDATE tasks
            SET sequence_code = 'lead_no_reply', sequence_step_index = 1
            WHERE id = ?
            """,
            (action["id"],),
        )

    ok, message = upsert_sequence_template_mapping(
        admin["id"],
        "lead_no_reply",
        1,
        "lead",
        "APP",
        template["id"],
        "Relance APP 1",
    )

    assert ok is True
    assert "enregistr" in message.lower()
    assert len(list_sequence_template_mappings()) == 1
    recommended = get_recommended_template_for_action(action["id"])
    assert recommended is not None
    assert recommended["template_id"] == template["id"]
    assert recommended["template_name"] == "app_relance_1"


def test_sequence_template_mapping_rejects_non_approved_or_demo_template() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    draft_id = create_template(
        admin["id"],
        "draft_relance",
        "Bonjour {{first_name}}",
        status="draft",
        twilio_content_sid="HXbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    demo_id = create_template(
        admin["id"],
        "demo_relance",
        "Bonjour {{first_name}}",
        status="approved",
        twilio_content_sid="HX_MOCK_demo_relance",
    )

    ok, message = upsert_sequence_template_mapping(
        admin["id"],
        "lead_no_reply",
        1,
        "lead",
        "APP",
        draft_id,
    )
    assert ok is False
    assert "approuv" in message

    ok, message = upsert_sequence_template_mapping(
        admin["id"],
        "lead_no_reply",
        1,
        "lead",
        "APP",
        demo_id,
    )
    assert ok is False
    assert "approuv" in message


def test_sequence_steps_can_be_added_updated_and_deactivated() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    before = list_sequence_steps("lead_no_reply", active_only=False)
    ok, message = add_sequence_step(
        admin["id"],
        "lead_no_reply",
        "Relance longue de test.",
        action_type="follow_up",
        offset_direction="after",
        offset_amount=14,
        offset_unit="days",
    )
    assert ok is True
    assert "ajout" in message

    steps = list_sequence_steps("lead_no_reply", active_only=False)
    assert len(steps) == len(before) + 1
    added = steps[-1]
    assert added["delay"] == "T+14j"
    assert added["action_type"] == "follow_up"
    assert added["offset_amount"] == 14
    assert added["offset_unit"] == "days"
    assert added["requires_template"] == 1

    ok, message = upsert_sequence_step(
        admin["id"],
        "lead_no_reply",
        int(added["step_index"]),
        "Relance longue ajustÃ©e.",
        action_type="other",
        offset_direction="after",
        offset_amount=7,
        offset_unit="days",
    )
    assert ok is True
    updated = list_sequence_steps("lead_no_reply", active_only=False)[-1]
    assert updated["delay"] == "T+7j"
    assert updated["action_type"] == "other"
    assert updated["meaning"] == "Relance longue ajustÃ©e."
    assert updated["requires_template"] == 0

    ok, message = deactivate_sequence_step(admin["id"], int(updated["id"]))
    assert ok is True
    active_ids = {item["id"] for item in list_sequence_steps("lead_no_reply")}
    assert updated["id"] not in active_ids


def test_readiness_allows_existing_followup_on_inactive_sequence_step() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    users = {item["email"]: item for item in list_users()}
    conv = next(item for item in list_conversations() if item["conversation_status"] == "open")
    step = next(item for item in list_sequence_steps("lead_no_reply") if item["step_index"] == 1)

    action_id = create_next_action(
        conv["lead_id"],
        conv["conversation_id"],
        "follow_up",
        "Relance existante sur étape ensuite désactivée",
        users["setter2@essr.ch"]["id"],
        admin["id"],
        due_at=iso_utc(),
        sequence_code="lead_no_reply",
        sequence_step_index=1,
    )
    ok, message = deactivate_sequence_step(admin["id"], int(step["id"]))
    assert ok, message

    readiness = get_integration_readiness()
    assert readiness["workflow"]["active_followup_missing_step_count"] == 0

    with connect() as conn:
        conn.execute("UPDATE tasks SET sequence_step_index = 999 WHERE id = ?", (action_id,))

    readiness = get_integration_readiness()
    assert readiness["workflow"]["active_followup_missing_step_count"] == 1


def test_course_default_session_can_be_configured_and_deactivated() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    ok, message = upsert_course_default_session(
        admin["id"],
        "app",
        "APP VISIO E26",
        "2026-07-11",
        default_session_name="APP Ã©tÃ© 2026",
        schooldrive_url="https://schooldrive.essr.ch/sd/example",
        note="Session par dÃ©faut pour les leads APP.",
    )

    assert ok is True
    assert "enregistr" in message
    sessions = list_course_default_sessions()
    assert len(sessions) == 1
    assert sessions[0]["course_category"] == "APP"
    assert sessions[0]["default_course_name"] == "APP VISIO E26"
    assert sessions[0]["default_start_date"] == "2026-07-11"

    ok, message = deactivate_course_default_session(admin["id"], sessions[0]["id"])

    assert ok is True
    assert "sactiv" in message
    assert list_course_default_sessions() == []


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
        "eligible",
        contact_status="do_not_contact",
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


def test_status_tab_updates_terminal_statuses_and_sales_stage_together() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    signed = record_inbound_message(unique_phone(), "Je vais signer.")
    update_lead_qualification(
        signed["lead_id"],
        admin["id"],
        "setting",
        "signed",
        contact_status="contact_allowed",
        honor_sales_stage_terminal_mapping=False,
    )
    signed_conversation = get_conversation(signed["conversation_id"])
    assert signed_conversation["status"] == "resolved"
    assert signed_conversation["lead_status"] == "signed"
    assert signed_conversation["sales_stage"] == "won"

    not_relevant = record_inbound_message(unique_phone(), "Ce n'est pas pour moi.")
    update_lead_qualification(
        not_relevant["lead_id"],
        admin["id"],
        "setting",
        "not_relevant",
        contact_status="contact_allowed",
        honor_sales_stage_terminal_mapping=False,
    )
    not_relevant_conversation = get_conversation(not_relevant["conversation_id"])
    assert not_relevant_conversation["status"] == "resolved"
    assert not_relevant_conversation["lead_status"] == "not_relevant"
    assert not_relevant_conversation["sales_stage"] == "not_interesting"

    do_not_contact = record_inbound_message(unique_phone(), "Stop.")
    update_lead_qualification(
        do_not_contact["lead_id"],
        admin["id"],
        "setting",
        "eligible",
        contact_status="do_not_contact",
        honor_sales_stage_terminal_mapping=False,
    )
    do_not_contact_conversation = get_conversation(do_not_contact["conversation_id"])
    assert do_not_contact_conversation["status"] == "resolved"
    assert do_not_contact_conversation["contact_status"] == "do_not_contact"
    assert do_not_contact_conversation["lead_status"] == "eligible"
    assert do_not_contact_conversation["sales_stage"] == "blacklist"


def test_status_tab_can_lift_do_not_contact_without_reapplying_blacklist() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Ne me contactez plus.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "setting",
        "eligible",
        contact_status="do_not_contact",
        honor_sales_stage_terminal_mapping=False,
    )
    assert get_conversation(result["conversation_id"])["sales_stage"] == "blacklist"
    assert get_next_action_for_lead(result["lead_id"]) is None

    record_inbound_message(phone, "Finalement vous pouvez me répondre.")
    review = get_next_action_for_lead(result["lead_id"])
    assert review["type"] == "contact_review"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "blacklist",
        "eligible",
        contact_status="contact_allowed",
        honor_sales_stage_terminal_mapping=False,
    )

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "open"
    assert conversation["contact_status"] == "contact_allowed"
    assert conversation["sales_stage"] == "setting"
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"


def test_contact_review_lift_do_not_contact_resets_blocked_stage() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Ne me contactez plus.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "setting",
        "eligible",
        contact_status="do_not_contact",
        honor_sales_stage_terminal_mapping=False,
    )

    record_inbound_message(phone, "Vous pouvez me répondre.")
    review = get_next_action_for_lead(result["lead_id"])
    assert review["type"] == "contact_review"

    ok, message = complete_action_with_workflow(
        review["id"],
        admin["id"],
        "lift_do_not_contact",
        note="Le prospect relance lui-même la conversation.",
    )
    assert ok is True, message

    conversation = get_conversation(result["conversation_id"])
    assert conversation["contact_status"] == "contact_allowed"
    assert conversation["sales_stage"] == "setting"
    assert get_next_action_for_lead(result["lead_id"])["type"] == "reply"


def test_forced_closing_stage_updates_next_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux parler Ã  Yasmine.")
    assert get_next_action_for_lead(result["lead_id"])["type"] == "reply"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "closing",
        "eligible",
        contact_status="contact_allowed",
    )

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "closing_call"
    assert next_action["assigned_to_role"] == "closer"


def test_will_sign_status_updates_next_action_to_setter2_followup() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je pense signer.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "closing",
        "will_sign",
        contact_status="contact_allowed",
    )

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "follow_up"
    assert next_action["assigned_to_email"] == "setter2@essr.ch"
    assert next_action["sequence_code"] == "closer_will_sign"
    assert get_conversation(result["conversation_id"])["sales_stage"] == "will_sign"


def test_forced_stage_overrides_will_sign_next_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je pense signer.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "closing",
        "will_sign",
        contact_status="contact_allowed",
    )
    assert get_next_action_for_lead(result["lead_id"])["type"] == "follow_up"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "appointment_booked",
        "will_sign",
        contact_status="contact_allowed",
    )

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"


def test_forced_appointment_stage_wins_when_will_sign_changes_same_update() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je pense signer mais il faut un setting.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "appointment_booked",
        "will_sign",
        contact_status="contact_allowed",
    )

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"
    assert next_action["trigger_reason"] == "sales_stage_forced_appointment_booked"
    assert next_action["sequence_code"] is None


def test_do_not_contact_blocks_freeform_and_template_send() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je reviens malgrÃ© le blocage.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "setting",
        "eligible",
        contact_status="do_not_contact",
    )

    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")
    assert ok is False
    assert "Contact" in message

    template = next(item for item in list_templates(approved_only=True))
    ok, message = send_template_message(result["conversation_id"], admin["id"], template["id"], {})
    assert ok is False
    assert "Contact" in message


def test_resolved_conversation_blocks_freeform_and_template_send() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Question apres cloture.")

    ok, _ = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "resolved",
        resolution_reason="other",
        resolution_note="Test cloture.",
    )
    assert ok is True

    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")
    assert ok is False
    assert "Conversation" in message
    assert "avant tout envoi" in message

    template = next(item for item in list_templates(approved_only=True))
    ok, message = send_template_message(result["conversation_id"], admin["id"], template["id"], {})
    assert ok is False
    assert "Conversation" in message
    assert "avant tout envoi" in message


def test_resolved_conversation_blocks_new_work_shortcuts() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Conversation a terminer.")

    ok, _ = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "resolved",
        resolution_reason="other",
        resolution_note="Test cloture.",
    )
    assert ok is True

    ok, message = schedule_followup(
        result["conversation_id"],
        admin["id"],
        admin["id"],
        iso_utc(utc_now()),
    )
    assert ok is False
    assert "activez" in message

    ok, message = handoff_to_closer(
        result["conversation_id"],
        admin["id"],
        closer["id"],
    )
    assert ok is False
    assert "activez" in message


def test_qualification_noop_does_not_replace_followup_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Merci pour les infos.")

    ok, _ = send_freeform_message(result["conversation_id"], admin["id"], "Je reviens vers vous.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "new",
        "eligible",
        contact_status="contact_allowed",
    )

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["id"] == followup["id"]
    assert next_action["type"] == "follow_up"


def test_reply_can_create_closing_call_directly() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je veux parler au closer.")

    ok, _ = send_freeform_message(
        result["conversation_id"],
        admin["id"],
        "Parfait, Yasmine vous appelle demain.",
        action_outcome="closing_booked",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=closer["id"],
        note="RDV closing fixe directement.",
    )
    assert ok is True

    conversation = get_conversation(result["conversation_id"])
    assert conversation["sales_stage"] == "closing"
    assert conversation["closer_user_id"] == closer["id"]
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "closing_call"
    assert action["assigned_to_user_id"] == closer["id"]


def test_blocked_followup_cannot_be_closed_by_unrelated_template_send() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je ne reponds plus.")

    ok, _ = send_freeform_message(result["conversation_id"], admin["id"], "Je reste disponible.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    ok, _ = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Modele specifique manquant.",
        "Contexte de relance.",
    )
    assert ok is True
    blocked = get_next_action_for_lead(result["lead_id"])
    assert blocked["status"] == "blocked"
    request = next(item for item in list_template_requests() if item["task_id"] == blocked["id"])
    admin_action = next(
        item for item in list_admin_actions()
        if item.get("template_request_id") == request["id"]
    )
    assert admin_action["type"] == "template_request"

    template = next(item for item in list_templates(approved_only=True))
    ok, message = send_template_message(result["conversation_id"], admin["id"], template["id"], {})
    assert ok is False
    assert "Relance" in message
    assert get_next_action_for_lead(result["lead_id"])["status"] == "blocked"

    approved_template_id = create_template(
        user_id=admin["id"],
        name="relance_demande_specifique",
        body="Bonjour, je reviens vers vous avec la bonne information.",
        status="approved",
        language="fr",
        category="utility",
        placeholders={},
        twilio_content_sid="HXaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    ok, _ = update_template_request_status(
        request["id"], admin["id"], "approved", approved_template_id
    )
    assert ok is True
    unblocked = get_next_action_for_lead(result["lead_id"])
    assert unblocked["status"] == "open"
    assert not [
        item for item in list_admin_actions()
        if item.get("template_request_id") == request["id"]
    ]


def test_blocked_followup_can_be_sent_with_recommended_approved_template() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je cherche une solution specifique.")

    ok, _ = send_freeform_message(result["conversation_id"], admin["id"], "Je regarde.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    old_sent_at = iso_utc(utc_now() - timedelta(days=4))
    with connect() as conn:
        conn.execute(
            """
            UPDATE leads
            SET lead_type = 'lead', course_category_short_title = 'FSM'
            WHERE id = ?
            """,
            (result["lead_id"],),
        )
        conn.execute(
            """
            UPDATE messages
            SET sent_at = ?, created_at = ?
            WHERE lead_id = ? AND direction = 'outbound'
            """,
            (old_sent_at, old_sent_at, result["lead_id"]),
        )
        conn.execute(
            """
            UPDATE conversations
            SET last_outbound_at = ?
            WHERE id = ?
            """,
            (old_sent_at, result["conversation_id"]),
        )
        conn.execute(
            """
            UPDATE tasks
            SET sequence_code = 'lead_no_reply',
                sequence_step_index = 1,
                due_at = ?
            WHERE id = ?
            """,
            (iso_utc(utc_now() - timedelta(hours=1)), followup["id"]),
        )

    template_id = create_template(
        user_id=admin["id"],
        name="relance_places_fsm_test",
        body="Bonjour, il reste des places pour la formation FSM.",
        status="approved",
        language="fr",
        category="marketing",
        placeholders={},
        twilio_content_sid="HXbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    ok, message = upsert_sequence_template_mapping(
        admin["id"],
        "lead_no_reply",
        1,
        "lead",
        "FSM",
        template_id,
        "Relance FSM test",
    )
    assert ok is True, message

    ok, _ = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Modele specifique demande.",
        "Contexte de relance.",
        task_id=followup["id"],
    )
    assert ok is True
    blocked = get_next_action_for_lead(result["lead_id"])
    assert blocked["status"] == "blocked"
    recommended = get_recommended_template_for_action(blocked["id"])
    assert recommended["template_id"] == template_id

    ok, message = send_template_message(result["conversation_id"], admin["id"], template_id, {})

    assert ok is True, message
    actions = list_actions_for_lead(result["lead_id"], "all")
    assert next(item for item in actions if item["id"] == blocked["id"])["status"] == "done"
    assert not [
        item for item in actions
        if item["status"] == "blocked" and item["blocked_reason"] == "template_missing"
    ]


def test_call_completion_note_is_visible_in_conversation() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Appelez-moi demain.")
    reply = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixÃ© demain.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=reply["assigned_to_user_id"],
    )
    assert ok is True
    setting_call = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        setting_call["id"],
        admin["id"],
        "not_ready",
        note="Client joint, pas prÃªt Ã  dÃ©cider.",
    )
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"
    assert followup["sequence_code"] == "post_setting_undecided"

    notes = [
        item["body"]
        for item in list_messages(result["conversation_id"])
        if item["direction"] == "manual_note"
    ]
    assert any("Note d'appel setting" in body for body in notes)


def test_terminal_stage_resolves_and_clears_next_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Finalement je ne continue pas.")

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "lost",
        "eligible",
        contact_status="contact_allowed",
    )

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["lead_status"] == "not_relevant"
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_call_can_be_rescheduled_then_cancelled_into_indecis_flow() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux un appel.")
    reply = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixe.",
        next_due_at=iso_utc(utc_now() + timedelta(days=1)),
        assigned_to_user_id=reply["assigned_to_user_id"],
    )
    assert ok is True
    call = get_next_action_for_lead(result["lead_id"])
    new_due = iso_utc(utc_now() + timedelta(days=2, minutes=7))
    ok, _ = reschedule_call_action(call["id"], admin["id"], new_due, "RDV deplace a la demande du prospect.")
    assert ok is True
    call = get_next_action_for_lead(result["lead_id"])
    assert call["due_at"] == new_due

    ok, _ = cancel_call_action_without_replacement(call["id"], admin["id"], "Prospect annule sans nouveau creneau.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"
    assert followup["sequence_code"] == "post_setting_undecided"
    notes = [item["body"] for item in list_messages(result["conversation_id"]) if item["direction"] == "manual_note"]
    assert any("RDV annul" in body for body in notes)


def test_closing_undecided_uses_dedicated_flow_and_do_not_contact_resolves() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    closer = next(user for user in list_users() if user["role"] == "closer")
    result = record_inbound_message(unique_phone(), "Je veux parler au closer.")
    reply = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "closing_booked",
        note="RDV closing fixe.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=closer["id"],
    )
    assert ok is True
    closing_call = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        closing_call["id"],
        admin["id"],
        "undecided",
        note="Prospect joint mais encore hesitant.",
    )
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"
    assert followup["sequence_code"] == "post_closing_undecided"

    result = record_inbound_message(unique_phone(), "Ne me contactez plus.")
    reply = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "closing_booked",
        note="RDV closing fixe.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=closer["id"],
    )
    assert ok is True
    closing_call = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        closing_call["id"],
        admin["id"],
        "do_not_contact",
        note="Le prospect demande explicitement de ne plus etre contacte.",
    )
    assert ok is True
    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["contact_status"] == "do_not_contact"


def test_schooldrive_business_signals_stop_or_route_work() -> None:
    seed_initial_data()
    signed_payload = schooldrive_signal_payload({"signed": {"is_signed": True}})
    signed_result = ingest_schooldrive_snapshot(signed_payload)
    signed_conversation = conversation_for_lead(signed_result["lead_id"])
    assert signed_conversation["status"] == "resolved"
    assert signed_conversation["lead_status"] == "signed"
    assert signed_conversation["sales_stage"] == "won"
    assert get_next_action_for_lead(signed_result["lead_id"]) is None

    dnc_payload = schooldrive_signal_payload({"contact": {"email_opt_out": True}})
    dnc_result = ingest_schooldrive_snapshot(dnc_payload)
    dnc_conversation = conversation_for_lead(dnc_result["lead_id"])
    assert dnc_conversation["status"] == "resolved"
    assert dnc_conversation["contact_status"] == "do_not_contact"
    assert dnc_conversation["sales_stage"] == "blacklist"
    assert get_next_action_for_lead(dnc_result["lead_id"]) is None

    course_full_payload = schooldrive_signal_payload({"course": {"category": "APP", "course_name": "APP TEST", "is_full": True}})
    course_full_result = ingest_schooldrive_snapshot(course_full_payload)
    next_action = get_next_action_for_lead(course_full_result["lead_id"])
    assert next_action["type"] == "other"
    assert next_action["trigger_reason"] == "schooldrive_course_full"
    ok, _ = complete_action_with_workflow(next_action["id"], 1, "done", note="Autre session proposee.")
    assert ok is True


def test_course_full_keeps_planned_call_as_primary_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    schooldrive_id = f"lead:{uuid4().hex[:8]}"
    result = record_inbound_message(unique_phone(), "Je veux un appel avant de choisir la session.")
    with connect() as conn:
        conn.execute(
            "UPDATE leads SET schooldrive_lead_id = ?, course_category_short_title = 'APP' WHERE id = ?",
            (schooldrive_id, result["lead_id"]),
        )
    reply = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixé.",
        next_due_at=iso_utc(utc_now() + timedelta(days=1)),
        assigned_to_user_id=reply["assigned_to_user_id"],
    )
    assert ok is True
    call = get_next_action_for_lead(result["lead_id"])

    payload = schooldrive_signal_payload(
        {
            "schooldrive_id": schooldrive_id,
            "course": {"category": "APP", "course_name": "APP TEST", "is_full": True},
        }
    )
    ingest_schooldrive_snapshot(payload)

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["id"] == call["id"]
    assert next_action["type"] == "setting_call"
    assert "session est complète" in (next_action["description"] or "")
    active_other = [
        item for item in list_actions_for_lead(result["lead_id"], "all")
        if item["type"] == "other" and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert active_other == []


def test_past_default_session_creates_admin_review_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    ok, _ = upsert_course_default_session(
        admin["id"],
        "APP",
        "APP ancienne session",
        "2026-01-01",
        default_session_name="APP ancienne",
    )
    assert ok is True

    payload = schooldrive_signal_payload(
        {
            "course": {"category": "APP", "course_name": None, "start_date": None},
            "whatsapp_autoresponders": [
                {
                    "message_id": f"armsg:{uuid4().hex[:8]}",
                    "autoresponder_id": 1,
                    "short_name": "MKT-APP-TEST",
                    "whatsapp_template_id": "HXdddddddddddddddddddddddddddddddd",
                    "whatsapp_template_variables_mapping": {"first_name": "Test"},
                    "whatsapp_send_body": "Bonjour.",
                    "status": "sent",
                    "sent_at": iso_utc(utc_now()),
                }
            ],
        }
    )
    ingest_schooldrive_snapshot(payload)

    admin_actions = [
        item for item in list_admin_actions()
        if item["type"] == "default_session_review"
    ]
    assert len(admin_actions) == 1
    assert "APP" in admin_actions[0]["title"]


def test_outbound_safeguards_can_block_whatsapp_sends() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    ok, _ = update_outbound_safeguards(admin["id"], {"outbound_global_block": True})
    assert ok is True
    assert get_outbound_safeguards()["outbound_global_block"] is True
    result = record_inbound_message(unique_phone(), "Bonjour.")

    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")
    assert ok is False
    assert "kill switch" in message


def test_followup_quota_blocks_followup_but_allows_human_reply() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour.")
    reply = get_next_action_for_lead(result["lead_id"])
    ok, _ = send_freeform_message(result["conversation_id"], reply["assigned_to_user_id"], "Bonjour.")
    assert ok is True
    ok, _ = update_outbound_safeguards(admin["id"], {"outbound_max_per_lead_day": 1})
    assert ok is True

    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"
    ok, message = send_freeform_message(result["conversation_id"], followup["assigned_to_user_id"], "Relance.")
    assert ok is False
    assert "limite quotidienne" in message

    record_inbound_message(phone, "Je réponds finalement.")
    reply = get_next_action_for_lead(result["lead_id"])
    assert reply["type"] == "reply"
    ok, message = send_freeform_message(result["conversation_id"], reply["assigned_to_user_id"], "Merci.")
    assert ok is True, message


def test_freeform_followup_is_not_blocked_by_min_followup_delay() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour.")
    reply = get_next_action_for_lead(result["lead_id"])
    ok, message = send_freeform_message(
        result["conversation_id"],
        reply["assigned_to_user_id"],
        "Bonjour, je vous réponds.",
    )
    assert ok is True, message
    ok, _ = update_outbound_safeguards(admin["id"], {"outbound_min_followup_hours": 24})
    assert ok is True

    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"
    ok, message = send_freeform_message(
        result["conversation_id"],
        followup["assigned_to_user_id"],
        "Je complète ma réponse pendant que la fenêtre est ouverte.",
    )

    assert ok is True, message


def test_inbound_cancels_blocked_followup_and_creates_reply() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = unique_phone()
    result = record_inbound_message(phone, "Bonjour.")
    reply = get_next_action_for_lead(result["lead_id"])
    ok, _ = send_freeform_message(result["conversation_id"], reply["assigned_to_user_id"], "Bonjour.")
    assert ok is True
    followup = get_next_action_for_lead(result["lead_id"])
    ok, _ = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Modèle manquant pour relance.",
        "Contexte.",
        task_id=followup["id"],
    )
    assert ok is True
    request = next(item for item in list_template_requests() if item["task_id"] == followup["id"])
    assert get_next_action_for_lead(result["lead_id"])["status"] == "blocked"

    record_inbound_message(phone, "Je viens de répondre.")

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "reply"
    blocked_followups = [
        item for item in list_actions_for_lead(result["lead_id"], "all")
        if item["type"] == "follow_up" and item["status"] == "blocked"
    ]
    assert blocked_followups == []
    updated_request = next(item for item in list_template_requests("all") if item["id"] == request["id"])
    assert updated_request["status"] == "cancelled"
    assert not [
        item for item in list_admin_actions()
        if item.get("template_request_id") == request["id"]
    ]


def test_outbox_keeps_send_error_message_when_twilio_fails(monkeypatch) -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Bonjour.")

    class FailingClient:
        def send_freeform(self, to_phone: str, body: str, media_urls=None):
            raise TwilioMessageError("temporary Twilio failure")

    monkeypatch.setattr("sales_cockpit.store.get_whatsapp_client", lambda: FailingClient())

    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")

    assert ok is False
    assert "Twilio" in message
    messages = list_messages(result["conversation_id"])
    failed = [item for item in messages if item["direction"] == "outbound"]
    assert len(failed) == 1
    assert failed[0]["twilio_status"] == "send_error"
    assert failed[0]["twilio_error_message"] == "temporary Twilio failure"


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:8]


def conversation_for_lead(lead_id: int) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
    assert row is not None
    conversation = get_conversation(row["id"])
    assert conversation is not None
    return conversation


def schooldrive_signal_payload(data_patch: dict) -> dict:
    payload = build_smoke_steps(
        run_id=uuid4().hex[:8],
        environment="staging",
        base_time=utc_now(),
    )[0].payload
    now = iso_utc(utc_now())
    payload["event_id"] = f"evt_{uuid4().hex}"
    payload["occurred_at"] = now
    payload["data"]["schooldrive_id"] = f"lead:{uuid4().hex[:8]}"
    payload["data"]["aggregated_updated_at"] = now
    payload["data"]["person"]["phone"] = unique_phone()
    for key, value in data_patch.items():
        if isinstance(value, dict) and isinstance(payload["data"].get(key), dict):
            payload["data"][key].update(value)
        else:
            payload["data"][key] = value
    return payload
