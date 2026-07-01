from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta

from fastapi.testclient import TestClient

from sales_cockpit.api.main import app
from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data
from sales_cockpit.services.schooldrive import SchoolDriveConnector
from sales_cockpit.store import (
    authenticate,
    get_conversation,
    get_next_action_for_lead,
    ingest_schooldrive_snapshot,
    list_actions_for_lead,
    list_messages,
    record_inbound_message,
    send_freeform_message,
    update_temporary_identity,
    upsert_course_default_session,
)
from sales_cockpit.services.front_import import import_front_transition_records
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now


ACTIVE_ACTION_STATUSES = {"planned", "open", "in_progress", "blocked"}


def schooldrive_payload(
    event_id: str = "evt_sd_1",
    occurred_at: str = "2026-06-18T09:34:20Z",
    aggregated_updated_at: str = "2026-06-18T09:34:20Z",
    schooldrive_id: str = "lead:137797",
    lead_type: str = "lead",
    first_name: str = "Marie",
    last_name: str = "Favre",
    course_category: str = "FSM",
    autoresponders: list[dict] | None = None,
    is_archived: bool = False,
) -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "occurred_at": occurred_at,
        "environment": "staging",
        "data": {
            "schooldrive_id": schooldrive_id,
            "lead_type": lead_type,
            "url": "https://schooldrive.essr.ch/crm/leads/137797",
            "aggregated_updated_at": aggregated_updated_at,
            "is_archived": is_archived,
            "archived_at": "2026-06-19T10:00:00Z" if is_archived else None,
            "archive_reason": "Test archive" if is_archived else None,
            "person": {
                "title": "mrs",
                "first_name": first_name,
                "last_name": last_name,
                "phone": "+41790000000",
                "email": "marie.favre@example.ch",
            },
            "course": {
                "category": course_category,
                "course_name": None if lead_type == "lead" else "FSM DISTANCE E26",
                "session_name": None,
                "start_date": None,
            },
            "status": "lead" if lead_type == "lead" else "pre_subscription",
            "whatsapp_autoresponders": autoresponders if autoresponders is not None else [
                {
                    "message_id": "armsg:1019771",
                    "autoresponder_id": 2063,
                    "template": "mkt_fsm_ln_subs_01",
                    "status": "sent",
                    "sent_at": "2026-06-18T09:34:20Z",
                }
            ],
        },
    }


def schooldrive_payload_21(
    schooldrive_id: str,
    lead_type: str = "lead",
    aggregated_updated_at: str = "2026-06-28T01:01:30Z",
    occurred_at: str | None = "2026-06-28T01:01:31Z",
    event_id: str | None = "evt_schema_21",
    autoresponders: list[dict] | None = None,
) -> dict:
    payload = {
        "schema_version": "2.1",
        "environment": "staging",
        "data": {
            "schooldrive_id": schooldrive_id,
            "lead_type": lead_type,
            "aggregated_updated_at": aggregated_updated_at,
            "is_archived": False,
            "archived_at": None,
            "archive_reason": None,
            "signed": False,
            "signed_at": None,
            "person": {
                "title": "M.",
                "first_name": "Jean",
                "last_name": "Dupont",
                "email": "jean.dupont@example.com",
                "phone": "+41790000000",
            },
            "do_not_contact": {"blocked": False, "reasons": []},
            "status": "prospect",
            "whatsapp_autoresponders": autoresponders
            if autoresponders is not None
            else [
                {
                    "message_id": f"armsg:{schooldrive_id}",
                    "autoresponder_id": 2063,
                    "short_name": "mkt_app_ln_subs_01",
                    "status": "sent",
                    "sent_at": "2026-06-28T01:01:30Z",
                }
            ],
            "course": {
                "id": 7921,
                "category": {
                    "id": 1,
                    "short_name": "APP",
                    "name": "Anatomie - Physiologie - Pathologie",
                },
                "short_name": "APP VISIO E26",
                "name": "Anatomie Physiologie ASCA Visioconférence Intensif Eté 2026",
                "start_date": "2026-07-11T08:30:00Z",
                "seats_total": 32,
                "seats_occupied": 20,
                "seats_available": 12,
                "is_full": False,
            },
            "related_subscriptions": [],
        },
    }
    if event_id is not None:
        payload["event_id"] = event_id
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    return payload


def active_actions_for_lead(lead_id: int) -> list[dict]:
    return [
        item
        for item in list_actions_for_lead(lead_id, "all")
        if item["status"] in ACTIVE_ACTION_STATUSES
    ]


def assert_no_active_action(lead_id: int) -> None:
    assert get_next_action_for_lead(lead_id) is None
    assert active_actions_for_lead(lead_id) == []


