from datetime import timedelta
from uuid import uuid4

from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import (
    authenticate,
    complete_action_with_workflow,
    create_bug_report,
    create_template_request,
    get_conversation,
    get_next_action_for_lead,
    handoff_to_closer,
    list_actions_for_lead,
    list_conversations,
    list_messages,
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
    update_lead_qualification,
)


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
    assert any("Note d'entretien setting" in body for body in notes)


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
