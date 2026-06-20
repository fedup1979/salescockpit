from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data
from sales_cockpit.services.twilio_content import TwilioContentTemplate
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import (
    assign_standard_next_action,
    authenticate,
    complete_action_with_workflow,
    create_and_submit_twilio_template,
    create_bug_report,
    create_template,
    create_template_request,
    add_sequence_step,
    deactivate_sequence_step,
    deactivate_course_default_session,
    get_conversation,
    get_integration_readiness,
    get_next_action_for_lead,
    get_recommended_template_for_action,
    ingest_schooldrive_snapshot,
    handoff_to_closer,
    list_actions_for_lead,
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
    schedule_followup,
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    sync_twilio_templates,
    upsert_course_default_session,
    update_lead_qualification,
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
        "La prochaine action semble incohérente.",
        expected_behavior="Voir une relance.",
        actual_behavior="Voir un appel.",
        severity="high",
    )

    assert ok is True
    assert "enregistré" in message
    reports = list_bug_reports()
    assert reports[0]["title"] == "Carte incorrecte"
    assert reports[0]["severity"] == "high"
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
    }
    assert readiness["front"]["message_count"] == 1
    assert readiness["front"]["migration_counts"]["active"] == 1
    assert "open_conversations_without_action" in readiness["workflow"]


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
    assert "fermée" in message


def test_conversation_can_be_resolved_and_reopened() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Conversation de test.")
    conversation_id = result["conversation_id"]

    ok, _ = set_conversation_status(
        conversation_id,
        1,
        "resolved",
        resolution_reason="sequence_completed_no_reply",
        resolution_note="Fin de séquence de test.",
    )
    assert ok is True
    assert get_conversation(conversation_id)["status"] == "resolved"
    assert any(
        "Clôture de conversation" in item["body"]
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
        "Réactivation de conversation" in item["body"]
        for item in list_messages(conversation_id)
        if item["direction"] == "manual_note"
    )


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
        resolution_note="Cas traité manuellement.",
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
                ) VALUES (?, ?, ?, ?, 'schooldrive_webhook', 'neutral',
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
    second = record_inbound_message(phone, "Deuxième message.")

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
        "À vérifier dans SchoolDrive.",
    )

    conversation = get_conversation(result["conversation_id"])
    messages = list_messages(result["conversation_id"])

    assert ok is True
    assert "mise à jour" in message
    assert conversation["first_name"] == "Samira"
    assert conversation["last_name"] == "Essai"
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["course_title"] == "APP GE P26"
    assert conversation["identity_status"] == "needs_identification"
    assert any("Identification à vérifier" in item["body"] for item in messages)


def test_do_not_contact_inbound_creates_contact_review() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Ne me contactez plus.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "lost",
        "neutral",
        contact_status="do_not_contact",
    )

    result = record_inbound_message(
        get_conversation(result["conversation_id"])["recipient_phone_e164"],
        "Finalement j'ai une question.",
    )

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "contact_review"
    assert action["assigned_to_role"] == "setter"


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


def test_reply_send_with_setting_booked_creates_setting_call_with_proof() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    due_at = iso_utc(utc_now() + timedelta(hours=2))

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Parfait, mon collègue vous appelle.",
        action_outcome="setting_booked",
        next_due_at=due_at,
        assigned_to_user_id=action["assigned_to_user_id"],
        note="RDV setting confirmé.",
    )

    assert ok is True
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"
    assert next_action["due_at"] == due_at
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
        note="RDV setting confirmé.",
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
        "Merci, le rendez-vous reste bien confirmé.",
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