def active_followups_for_phone_category(phone: str, category: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                l.schooldrive_lead_id,
                l.course_title,
                l.course_start_date,
                l.schooldrive_is_archived,
                l.is_full,
                t.type,
                t.status,
                t.trigger_reason,
                t.sequence_code
            FROM leads l
            JOIN tasks t ON t.lead_id = l.id
            WHERE l.phone_e164 = ?
              AND upper(coalesce(l.course_category_short_title, '')) = ?
              AND t.type = 'follow_up'
              AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
            ORDER BY datetime(l.course_start_date), l.schooldrive_lead_id
            """,
            (phone, category.upper()),
        ).fetchall()
    return [dict(row) for row in rows]


def test_schooldrive_snapshot_creates_lead_conversation_messages_and_followup() -> None:
    seed_initial_data()

    result = ingest_schooldrive_snapshot(schooldrive_payload())

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["schooldrive_lead_id"] == "lead:137797"
    assert conversation["lead_type"] == "lead"
    assert conversation["course_category_short_title"] == "FSM"

    messages = list_messages(result["conversation_id"])
    assert any(
        message["channel"] == "schooldrive_autoresponder"
        and "mkt_fsm_ln_subs_01" in message["body"]
        for message in messages
    )

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["sequence_code"] == "lead_no_reply"
    assert action["sequence_step_index"] == 1
    assert action["due_at"].startswith("2026-06-21T09:34:20")


def test_schooldrive_identity_overwrites_manual_front_transition_identity() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    phone = "+41790012345"
    import_front_transition_records(
        [
            {
                "conversation": {
                    "id": "cnv_front_identity_schooldrive",
                    "subject": f"WhatsApp thread with {phone}",
                    "status": "assigned",
                },
                "messages": [
                    {
                        "id": "msg_front_identity_schooldrive",
                        "type": "whatsapp",
                        "is_inbound": True,
                        "created_at": 1780000000,
                        "text": "Historique Front importé.",
                    }
                ],
            }
        ],
        "front-transition-schooldrive-identity",
    )
    with connect() as conn:
        front = conn.execute(
            """
            SELECT c.id AS conversation_id
            FROM leads l
            JOIN conversations c ON c.lead_id = l.id
            WHERE l.source = 'front_transition'
              AND l.phone_e164 = ?
            """,
            (phone,),
        ).fetchone()
    assert front is not None

    ok, _message = update_temporary_identity(
        front["conversation_id"],
        admin["id"],
        "Nom",
        "Manuel",
        "",
        "",
        "Saisie pendant la transition Front.",
    )
    assert ok is True
    assert get_conversation(front["conversation_id"])["first_name"] == "Nom"

    payload = schooldrive_payload(
        event_id="evt_sd_front_identity_overwrite",
        schooldrive_id="lead:front-identity-overwrite",
        first_name="Nora",
        last_name="SchoolDrive",
        course_category="APP",
    )
    payload["data"]["person"]["phone"] = phone

    ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(front["conversation_id"])
    assert conversation["source"] == "front_transition"
    assert conversation["schooldrive_lead_id"] is None
    assert conversation["first_name"] == "Nora"
    assert conversation["last_name"] == "SchoolDrive"
    assert conversation["identity_status"] == "verified"


def test_schooldrive_new_snapshot_without_autoresponder_is_ignored() -> None:
    seed_initial_data()

    result = ingest_schooldrive_snapshot(
        schooldrive_payload(
            event_id="evt_sd_no_ar",
            schooldrive_id="lead:no-ar-yet",
            autoresponders=[],
        )
    )

    assert result["status"] == "ignored"
    assert result["ignored_reason"] == "waiting_for_first_autoresponder"
    with connect() as conn:
        lead = conn.execute(
            "SELECT id FROM leads WHERE schooldrive_lead_id = 'lead:no-ar-yet'"
        ).fetchone()
        event = conn.execute(
            "SELECT status, ignored_reason FROM schooldrive_webhook_events WHERE event_id = ?",
            ("evt_sd_no_ar",),
        ).fetchone()
    assert lead is None
    assert event["status"] == "ignored"
    assert event["ignored_reason"] == "waiting_for_first_autoresponder"


def test_schooldrive_sent_autoresponder_can_create_after_initial_ignored_snapshot() -> None:
    seed_initial_data()
    initial = schooldrive_payload(
        event_id="evt_sd_initial_ignored",
        schooldrive_id="lead:initial-then-sent",
        autoresponders=[],
    )
    sent = schooldrive_payload(
        event_id="evt_sd_later_sent",
        occurred_at="2026-06-18T10:00:00Z",
        aggregated_updated_at="2026-06-18T10:00:00Z",
        schooldrive_id="lead:initial-then-sent",
    )

    assert ingest_schooldrive_snapshot(initial)["status"] == "ignored"
    result = ingest_schooldrive_snapshot(sent)

    assert result["status"] == "created"
    assert get_next_action_for_lead(result["lead_id"])["type"] == "follow_up"


def test_schooldrive_new_snapshot_with_missing_identity_is_ignored() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_sd_missing_identity",
        schooldrive_id="lead:missing-identity",
        first_name="",
        last_name="",
    )
    payload["data"]["person"]["phone"] = None
    payload["data"]["person"]["email"] = None

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "ignored"
    assert result["ignored_reason"] == "missing_identity"
    with connect() as conn:
        lead = conn.execute(
            "SELECT id FROM leads WHERE schooldrive_lead_id = 'lead:missing-identity'"
        ).fetchone()
    assert lead is None


def test_schooldrive_min_sent_at_ignores_historical_new_sent_autoresponder(monkeypatch) -> None:
    monkeypatch.setenv(
        "SALES_COCKPIT_SCHOOLDRIVE_INGEST_MIN_SENT_AT",
        "2026-06-19T00:00:00Z",
    )
    get_settings.cache_clear()
    seed_initial_data()

    result = ingest_schooldrive_snapshot(
        schooldrive_payload(
            event_id="evt_sd_old_sent",
            schooldrive_id="lead:old-sent",
            aggregated_updated_at="2026-06-18T09:34:20Z",
        )
    )

    assert result["status"] == "ignored"
    assert result["ignored_reason"] == "sent_autoresponder_before_ingest_window"
    get_settings.cache_clear()


def test_schooldrive_queued_autoresponder_is_kept_as_waiting_record() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_sd_queued",
        schooldrive_id="subscription:queued",
        lead_type="presubscription",
        autoresponders=[
            {
                "message_id": "armsg:queued",
                "autoresponder_id": 2063,
                "short_name": "mkt_app_ln_subs_01",
                "status": "queued",
                "sent_at": None,
            }
        ],
    )

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_course_start_followup_replaces_nearby_lead_followup() -> None:
    seed_initial_data()
    now = utc_now()
    payload = schooldrive_payload(
        event_id="evt_course_start_priority",
        occurred_at=iso_utc(now),
        aggregated_updated_at=iso_utc(now),
        schooldrive_id="subscription:course-start-priority",
        lead_type="presubscription",
        course_category="APP",
        autoresponders=[
            {
                "message_id": "armsg:course-start-priority",
                "autoresponder_id": 2063,
                "template": "mkt_app_ln_subs_01",
                "status": "sent",
                "sent_at": iso_utc(now),
            }
        ],
    )
    payload["data"]["course"]["course_name"] = "APP VISIO TEST"
    payload["data"]["course"]["start_date"] = (now + timedelta(days=1)).date().isoformat()

    result = ingest_schooldrive_snapshot(payload)

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["sequence_code"] == "course_start"
    assert action["trigger_reason"] == "course_start_approaching"
    actions = list_actions_for_lead(result["lead_id"], "all")
    cancelled_initial = [
        item for item in actions
        if item["sequence_code"] == "lead_no_reply"
        and item["status"] == "done"
        and "début de cours" in (item["outcome"] or "")
    ]
    assert cancelled_initial


def test_course_start_does_not_interrupt_planned_call() -> None:
    seed_initial_data()
    now = utc_now()
    initial = schooldrive_payload(
        event_id="evt_course_call_initial",
        occurred_at=iso_utc(now),
        aggregated_updated_at=iso_utc(now),
        schooldrive_id="subscription:course-call",
        lead_type="presubscription",
        course_category="APP",
        autoresponders=[
            {
                "message_id": "armsg:course-call",
                "autoresponder_id": 2063,
                "template": "mkt_app_ln_subs_01",
                "status": "sent",
                "sent_at": iso_utc(now),
            }
        ],
    )
    initial["data"]["course"]["course_name"] = "APP VISIO TEST"
    initial["data"]["course"]["start_date"] = (now + timedelta(days=30)).date().isoformat()
    result = ingest_schooldrive_snapshot(initial)
    record_inbound_message("+41790000000", "Je suis disponible pour un appel setting.")
    reply = get_next_action_for_lead(result["lead_id"])
    assert reply["type"] == "reply"

    ok, _ = send_freeform_message(
        result["conversation_id"],
        reply["assigned_to_user_id"],
        "Votre appel setting est confirmé.",
        action_outcome="setting_booked",
        next_due_at=iso_utc(now + timedelta(days=1)),
        assigned_to_user_id=reply["assigned_to_user_id"],
        note="RDV setting confirmé.",
    )
    assert ok is True
    call = get_next_action_for_lead(result["lead_id"])
    assert call["type"] == "setting_call"

    update = deepcopy(initial)
    update["event_id"] = "evt_course_call_update"
    update["occurred_at"] = iso_utc(now + timedelta(minutes=1))
    update["data"]["aggregated_updated_at"] = iso_utc(now + timedelta(minutes=1))
    update["data"]["course"]["start_date"] = (now + timedelta(days=1)).date().isoformat()

    ingest_schooldrive_snapshot(update)

    next_action = get_next_action_for_lead(result["lead_id"])
    assert next_action["type"] == "setting_call"
    actions = list_actions_for_lead(result["lead_id"], "all")
    active_course_followups = [
        item for item in actions
        if item["sequence_code"] == "course_start"
        and item["status"] in {"open", "planned", "in_progress", "blocked"}
    ]
    assert active_course_followups == []


def test_schooldrive_sent_whatsapp_for_non_v1_category_creates_no_action() -> None:
    seed_initial_data()

    result = ingest_schooldrive_snapshot(
        schooldrive_payload(
            event_id="evt_unconfigured_category",
            schooldrive_id="lead:999001",
            course_category="NUTR",
        )
    )

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_category_short_title"] == "NUTR"
    messages = list_messages(result["conversation_id"])
    assert any(message["channel"] == "schooldrive_autoresponder" for message in messages)
    assert_no_active_action(result["lead_id"])


def test_schooldrive_non_v1_record_can_receive_reply_only_after_inbound() -> None:
    seed_initial_data()
    created = ingest_schooldrive_snapshot(
        schooldrive_payload(
            event_id="evt_non_v1_then_inbound",
            schooldrive_id="lead:non-v1-then-inbound",
            course_category="NUTR",
        )
    )

    assert_no_active_action(created["lead_id"])
    record_inbound_message("+41790000000", "Je veux quand même parler à quelqu'un.")

    actions = active_actions_for_lead(created["lead_id"])
    assert [item["type"] for item in actions] == ["reply"]


def test_schooldrive_sent_whatsapp_without_course_category_creates_no_action() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_missing_category",
        schooldrive_id="lead:missing-category",
    )
    payload["data"]["course"]["category"] = None

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_category_short_title"] is None
    assert_no_active_action(result["lead_id"])


def test_schooldrive_api_preserves_extra_fields_and_projects_capacity(monkeypatch) -> None:
    seed_initial_data()
    monkeypatch.setenv("SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN", "sd-test-token")
    get_settings.cache_clear()
    payload = schooldrive_payload(
        event_id="evt_extra_fields_capacity",
        schooldrive_id="subscription:extra-fields",
        lead_type="presubscription",
    )
    payload["data"]["unexpected_root_field"] = {"kept": True}
    payload["data"]["course"].update(
        {
            "id": "course-extra-1",
            "session_id": "session-extra-1",
            "session_name": "APP GE P26",
            "start_date": "2026-09-01",
            "capacity_total": 20,
            "capacity_occupied": 12,
            "capacity_available": 8,
            "unexpected_course_field": "kept too",
        }
    )

    client = TestClient(app)
    response = client.post(
        "/webhooks/schooldrive/lead-or-presubscription",
        json=payload,
        headers={"Authorization": "Bearer sd-test-token"},
    )

    assert response.status_code == 200
    result = response.json()
    conversation = get_conversation(result["conversation_id"])
    assert conversation["session_id"] == "session-extra-1"
    assert conversation["session_name"] == "APP GE P26"
    assert conversation["capacity_total"] == 20
    assert conversation["capacity_occupied"] == 12
    assert conversation["capacity_available"] == 8
    with connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM schooldrive_webhook_events WHERE event_id = ?",
            ("evt_extra_fields_capacity",),
        ).fetchone()
        lead_row = conn.execute(
            "SELECT schooldrive_payload_json FROM leads WHERE id = ?",
            (result["lead_id"],),
        ).fetchone()
    event_payload = json.loads(row["payload_json"])
    lead_payload = json.loads(lead_row["schooldrive_payload_json"])
    assert event_payload["data"]["unexpected_root_field"] == {"kept": True}
    assert event_payload["data"]["course"]["unexpected_course_field"] == "kept too"
    assert lead_payload["data"]["unexpected_root_field"] == {"kept": True}


def test_schooldrive_schema_11_course_capacity_and_full_course_creates_no_followup() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_schema_11_full_course",
        occurred_at="2026-06-26T09:14:22Z",
        aggregated_updated_at="2026-06-26T09:14:21Z",
        schooldrive_id="lead:48213",
        first_name="Jean",
        last_name="Dupont",
    )
    payload["schema_version"] = "1.1"
    payload["data"].update(
        {
            "signed": False,
            "signed_at": None,
            "do_not_contact": {"blocked": False, "reasons": []},
            "status": "contacted",
            "related_subscriptions": [
                {
                    "subscription_id": 33120,
                    "course_id": 1790,
                    "course_short_name": "FSM-2026-05",
                    "category_short_title": "FSM",
                    "status": "subscription",
                    "signed": True,
                    "signed_at": "2026-05-12T13:40:00Z",
                    "is_archived": False,
                }
            ],
        }
    )
    payload["data"]["course"] = {
        "course_id": 1842,
        "course_short_name": "APP-2026-09",
        "category_short_title": "APP",
        "start_date": "2026-09-01T06:00:00Z",
        "seats_total": 20,
        "seats_occupied": 20,
        "seats_available": 0,
        "is_full": True,
    }

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "1842"
    assert conversation["course_title"] == "APP-2026-09"
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["capacity_total"] == 20
    assert conversation["capacity_occupied"] == 20
    assert conversation["capacity_available"] == 0
    assert conversation["is_full"] == 1
    actions = list_actions_for_lead(result["lead_id"], "all")
    assert all(item["type"] != "follow_up" or item["status"] == "done" for item in actions)
    assert_no_active_action(result["lead_id"])
    with connect() as conn:
        row = conn.execute(
            "SELECT schooldrive_payload_json FROM leads WHERE id = ?",
            (result["lead_id"],),
        ).fetchone()
    lead_payload = json.loads(row["schooldrive_payload_json"])
    assert lead_payload["data"]["related_subscriptions"][0]["signed"] is True


def test_schooldrive_do_not_contact_blocked_stops_commercial_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_schema_11_do_not_contact",
        schooldrive_id="lead:dnc-blocked",
    )
    payload["schema_version"] = "1.1"
    payload["data"]["signed"] = True
    payload["data"]["do_not_contact"] = {
        "blocked": True,
        "reasons": ["customer_opt_out"],
    }

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["contact_status"] == "do_not_contact"
    assert conversation["status"] == "resolved"
    assert conversation["resolution_reason"] == "do_not_contact"
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_schooldrive_top_level_signed_stops_commercial_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_schema_11_top_level_signed",
        schooldrive_id="lead:top-level-signed",
    )
    payload["schema_version"] = "1.1"
    payload["data"]["signed"] = True
    payload["data"]["signed_at"] = "2026-06-26T10:11:46Z"
    payload["data"]["do_not_contact"] = {"blocked": False, "reasons": []}

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert conversation["lead_status"] == "signed"
    assert conversation["sales_stage"] == "won"
    assert conversation["resolution_reason"] == "signed"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_related_signed_subscription_same_category_stops_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_schema_11_related_signed",
        schooldrive_id="lead:related-signed",
    )
    payload["schema_version"] = "1.1"
    payload["data"].update(
        {
            "signed": False,
            "do_not_contact": {"blocked": False, "reasons": []},
            "related_subscriptions": [
                {
                    "subscription_id": 33120,
                    "course_id": 1790,
                    "course_short_name": "APP-2026-05",
                    "category_short_title": "APP",
                    "status": "subscription",
                    "signed": True,
                    "signed_at": "2026-05-12T13:40:00Z",
                    "is_archived": False,
                }
            ],
        }
    )
    payload["data"]["course"].update(
        {
            "course_id": 1842,
            "course_short_name": "APP-2026-09",
            "category_short_title": "APP",
            "seats_total": 20,
            "seats_occupied": 8,
            "seats_available": 12,
            "is_full": False,
        }
    )

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_schema_21_nested_course_capacity_and_optional_event_id() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-capacity",
        event_id=None,
        occurred_at=None,
    )

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "7921"
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["course_title"] == "APP VISIO E26"
    assert conversation["course_start_date"].startswith("2026-07-11T08:30:00")
    assert conversation["capacity_total"] == 32
    assert conversation["capacity_occupied"] == 20
    assert conversation["capacity_available"] == 12
    assert conversation["is_full"] == 0
    with connect() as conn:
        row = conn.execute(
            """
            SELECT event_id, occurred_at
            FROM schooldrive_webhook_events
            WHERE schooldrive_id = ?
            """,
            ("lead:schema-21-capacity",),
        ).fetchone()
    assert row["event_id"].startswith("schooldrive:lead:schema-21-capacity:")
    assert row["occurred_at"].startswith("2026-06-28T01:01:30")


def test_schooldrive_schema_21_do_not_contact_reason_objects_are_consumed() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="subscription:schema-21-dnc",
        lead_type="presubscription",
        event_id="evt_schema_21_dnc",
    )
    payload["data"]["do_not_contact"] = {
        "blocked": True,
        "reasons": [
            {
                "type": "customer_opt_out",
                "customer_id": 38459,
                "opt_out_group_id": 22,
                "opt_out_group": "ESSR - Marketing - AS",
                "record_id": 3,
                "since": "2023-01-26T09:30:58Z",
            }
        ],
    }

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["contact_status"] == "do_not_contact"
    assert conversation["status"] == "resolved"
    assert conversation["resolution_reason"] == "do_not_contact"
    assert "customer_opt_out/ESSR - Marketing - AS" in conversation["resolution_note"]
    assert "{" not in conversation["resolution_note"]
    assert get_next_action_for_lead(result["lead_id"]) is None


def test_schooldrive_schema_21_capacity_null_does_not_imply_full_course() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-category-only",
        event_id="evt_schema_21_category_only",
    )
    payload["data"]["course"] = {
        "id": None,
        "category": {
            "id": 1,
            "short_name": "APP",
            "name": "Anatomie - Physiologie - Pathologie",
        },
        "short_name": None,
        "name": None,
        "start_date": None,
        "seats_total": None,
        "seats_occupied": None,
        "seats_available": None,
        "is_full": None,
    }

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] is None
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["capacity_total"] is None
    assert conversation["capacity_available"] is None
    assert conversation["is_full"] == 0
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["trigger_reason"] == "schooldrive_initial_autoresponder_sent"


def test_schooldrive_v1_lead_without_course_id_uses_default_session_capacity() -> None:
    seed_initial_data()
    with connect() as conn:
        admin_id = conn.execute(
            "SELECT id FROM users WHERE email = 'francois.dupuis@essr.ch'"
        ).fetchone()["id"]
    ok, message = upsert_course_default_session(
        admin_id,
        "APP",
        "APP VISIO P26",
        "2026-09-01",
        default_session_name="APP printemps 2026",
        default_capacity_total=20,
        default_capacity_occupied=12,
        default_capacity_available=8,
    )
    assert ok, message
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-category-only-default-session",
        event_id="evt_schema_21_category_only_default_session",
    )
    payload["data"]["course"] = {
        "id": None,
        "category": {
            "id": 1,
            "short_name": "APP",
            "name": "Anatomie - Physiologie - Pathologie",
        },
        "short_name": None,
        "name": None,
        "start_date": None,
        "seats_total": None,
        "seats_occupied": None,
        "seats_available": None,
        "is_full": None,
    }

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] is None
    assert conversation["course_category_short_title"] == "APP"
    assert conversation["course_title"] == "APP VISIO P26"
    assert conversation["session_id"] == "default:APP"
    assert conversation["session_name"] == "APP printemps 2026"
    assert conversation["course_start_date"].startswith("2026-09-01")
    assert conversation["capacity_total"] == 20
    assert conversation["capacity_occupied"] == 12
    assert conversation["capacity_available"] == 8
    assert conversation["is_full"] == 0
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["trigger_reason"] == "schooldrive_initial_autoresponder_sent"


def test_schooldrive_schema_21_roadmap_without_course_creates_no_action_without_autoresponder() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-roadmap",
        event_id="evt_schema_21_roadmap",
        autoresponders=[],
    )
    payload["data"].pop("course")
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "ASCA_RME"
    assert conversation["course_title"] == "Roadmap ASCA_RME"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_schema_21_roadmap_without_identity_is_still_ignored() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-roadmap-no-identity",
        event_id="evt_schema_21_roadmap_no_identity",
        autoresponders=[],
    )
    payload["data"].pop("course")
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}
    payload["data"]["person"] = {
        "title": None,
        "first_name": "",
        "last_name": "",
        "email": None,
        "phone": None,
    }

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "ignored"
    assert result["ignored_reason"] == "missing_identity"


def test_schooldrive_roadmap_record_can_receive_reply_only_after_inbound() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="lead:schema-21-roadmap-inbound",
        event_id="evt_schema_21_roadmap_inbound",
        autoresponders=[],
    )
    payload["data"].pop("course")
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}

    result = ingest_schooldrive_snapshot(payload)
    assert_no_active_action(result["lead_id"])

    record_inbound_message("+41790000000", "Je réponds au sujet Roadmap.")

    actions = active_actions_for_lead(result["lead_id"])
    assert [item["type"] for item in actions] == ["reply"]


def test_schooldrive_schema_21_related_subscription_same_category_stops_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="subscription:schema-21-related-same-category",
        lead_type="presubscription",
        event_id="evt_schema_21_related_same_category",
    )
    payload["data"]["related_subscriptions"] = [
        {
            "subscription_id": 129076,
            "status": "in_class",
            "signed": True,
            "signed_at": "2026-04-23T07:44:00Z",
            "is_archived": False,
            "course": {
                "id": 8133,
                "category": {"id": 1, "short_name": "APP", "name": "Anatomie - Physiologie - Pathologie"},
                "short_name": "APP VISIO P26",
                "name": "Anatomie Physiologie ASCA Visioconférence Printemps 2026",
                "start_date": "2026-04-20T08:30:00Z",
                "seats_total": 100,
                "seats_occupied": 5,
                "seats_available": 95,
                "is_full": False,
            },
        }
    ]

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["status"] == "resolved"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_schema_21_related_subscription_other_category_keeps_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="subscription:schema-21-related-other-category",
        lead_type="presubscription",
        event_id="evt_schema_21_related_other_category",
    )
    payload["data"]["related_subscriptions"] = [
        {
            "subscription_id": 129076,
            "status": "in_class",
            "signed": True,
            "signed_at": "2026-04-23T07:44:00Z",
            "is_archived": False,
            "course": {
                "id": 8133,
                "category": {"id": 29, "short_name": "AMS", "name": "Ausbildung Medizinisches Sekretariat"},
                "short_name": "AMS Fernkurs F26",
                "name": "Ausbildung Medizinisches Sekretariat Fernkurs Frühjahr 2026",
                "start_date": "2026-04-20T08:30:00Z",
                "seats_total": 100,
                "seats_occupied": 5,
                "seats_available": 95,
                "is_full": False,
            },
        }
    ]

    result = ingest_schooldrive_snapshot(payload)

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["trigger_reason"] == "schooldrive_initial_autoresponder_sent"


def test_schooldrive_schema_21_archived_related_subscription_does_not_block_flow() -> None:
    seed_initial_data()
    payload = schooldrive_payload_21(
        schooldrive_id="subscription:schema-21-related-archived",
        lead_type="presubscription",
        event_id="evt_schema_21_related_archived",
    )
    payload["data"]["related_subscriptions"] = [
        {
            "subscription_id": 131972,
            "status": "subscription",
            "signed": True,
            "signed_at": "2026-06-26T10:11:46Z",
            "is_archived": True,
            "course": {
                "id": 7344,
                "category": {"id": 38, "short_name": "MP", "name": "Modules Préparatoires"},
                "short_name": "MP DISTANCE E26",
                "name": "Modules Préparatoires à distance Été 2026",
                "start_date": "2026-07-13T08:30:00Z",
                "seats_total": 100,
                "seats_occupied": 42,
                "seats_available": 58,
                "is_full": False,
            },
        }
    ]

    result = ingest_schooldrive_snapshot(payload)

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["trigger_reason"] == "schooldrive_initial_autoresponder_sent"


def test_schooldrive_same_person_category_selects_default_session_record() -> None:
    seed_initial_data()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO course_default_sessions (
                course_category, default_course_name, default_start_date, active
            ) VALUES ('APP', 'APP GE P26', '2026-09-01', 1)
            """
        )
    early = schooldrive_payload_21(
        schooldrive_id="subscription:multi-default-early",
        lead_type="presubscription",
        event_id="evt_multi_default_early",
        aggregated_updated_at="2026-06-28T01:01:30Z",
    )
    early["data"]["course"]["short_name"] = "APP GE E26"
    early["data"]["course"]["start_date"] = "2026-08-01T08:30:00Z"
    default = schooldrive_payload_21(
        schooldrive_id="subscription:multi-default-selected",
        lead_type="presubscription",
        event_id="evt_multi_default_selected",
        aggregated_updated_at="2026-06-28T01:02:30Z",
    )
    default["data"]["course"]["short_name"] = "APP GE P26"
    default["data"]["course"]["start_date"] = "2026-09-01T08:30:00Z"

    ingest_schooldrive_snapshot(early)
    ingest_schooldrive_snapshot(default)

    followups = active_followups_for_phone_category("+41790000000", "APP")
    assert [(item["schooldrive_lead_id"], item["course_title"]) for item in followups] == [
        ("subscription:multi-default-selected", "APP GE P26")
    ]


