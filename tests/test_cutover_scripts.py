from __future__ import annotations

from datetime import timedelta

import pytest

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db, seed_initial_data
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import record_inbound_message
from scripts import cleanup_schooldrive_staging, pre_cutover_check


def test_cleanup_schooldrive_staging_refuses_prod(monkeypatch) -> None:
    monkeypatch.setenv("SALES_COCKPIT_ENVIRONMENT", "prod")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "sys.argv",
        [
            "cleanup_schooldrive_staging.py",
            "--execute",
            "--target-environment",
            "staging",
            "--confirm",
            "CLEAN_STAGING_SCHOOLDRIVE",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        cleanup_schooldrive_staging.main()

    assert "prod/production" in str(exc.value)


def test_pre_cutover_strict_mapping_check_includes_lead_type() -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sequences (code, label, timeline, trigger, owner, stop_when, active)
            VALUES ('strict_test_flow', 'Strict test', 'T+1h', 'test', 'Setter II', 'stop', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO sequence_steps (
                sequence_id, sequence_code, step_index, delay, action_type,
                offset_direction, offset_amount, offset_unit, template_name,
                requires_template, meaning, active
            )
            SELECT id, 'strict_test_flow', 1, '+1h', 'follow_up',
                   'after', 1, 'hours', 'strict_template', 1, 'Strict test', 1
            FROM sequences
            WHERE code = 'strict_test_flow'
            """
        )
        conn.execute(
            """
            INSERT INTO course_categories (course_category, label, active)
            VALUES ('STRICT', 'Strict', 1)
            """
        )
        template_id = conn.execute(
            """
            INSERT INTO whatsapp_templates (
                twilio_content_sid, twilio_content_type, name, language, category,
                body, status
            ) VALUES (
                'HXstrictstrictstrictstrictstrict000001', 'twilio/text',
                'strict_template', 'fr', 'utility', 'Bonjour', 'approved'
            )
            """
        ).lastrowid
        conn.execute(
            """
            INSERT INTO sequence_template_mappings (
                sequence_code, sequence_step_index, lead_type, course_category,
                template_id, active
            ) VALUES ('strict_test_flow', 1, 'lead', 'STRICT', ?, 1)
            """,
            (template_id,),
        )

    assert pre_cutover_check._strict_missing_template_mapping_count() == 1


def test_pre_cutover_strict_detects_old_pending_send() -> None:
    seed_initial_data()
    result = record_inbound_message("+41790000001", "Bonjour.")
    old = iso_utc(utc_now() - timedelta(minutes=20))
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body,
                twilio_status, created_at
            ) VALUES (?, ?, 'outbound', 'whatsapp_twilio', 'Pending old', 'pending_send', ?)
            """,
            (result["conversation_id"], result["lead_id"], old),
        )

    assert pre_cutover_check._old_pending_send_count() == 1
