from __future__ import annotations

from datetime import UTC, datetime

from scripts.schooldrive_smoke import build_smoke_steps


def test_schooldrive_smoke_steps_cover_expected_statuses() -> None:
    steps = build_smoke_steps(
        run_id="smoke-test",
        environment="staging",
        base_time=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )

    assert [step.expected_status for step in steps] == [
        "ignored",
        "created",
        "ignored",
        "duplicate",
        "created",
        "created",
        "created",
        "updated",
    ]
    assert [step.payload["event_id"] for step in steps] == [
        "evt_smoke-test_01_initial",
        "evt_smoke-test_02_sent",
        "evt_smoke-test_03_stale",
        "evt_smoke-test_02_sent",
        "evt_smoke-test_05_presub_sent",
        "evt_smoke-test_06_presub_queued",
        "evt_smoke-test_07_archive_initial",
        "evt_smoke-test_08_archive_update",
    ]


def test_schooldrive_smoke_steps_use_synthetic_ids_and_real_shape() -> None:
    steps = build_smoke_steps(
        run_id="smoke-test",
        environment="staging",
        base_time=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
    )

    lead_update = steps[1].payload
    queued = steps[5].payload
    archived = steps[-1].payload

    assert lead_update["schema_version"] == "2.1"
    assert lead_update["environment"] == "staging"
    assert lead_update["data"]["schooldrive_id"] == "lead:smoke-test-lead"
    assert lead_update["data"]["signed"] is False
    assert lead_update["data"]["do_not_contact"] == {"blocked": False, "reasons": []}
    assert lead_update["data"]["course"]["id"] is None
    assert lead_update["data"]["course"]["category"]["short_name"] == "FSM"
    assert lead_update["data"]["course"]["seats_total"] is None
    assert lead_update["data"]["whatsapp_autoresponders"][0]["status"] == "sent"
    assert lead_update["data"]["whatsapp_autoresponders"][0]["sent_at"] == "2026-06-19T09:00:00Z"

    assert queued["data"]["schooldrive_id"] == "subscription:smoke-test-presub-queued"
    assert queued["data"]["course"]["id"] == "smoke-course-subscription-smoke-test-presub-queued"
    assert queued["data"]["course"]["seats_available"] == 90
    assert queued["data"]["whatsapp_autoresponders"][0]["status"] == "queued"
    assert queued["data"]["whatsapp_autoresponders"][0]["sent_at"] is None

    assert archived["data"]["schooldrive_id"] == "subscription:smoke-test-archive"
    assert archived["data"]["is_archived"] is True
    assert archived["data"]["archive_reason"] == "Synthetic smoke archive"