def test_schooldrive_same_person_category_without_default_selects_later_session() -> None:
    seed_initial_data()
    earlier = schooldrive_payload_21(
        schooldrive_id="subscription:multi-later-earlier",
        lead_type="presubscription",
        event_id="evt_multi_later_earlier",
        aggregated_updated_at="2026-06-28T01:03:30Z",
    )
    earlier["data"]["course"]["short_name"] = "APP GE A26"
    earlier["data"]["course"]["start_date"] = "2026-08-01T08:30:00Z"
    later = schooldrive_payload_21(
        schooldrive_id="subscription:multi-later-selected",
        lead_type="presubscription",
        event_id="evt_multi_later_selected",
        aggregated_updated_at="2026-06-28T01:04:30Z",
    )
    later["data"]["course"]["short_name"] = "APP GE H26"
    later["data"]["course"]["start_date"] = "2026-10-01T08:30:00Z"

    ingest_schooldrive_snapshot(earlier)
    ingest_schooldrive_snapshot(later)

    followups = active_followups_for_phone_category("+41790000000", "APP")
    assert [(item["schooldrive_lead_id"], item["course_title"]) for item in followups] == [
        ("subscription:multi-later-selected", "APP GE H26")
    ]


def test_schooldrive_same_person_category_all_sessions_full_creates_no_followup() -> None:
    seed_initial_data()
    first = schooldrive_payload_21(
        schooldrive_id="subscription:multi-full-first",
        lead_type="presubscription",
        event_id="evt_multi_full_first",
        aggregated_updated_at="2026-06-28T01:05:30Z",
    )
    first["data"]["course"]["short_name"] = "APP GE FULL 1"
    first["data"]["course"]["start_date"] = "2026-08-01T08:30:00Z"
    first["data"]["course"]["seats_available"] = 0
    first["data"]["course"]["is_full"] = True
    second = schooldrive_payload_21(
        schooldrive_id="subscription:multi-full-second",
        lead_type="presubscription",
        event_id="evt_multi_full_second",
        aggregated_updated_at="2026-06-28T01:06:30Z",
    )
    second["data"]["course"]["short_name"] = "APP GE FULL 2"
    second["data"]["course"]["start_date"] = "2026-10-01T08:30:00Z"
    second["data"]["course"]["seats_available"] = 0
    second["data"]["course"]["is_full"] = True

    ingest_schooldrive_snapshot(first)
    ingest_schooldrive_snapshot(second)

    assert active_followups_for_phone_category("+41790000000", "APP") == []


