from __future__ import annotations

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from sales_cockpit.api.main import app
from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data
from sales_cockpit.store import get_next_action_for_lead


TWILIO_AUTH_TOKEN = "twilio-test-token"


def _signature(url: str, params: dict[str, str]) -> str:
    return RequestValidator(TWILIO_AUTH_TOKEN).compute_signature(url, params)


def _configure_twilio(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN)
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_VALIDATE_SIGNATURE", "true")
    monkeypatch.delenv("SALES_COCKPIT_TWILIO_WEBHOOK_URL", raising=False)
    get_settings.cache_clear()


def test_twilio_inbound_rejects_invalid_signature(monkeypatch) -> None:
    _configure_twilio(monkeypatch)
    seed_initial_data()
    client = TestClient(app)

    response = client.post(
        "/webhooks/twilio/whatsapp/inbound",
        data={
            "From": "whatsapp:+41790001111",
            "Body": "Bonjour",
            "MessageSid": "SM_TEST_INVALID",
            "SmsStatus": "received",
        },
        headers={"X-Twilio-Signature": "invalid"},
    )

    assert response.status_code == 403
    get_settings.cache_clear()


def test_twilio_inbound_form_creates_reply_action_and_is_idempotent(monkeypatch) -> None:
    _configure_twilio(monkeypatch)
    seed_initial_data()
    client = TestClient(app)
    url = "http://testserver/webhooks/twilio/whatsapp/inbound"
    params = {
        "From": "whatsapp:+41790002222",
        "To": "whatsapp:+14155238886",
        "Body": "Bonjour, je veux des informations.",
        "MessageSid": "SM_TEST_INBOUND_1",
        "SmsStatus": "received",
        "NumMedia": "0",
    }
    headers = {"X-Twilio-Signature": _signature(url, params)}

    response = client.post("/webhooks/twilio/whatsapp/inbound", data=params, headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["duplicate"] is False
    assert payload["provider"] == "twilio"

    duplicate = client.post("/webhooks/twilio/whatsapp/inbound", data=params, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["message_id"] == payload["message_id"]

    with connect() as conn:
        message_count = conn.execute(
            "SELECT COUNT(*) AS total FROM messages WHERE twilio_message_sid = ?",
            ("SM_TEST_INBOUND_1",),
        ).fetchone()["total"]
        message = conn.execute(
            "SELECT body, twilio_status FROM messages WHERE twilio_message_sid = ?",
            ("SM_TEST_INBOUND_1",),
        ).fetchone()

    assert message_count == 1
    assert message["body"] == "Bonjour, je veux des informations."
    assert message["twilio_status"] == "received"
    action = get_next_action_for_lead(payload["lead_id"])
    assert action["type"] == "reply"
    assert action["status"] == "open"
    get_settings.cache_clear()


def test_twilio_status_callback_updates_message(monkeypatch) -> None:
    _configure_twilio(monkeypatch)
    seed_initial_data()
    client = TestClient(app)

    inbound_url = "http://testserver/webhooks/twilio/whatsapp/inbound"
    inbound_params = {
        "From": "whatsapp:+41790003333",
        "To": "whatsapp:+14155238886",
        "Body": "Merci.",
        "MessageSid": "SM_TEST_STATUS_1",
        "SmsStatus": "received",
    }
    client.post(
        "/webhooks/twilio/whatsapp/inbound",
        data=inbound_params,
        headers={"X-Twilio-Signature": _signature(inbound_url, inbound_params)},
    )

    status_url = "http://testserver/webhooks/twilio/whatsapp/status"
    status_params = {
        "MessageSid": "SM_TEST_STATUS_1",
        "MessageStatus": "delivered",
    }
    response = client.post(
        "/webhooks/twilio/whatsapp/status",
        data=status_params,
        headers={"X-Twilio-Signature": _signature(status_url, status_params)},
    )

    assert response.status_code == 200
    assert response.json()["callback_status"] == "updated"
    with connect() as conn:
        row = conn.execute(
            "SELECT twilio_status FROM messages WHERE twilio_message_sid = ?",
            ("SM_TEST_STATUS_1",),
        ).fetchone()
    assert row["twilio_status"] == "delivered"
    get_settings.cache_clear()


def test_twilio_status_callback_ignores_status_regression(monkeypatch) -> None:
    _configure_twilio(monkeypatch)
    seed_initial_data()
    client = TestClient(app)

    inbound_url = "http://testserver/webhooks/twilio/whatsapp/inbound"
    inbound_params = {
        "From": "whatsapp:+41790003334",
        "To": "whatsapp:+14155238886",
        "Body": "Merci.",
        "MessageSid": "SM_TEST_STATUS_REGRESSION",
        "SmsStatus": "received",
    }
    client.post(
        "/webhooks/twilio/whatsapp/inbound",
        data=inbound_params,
        headers={"X-Twilio-Signature": _signature(inbound_url, inbound_params)},
    )

    status_url = "http://testserver/webhooks/twilio/whatsapp/status"
    delivered_params = {
        "MessageSid": "SM_TEST_STATUS_REGRESSION",
        "MessageStatus": "delivered",
    }
    sent_params = {
        "MessageSid": "SM_TEST_STATUS_REGRESSION",
        "MessageStatus": "sent",
    }
    delivered = client.post(
        "/webhooks/twilio/whatsapp/status",
        data=delivered_params,
        headers={"X-Twilio-Signature": _signature(status_url, delivered_params)},
    )
    stale = client.post(
        "/webhooks/twilio/whatsapp/status",
        data=sent_params,
        headers={"X-Twilio-Signature": _signature(status_url, sent_params)},
    )

    assert delivered.status_code == 200
    assert stale.status_code == 200
    assert stale.json()["callback_status"] == "stale_status"
    with connect() as conn:
        row = conn.execute(
            "SELECT twilio_status FROM messages WHERE twilio_message_sid = ?",
            ("SM_TEST_STATUS_REGRESSION",),
        ).fetchone()
    assert row["twilio_status"] == "delivered"
    get_settings.cache_clear()


def test_legacy_json_mock_inbound_still_works_without_twilio_signature(monkeypatch) -> None:
    monkeypatch.delenv("SALES_COCKPIT_TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("SALES_COCKPIT_TWILIO_VALIDATE_SIGNATURE", "true")
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)

    response = client.post(
        "/webhooks/twilio/whatsapp/inbound",
        json={"from_phone": "+41790004444", "body": "Mock JSON."},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["duplicate"] is False
    get_settings.cache_clear()
