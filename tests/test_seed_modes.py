from __future__ import annotations

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data


def test_seed_demo_data_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_SEED_DEMO_DATA", "false")
    get_settings.cache_clear()

    seed_initial_data()

    with connect() as conn:
        users = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
        demo_leads = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM leads
            WHERE schooldrive_lead_id LIKE 'SD-DEMO-%'
            """
        ).fetchone()["total"]
        sequences = conn.execute("SELECT COUNT(*) AS total FROM sequences").fetchone()["total"]
        templates = conn.execute("SELECT COUNT(*) AS total FROM whatsapp_templates").fetchone()["total"]

    assert users >= 6
    assert sequences > 0
    assert templates > 0
    assert demo_leads == 0
    get_settings.cache_clear()