def test_schooldrive_same_person_category_never_selects_archived_record() -> None:
    seed_initial_data()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO course_default_sessions (
                course_category, default_course_name, default_start_date, active
            ) VALUES ('APP', 'APP GE ARCHIVE', '2026-09-01', 1)
            """
        )
    archived = schooldrive_payload_21(
        schooldrive_id="subscription:multi-archived-default",
        lead_type="presubscription",
        event_id="evt_multi_archived_default",
        aggregated_updated_at="2026-06-28T01:07:30Z",
    )
    archived["data"]["is_archived"] = True
    archived["data"]["archived_at"] = "2026-06-28T01:07:00Z"
    archived["data"]["archive_reason"] = "Archived test record"
    archived["data"]["course"]["short_name"] = "APP GE ARCHIVE"
    archived["data"]["course"]["start_date"] = "2026-09-01T08:30:00Z"
    active = schooldrive_payload_21(
        schooldrive_id="subscription:multi-archived-active",
        lead_type="presubscription",
        event_id="evt_multi_archived_active",
        aggregated_updated_at="2026-06-28T01:08:30Z",
    )
    active["data"]["course"]["short_name"] = "APP GE ACTIVE"
    active["data"]["course"]["start_date"] = "2026-10-01T08:30:00Z"

    ingest_schooldrive_snapshot(archived)
    ingest_schooldrive_snapshot(active)

    followups = active_followups_for_phone_category("+41790000000", "APP")
    assert [(item["schooldrive_lead_id"], item["course_title"]) for item in followups] == [
        ("subscription:multi-archived-active", "APP GE ACTIVE")
    ]


def test_schooldrive_api_accepts_roadmap_product_without_course(monkeypatch) -> None:
    seed_initial_data()
    monkeypatch.setenv("SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN", "sd-test-token")
    get_settings.cache_clear()
    payload = schooldrive_payload(
        event_id="evt_api_roadmap_without_course",
        schooldrive_id="lead:api-roadmap",
    )
    payload["data"].pop("course", None)
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}

    client = TestClient(app)
    response = client.post(
        "/webhooks/schooldrive/lead-or-presubscription",
        json=payload,
        headers={"Authorization": "Bearer sd-test-token"},
    )

    assert response.status_code == 200
    result = response.json()
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_title"] == "Roadmap ASCA_RME"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_later_autoresponder_does_not_recreate_initial_followup() -> None:
    seed_initial_data()
    first = ingest_schooldrive_snapshot(schooldrive_payload())
    first_action = get_next_action_for_lead(first["lead_id"])
    assert first_action["due_at"].startswith("2026-06-21T09:34:20")

    update = schooldrive_payload(
        event_id="evt_sd_later_ar",
        occurred_at="2026-06-19T12:05:00Z",
        aggregated_updated_at="2026-06-19T12:05:00Z",
        autoresponders=[
            {
                "message_id": "armsg:1019771",
                "autoresponder_id": 2063,
                "template": "mkt_fsm_ln_subs_01",
                "status": "sent",
                "sent_at": "2026-06-18T09:34:20Z",
            },
            {
                "message_id": "armsg:1019999",
                "autoresponder_id": 2064,
                "template": "mkt_fsm_extra_01",
                "status": "sent",
                "sent_at": "2026-06-19T12:00:00Z",
            },
        ],
    )
    result = ingest_schooldrive_snapshot(update)

    assert result["status"] == "updated"
    action = get_next_action_for_lead(first["lead_id"])
    assert action["type"] == "follow_up"
    assert action["sequence_code"] == "lead_no_reply"
    assert action["sequence_step_index"] == 1
    assert action["due_at"].startswith("2026-06-21T09:34:20")
    with connect() as conn:
        total_initial = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM tasks
            WHERE lead_id = ?
              AND trigger_reason IN (
                'schooldrive_initial_autoresponder_sent',
                'schooldrive_initial_followup_updated'
              )
            """,
            (first["lead_id"],),
        ).fetchone()["total"]
    assert total_initial == 1