def test_reply_send_with_do_not_contact_resolves_without_followup() -> None:
    seed_initial_data()
    result = record_inbound_message(unique_phone(), "Ne me contactez plus.")
    action = get_next_action_for_lead(result["lead_id"])

    ok, _ = send_freeform_message(
        result["conversation_id"],
        action["assigned_to_user_id"],
        "Bien reçu, nous ne vous recontacterons plus.",
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


def test_call_completion_requires_note() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    action = get_next_action_for_lead(result["lead_id"])
    complete_action_with_workflow(
        action["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixé.",
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
    result = record_inbound_message(unique_phone(), "Je veux un cas très spécifique.")
    due_at = iso_utc(utc_now() + timedelta(hours=1))
    schedule_followup(result["conversation_id"], admin["id"], admin["id"], due_at)
    action = get_next_action_for_lead(result["lead_id"])

    ok, message = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Aucun modèle ne correspond au cas spécifique.",
        "Contexte de test",
        task_id=action["id"],
    )

    assert ok is True
    assert "modèle" in message
    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["status"] == "blocked"
    requests = list_template_requests()
    assert any(item["task_id"] == action["id"] for item in requests)


def test_template_request_without_followup_does_not_block_reply_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux un modèle spécifique.")
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "reply"

    ok, message = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Créer un modèle de clarification.",
        "Contexte de test",
    )

    assert ok is True
    assert "relance bloquée" not in message
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
        note="RDV setting fixé.",
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
        note="Pas de réponse au téléphone.",
    )

    assert ok is True
    retry = get_next_action_for_lead(result["lead_id"])
    assert retry["type"] == "setting_call"
    assert retry["sequence_code"] == "setting_call_not_reached"
    assert retry["sequence_step_index"] == 1


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
    assert "enregistré" in message
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
        "Relance longue ajustée.",
        action_type="other",
        offset_direction="after",
        offset_amount=7,
        offset_unit="days",
    )
    assert ok is True
    updated = list_sequence_steps("lead_no_reply", active_only=False)[-1]
    assert updated["delay"] == "T+7j"
    assert updated["action_type"] == "other"
    assert updated["requires_template"] == 0

    ok, message = deactivate_sequence_step(admin["id"], int(updated["id"]))
    assert ok is True
    active_ids = {item["id"] for item in list_sequence_steps("lead_no_reply")}
    assert updated["id"] not in active_ids


def test_course_default_session_can_be_configured_and_deactivated() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    ok, message = upsert_course_default_session(
        admin["id"],
        "app",
        "APP VISIO E26",
        "2026-07-11",
        default_session_name="APP été 2026",
        schooldrive_url="https://schooldrive.essr.ch/sd/example",
        note="Session par défaut pour les leads APP.",
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
    assert "désactiv" in message
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
        "neutral",
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


def test_forced_closing_stage_updates_next_action() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux parler à Yasmine.")
    assert get_next_action_for_lead(result["lead_id"])["type"] == "reply"

    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "closing",
        "neutral",
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
    result = record_inbound_message(unique_phone(), "Je reviens malgré le blocage.")
    update_lead_qualification(
        result["lead_id"],
        admin["id"],
        "setting",
        "neutral",
        contact_status="do_not_contact",
    )

    ok, message = send_freeform_message(result["conversation_id"], admin["id"], "Bonjour.")
    assert ok is False
    assert "Contact bloqué" in message

    template = next(item for item in list_templates(approved_only=True))
    ok, message = send_template_message(result["conversation_id"], admin["id"], template["id"], {})
    assert ok is False
    assert "Contact bloqué" in message


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
    assert "réactivez" in message or "rÃ©activez" in message

    ok, message = handoff_to_closer(
        result["conversation_id"],
        admin["id"],
        closer["id"],
    )
    assert ok is False
    assert "réactivez" in message or "rÃ©activez" in message


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
        "neutral",
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

    template = next(item for item in list_templates(approved_only=True))
    ok, message = send_template_message(result["conversation_id"], admin["id"], template["id"], {})
    assert ok is False
    assert "Relance" in message
    assert get_next_action_for_lead(result["lead_id"])["status"] == "blocked"


def test_call_completion_note_is_visible_in_conversation() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Appelez-moi demain.")
    reply = get_next_action_for_lead(result["lead_id"])

    ok, _ = complete_action_with_workflow(
        reply["id"],
        admin["id"],
        "setting_booked",
        note="RDV setting fixé demain.",
        next_due_at=iso_utc(utc_now()),
        assigned_to_user_id=reply["assigned_to_user_id"],
    )
    assert ok is True
    setting_call = get_next_action_for_lead(result["lead_id"])
    ok, _ = complete_action_with_workflow(
        setting_call["id"],
        admin["id"],
        "not_ready",
        note="Client joint, pas prêt à décider.",
    )
    assert ok is True

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
        "neutral",
        contact_status="contact_allowed",
    )

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["lead_status"] == "not_relevant"
    assert get_next_action_for_lead(result["lead_id"]) is None


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:8]
