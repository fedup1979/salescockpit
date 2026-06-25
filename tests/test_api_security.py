from __future__ import annotations

from fastapi.testclient import TestClient

from sales_cockpit.api.main import app
from sales_cockpit.config import get_settings
from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import record_inbound_message


def test_application_api_requires_configured_token(monkeypatch) -> None:
    monkeypatch.delenv("SALES_COCKPIT_API_TOKEN", raising=False)
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)

    response = client.get("/leads")

    assert response.status_code == 503
    get_settings.cache_clear()


def test_application_api_accepts_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_API_TOKEN", "api-secret")
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)

    missing = client.get("/leads")
    wrong = client.get("/leads", headers={"Authorization": "Bearer wrong"})
    ok = client.get("/leads", headers={"Authorization": "Bearer api-secret"})

    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert ok.status_code == 200
    assert isinstance(ok.json(), list)
    get_settings.cache_clear()


def test_application_send_api_requires_action_id_for_active_whatsapp_action(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_API_TOKEN", "api-secret")
    get_settings.cache_clear()
    seed_initial_data()
    result = record_inbound_message("+41790006666", "Bonjour.")
    client = TestClient(app)

    response = client.post(
        f"/conversations/{result['conversation_id']}/messages",
        json={"user_id": 1, "body": "Bonjour."},
        headers={"Authorization": "Bearer api-secret"},
    )

    assert response.status_code == 409
    assert "action_id requis" in response.json()["detail"]
    get_settings.cache_clear()


def test_json_mock_twilio_webhook_requires_token_outside_local(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_ENVIRONMENT", "staging")
    monkeypatch.setenv("SALES_COCKPIT_MOCK_WEBHOOK_TOKEN", "mock-secret")
    monkeypatch.delenv("SALES_COCKPIT_API_TOKEN", raising=False)
    get_settings.cache_clear()
    seed_initial_data()
    client = TestClient(app)
    payload = {"from_phone": "+41790005555", "body": "Mock staging."}

    missing = client.post("/webhooks/twilio/whatsapp/inbound", json=payload)
    wrong = client.post(
        "/webhooks/twilio/whatsapp/inbound",
        json=payload,
        headers={"X-Sales-Cockpit-Mock-Token": "wrong"},
    )
    ok = client.post(
        "/webhooks/twilio/whatsapp/inbound",
        json=payload,
        headers={"X-Sales-Cockpit-Mock-Token": "mock-secret"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert ok.status_code == 200
    assert ok.json()["provider"] == "mock"
    get_settings.cache_clear()