def test_schooldrive_snapshot_accepts_real_subscription_payload_fields() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_real_subscription_shape",
        schooldrive_id="subscription:131885",
        lead_type="presubscription",
        first_name="Souad",
        last_name="Bousaid",
    )
    payload["data"]["url"] = (
        "https://schooldrive.essr.ch/sd/customers/customers"
        "(p1:sd/customers/customers/subscription/view/131885)"
    )
    payload["data"]["course"]["category"] = "APP"
    payload["data"]["course"]["course_name"] = "APP VISIO E26"
    payload["data"]["course"]["start_date"] = "2026-07-11"
    payload["data"]["whatsapp_autoresponders"] = [
        {
            "message_id": "armsg:1019771",
            "autoresponder_id": 2063,
            "short_name": "mkt_app_ln_subs_01",
            "whatsapp_template_id": "HXba7e2e78abb551de1f9c9cee798c8e59",
            "whatsapp_template_variables_mapping": {"prenom": "Souad"},
            "whatsapp_send_body": "Bonjour Souad, ceci est le vrai corps envoyé.",
            "status": "sent",
            "sent_at": "2026-06-18T09:34:20Z",
        }
    ]

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["schooldrive_lead_id"] == "subscription:131885"
    assert conversation["lead_type"] == "presubscription"
    assert conversation["course_title"] == "APP VISIO E26"
    messages = list_messages(result["conversation_id"])
    assert any(
        message["channel"] == "schooldrive_autoresponder"
        and message["body"] == "Bonjour Souad, ceci est le vrai corps envoyé."
        for message in messages
    )
    with connect() as conn:
        ar = conn.execute(
            """
            SELECT template, payload_json
            FROM schooldrive_whatsapp_autoresponders
            WHERE message_id = 'armsg:1019771'
            """
        ).fetchone()
    assert ar["template"] == "mkt_app_ln_subs_01"
    assert "whatsapp_template_id" in ar["payload_json"]


