from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from sales_cockpit.api.main import app
from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data
from sales_cockpit.store import (
    get_conversation,
    get_next_action_for_lead,
    ingest_schooldrive_snapshot,
    list_messages,
)


def schooldrive_payload(
    event_id: str = "evt_sd_1",
    occurred_at: str = "2026-06-18T09:34:20Z",
    aggregated_updated_at: str = "2026-06-18T09:34:20Z",
    schooldrive_id: str = "lead:137797",
    lead_type: str = "lead",
    first_name: str = "Marie",
    last_name: str = "Favre",
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
                "category": "FSM",
                "course_name": None if lead_type == "lead" else "FSM DISTANCE E26",
                "session_name": None,
                "start_date": None,
            },
            "status": "lead" if lead_type == "lead" else "pre_subscription",
            "whatsapp_autoresponders": [
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
