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
    get_conversation,
    get_next_action_for_lead,
    ingest_schooldrive_snapshot,
    list_actions_for_lead,
    list_messages,
    record_inbound_message,
    send_freeform_message,
)
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now


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


def test_schooldrive_sent_whatsapp_for_unconfigured_category_creates_human_review() -> None:
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
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "unconfigured_course_category"
    assert action["assigned_to_email"] == "service.etudiants@essr.ch"


def test_schooldrive_active_human_review_blocks_later_course_start_followup() -> None:
    seed_initial_data()
    created = ingest_schooldrive_snapshot(
        schooldrive_payload(
            event_id="evt_unconfigured_then_course_start",
            schooldrive_id="lead:unconfigured-then-course-start",
            course_category="NUTR",
        )
    )
    review = get_next_action_for_lead(created["lead_id"])
    assert review["trigger_reason"] == "unconfigured_course_category"

    update = schooldrive_payload(
        event_id="evt_unconfigured_then_course_start_update",
        occurred_at="2026-06-19T12:00:00Z",
        aggregated_updated_at="2026-06-19T12:00:00Z",
        schooldrive_id="lead:unconfigured-then-course-start",
        course_category="APP",
    )
    update["data"]["course"].update(
        {
            "course_id": 1842,
            "course_short_name": "APP-2026-09",
            "category_short_title": "APP",
            "start_date": "2026-06-20T08:00:00Z",
        }
    )

    result = ingest_schooldrive_snapshot(update)

    assert result["status"] == "updated"
    actions = list_actions_for_lead(created["lead_id"], "all")
    active = [item for item in actions if item["status"] in {"planned", "open", "in_progress", "blocked"}]
    assert [item["trigger_reason"] for item in active] == ["unconfigured_course_category"]
    assert all(item["sequence_code"] != "course_start" for item in active)


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


def test_schooldrive_schema_11_course_capacity_and_full_course_review() -> None:
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
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "schooldrive_course_full"
    actions = list_actions_for_lead(result["lead_id"], "all")
    assert all(item["type"] != "follow_up" or item["status"] == "done" for item in actions)
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


def test_schooldrive_related_signed_subscription_routes_to_human_review() -> None:
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
    assert conversation["lead_status"] == "eligible"
    assert conversation["status"] == "open"
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "schooldrive_related_subscription_signed"
    actions = list_actions_for_lead(result["lead_id"], "all")
    assert all(item["type"] != "follow_up" or item["status"] == "done" for item in actions)


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
    action = get_next_action_for_lead(result["lead_id"])
    assert action["trigger_reason"] == "unconfigured_course_category"


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
    assert conversation["course_category_short_title"] == "Nutrition"
    assert conversation["course_title"] == "NUTRI GE A26"
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "unconfigured_course_category"


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
        "start_date": "2026-07-13T08:30:00Z",
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
    assert conversation["course_id"] == "5"
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
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "unconfigured_course_category"


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
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "unconfigured_course_category"


def test_schooldrive_snapshot_detects_top_level_course_full_without_course_object() -> None:
    seed_initial_data()
    payload = schooldrive_payload(
        event_id="evt_top_level_course_full",
        schooldrive_id="lead:top-level-course-full",
        lead_type="lead",
    )
    payload["data"].pop("course")
    payload["data"]["course_full"] = True

    result = ingest_schooldrive_snapshot(payload)

    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "other"
    assert action["trigger_reason"] == "schooldrive_course_full"


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