def test_schooldrive_autoresponder_body_drops_trailing_orphan_html_tags() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_sd_autoresponder_html_tail",
        schooldrive_id="lead:html-tail",
        autoresponders=[
            {
                "message_id": "armsg:html-tail",
                "autoresponder_id": 2063,
                "template": "mkt_app_ln_subs_02",
                "whatsapp_send_body": "Bonjour Dévaki,\n\nRépondez simplement 1 ou 2.\n\n          </div>\n        </div>",
                "status": "sent",
                "sent_at": "2026-06-25T11:56:00Z",
            }
        ],
    )

    result = ingest_schooldrive_snapshot(payload)

    messages = list_messages(result["conversation_id"])
    outbound = [item for item in messages if item["channel"] == "schooldrive_autoresponder"][-1]
    assert outbound["body"] == "Bonjour Dévaki,\n\nRépondez simplement 1 ou 2."
    with connect() as conn:
        ar = conn.execute(
            "SELECT payload_json FROM schooldrive_whatsapp_autoresponders WHERE message_id = ?",
            ("armsg:html-tail",),
        ).fetchone()
    assert "</div>" in ar["payload_json"]


def test_schooldrive_snapshot_accepts_nested_nutrition_subscription_course() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_nested_nutrition_subscription",
        schooldrive_id="subscription:7931",
        lead_type="presubscription",
        first_name="Nora",
        last_name="Nutrition",
    )
    payload["data"]["course"] = {
        "id": 7931,
        "category": {"id": 39, "short_name": "Nutrition", "name": "Nutrition (150h)"},
        "short_name": "NUTRI GE A26",
        "name": "Nutrition Geneve Automne 2026",
        "start_date": "2026-12-19T08:30:00Z",
    }

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "7931"
    assert conversation["course_category_short_title"].upper() == "NUTRITION"
    assert conversation["course_title"] == "NUTRI GE A26"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_snapshot_accepts_nested_fsm_lead_with_linked_subscription() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_nested_fsm_lead_linked_subscription",
        schooldrive_id="lead:linked-fsm",
        lead_type="lead",
    )
    payload["data"]["course"] = {
        "id": 7348,
        "category": {
            "id": 5,
            "short_name": "FSM",
            "name": "Formation Secretaire Medicale",
        },
        "short_name": "FSM DISTANCE E26",
        "name": "Formation Secretaire Medicale a distance Ete 2026",
        "start_date": "2026-12-13T08:30:00Z",
    }

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "7348"
    assert conversation["course_category_short_title"] == "FSM"
    assert conversation["course_title"] == "FSM DISTANCE E26"
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["sequence_code"] == "lead_no_reply"


def test_schooldrive_snapshot_accepts_nested_fsm_lead_without_linked_subscription() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_nested_fsm_lead_without_subscription",
        schooldrive_id="lead:no-linked-subscription",
        lead_type="lead",
    )
    payload["data"]["course"] = {
        "id": None,
        "category": {
            "id": 5,
            "short_name": "FSM",
            "name": "Formation Secretaire Medicale",
        },
        "short_name": None,
        "name": None,
        "start_date": None,
    }

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] is None
    assert conversation["course_category_short_title"] == "FSM"
    assert conversation["course_title"] == "Formation Secretaire Medicale"
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "follow_up"
    assert action["sequence_code"] == "lead_no_reply"


def test_schooldrive_snapshot_accepts_roadmap_product_without_course() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_roadmap_product_without_course",
        schooldrive_id="lead:roadmap-asca-rme",
        lead_type="lead",
    )
    payload["data"].pop("course")
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}

    result = ingest_schooldrive_snapshot(payload)

    assert result["status"] == "created"
    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "ASCA_RME"
    assert conversation["course_category_short_title"] is None
    assert conversation["course_title"] == "Roadmap ASCA_RME"
    assert_no_active_action(result["lead_id"])


def test_schooldrive_snapshot_accepts_roadmap_product_with_non_identity_course_fields() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_roadmap_product_partial_course",
        schooldrive_id="lead:roadmap-partial-course",
        lead_type="lead",
    )
    payload["data"]["course"] = {
        "start_date": "2026-10-01",
        "capacity_available": 12,
    }
    payload["data"]["product"] = {"roadmap_descriptive_id": "ASCA_RME"}

    result = ingest_schooldrive_snapshot(payload)

    conversation = get_conversation(result["conversation_id"])
    assert conversation["course_id"] == "ASCA_RME"
    assert conversation["course_title"] == "Roadmap ASCA_RME"
    assert conversation["course_start_date"].startswith("2026-10-01")
    assert_no_active_action(result["lead_id"])


def test_schooldrive_snapshot_detects_top_level_course_full_without_course_object_and_creates_no_followup() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_top_level_course_full",
        schooldrive_id="lead:top-level-course-full",
        lead_type="lead",
    )
    payload["data"].pop("course")
    payload["data"]["course_full"] = True

    result = ingest_schooldrive_snapshot(payload)

    actions = list_actions_for_lead(result["lead_id"], "all")
    assert all(item["type"] != "follow_up" or item["status"] == "done" for item in actions)
    assert_no_active_action(result["lead_id"])


def test_schooldrive_connector_supports_subscription_urls() -> None:
    url = SchoolDriveConnector().get_lead_url("subscription:131885")

    assert url == (
        "https://schooldrive.essr.ch/sd/customers/customers"
        "(p1:sd/customers/customers/subscription/view/131885)"
    )


def test_schooldrive_duplicate_event_is_idempotent() -> None:
    seed_initial_data()
    payload = schooldrive_payload()

    first = ingest_schooldrive_snapshot(payload)
    second = ingest_schooldrive_snapshot(payload)

    assert first["accepted"] is True
    assert second["status"] == "duplicate"
    with connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS total FROM schooldrive_webhook_events WHERE event_id = ?",
            ("evt_sd_1",),
        ).fetchone()["total"]
    assert count == 1


def test_schooldrive_older_snapshot_is_ignored() -> None:
    seed_initial_data()
    ingest_schooldrive_snapshot(schooldrive_payload(first_name="Marie"))

    older = schooldrive_payload(
        event_id="evt_sd_older",
        occurred_at="2026-06-18T09:20:00Z",
        aggregated_updated_at="2026-06-18T09:20:00Z",
        first_name="Ancienne",
    )
    result = ingest_schooldrive_snapshot(older)

    assert result["status"] == "ignored"
    with connect() as conn:
        lead = conn.execute(
            "SELECT first_name FROM leads WHERE schooldrive_lead_id = 'lead:137797'"
        ).fetchone()
    assert lead["first_name"] == "Marie"


def test_schooldrive_equal_aggregate_uses_occurred_at_tiebreak() -> None:
    seed_initial_data()
    ingest_schooldrive_snapshot(schooldrive_payload(first_name="Marie"))

    newer_delivery = schooldrive_payload(
        event_id="evt_sd_same_agg_later_delivery",
        occurred_at="2026-06-18T09:40:00Z",
        aggregated_updated_at="2026-06-18T09:34:20Z",
        first_name="Nadia",
    )
    result = ingest_schooldrive_snapshot(newer_delivery)

    assert result["status"] == "updated"
    with connect() as conn:
        lead = conn.execute(
            "SELECT first_name FROM leads WHERE schooldrive_lead_id = 'lead:137797'"
        ).fetchone()
    assert lead["first_name"] == "Nadia"


def test_schooldrive_archive_resolves_conversation_and_closes_actions() -> None:
    seed_initial_data()
    created = ingest_schooldrive_snapshot(schooldrive_payload())

    archive = schooldrive_payload(
        event_id="evt_sd_archive",
        occurred_at="2026-06-19T10:00:00Z",
        aggregated_updated_at="2026-06-19T10:00:00Z",
        is_archived=True,
    )
    result = ingest_schooldrive_snapshot(archive)

    assert result["status"] == "updated"
    conversation = get_conversation(created["conversation_id"])
    assert conversation["status"] == "resolved"
    action = get_next_action_for_lead(created["lead_id"])
    assert action is None
    messages = list_messages(created["conversation_id"])
    assert any("Archivé dans SchoolDrive" in message["body"] for message in messages)


def test_schooldrive_api_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN", "secret-test-token")
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)

    response = client.post(
        "/webhooks/schooldrive/lead-or-presubscription",
        json=schooldrive_payload(event_id="evt_api_no_auth"),
    )
    assert response.status_code == 401

    response = client.post(
        "/webhooks/schooldrive/lead-or-presubscription",
        headers={"Authorization": "Bearer secret-test-token"},
        json=schooldrive_payload(event_id="evt_api_ok"),
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    get_settings.cache_clear()


def test_schooldrive_api_rejects_wrong_environment(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN", "secret-test-token")
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)
    payload = deepcopy(schooldrive_payload(event_id="evt_wrong_env"))
    payload["environment"] = "production"

    response = client.post(
        "/webhooks/schooldrive/lead-or-presubscription",
        headers={"Authorization": "Bearer secret-test-token"},
        json=payload,
    )

    assert response.status_code == 409
    get_settings.cache_clear()
