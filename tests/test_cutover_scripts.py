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


def test_pre_cutover_strict_mapping_check_includes_v1_categories_and_lead_type() -> None:
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
            VALUES ('APP', 'APP', 1)
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
            ) VALUES ('strict_test_flow', 1, 'lead', 'APP', ?, 1)
            """,
            (template_id,),
        )

    assert pre_cutover_check._strict_missing_template_mapping_count() == 1


def test_pre_cutover_strict_v1_category_configuration_flags_missing_and_extra_categories() -> None:
    init_db()
    with connect() as conn:
        conn.executemany(
            "INSERT INTO course_categories (course_category, label, active) VALUES (?, ?, 1)",
            [("APP", "APP"), ("FSM", "FSM"), ("NUTR", "Nutrition")],
        )

    failures = pre_cutover_check._strict_v1_category_configuration_failures()

    assert "Missing active V1 course categories: AS" in failures
    assert "Only APP/FSM/AS may be active pilotable categories in strict V1: NUTR" in failures


def test_pre_cutover_strict_blocks_schooldrive_followups_for_full_or_non_v1_records() -> None:
    seed_initial_data()
    full = record_inbound_message("+41790000031", "Bonjour.")
    unsupported = record_inbound_message("+41790000032", "Bonjour.")
    with connect() as conn:
        conn.execute(
            """
            UPDATE leads
            SET source = 'schooldrive_webhook',
                schooldrive_lead_id = 'lead:strict-full',
                course_category_short_title = 'APP',
                is_full = 1
            WHERE id = ?
            """,
            (full["lead_id"],),
        )
        conn.execute(
            "UPDATE tasks SET type = 'follow_up', status = 'open' WHERE lead_id = ?",
            (full["lead_id"],),
        )
        conn.execute(
            """
            UPDATE leads
            SET source = 'schooldrive_webhook',
                schooldrive_lead_id = 'lead:strict-nutrition',
                course_category_short_title = 'NUTR',
                is_full = 0
            WHERE id = ?
            """,
            (unsupported["lead_id"],),
        )
        conn.execute(
            "UPDATE tasks SET type = 'follow_up', status = 'open' WHERE lead_id = ?",
            (unsupported["lead_id"],),
        )

    assert pre_cutover_check._strict_forbidden_schooldrive_followup_count() == 2


def test_pre_cutover_strict_requires_capacity_for_configured_default_sessions() -> None:
    seed_initial_data()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO course_default_sessions (
                course_category, default_course_name, default_start_date, active
            ) VALUES ('APP', 'APP GE P26', '2026-07-11', 1)
            """
        )

    assert pre_cutover_check._strict_default_session_capacity_missing_count() == 1

    record = record_inbound_message("+41790000033", "Bonjour.")
    with connect() as conn:
        conn.execute(
            """
            UPDATE leads
            SET source = 'schooldrive_webhook',
                schooldrive_lead_id = 'subscription:strict-capacity',
                schooldrive_is_archived = 0,
                course_category_short_title = 'APP',
                course_start_date = '2026-07-11T08:30:00Z',
                capacity_total = 32,
                capacity_available = 4,
                is_full = 0
            WHERE id = ?
            """,
            (record["lead_id"],),
        )

    assert pre_cutover_check._strict_default_session_capacity_missing_count() == 0


def test_pre_cutover_strict_allows_at_most_one_pilotable_record_per_person_category() -> None:
    seed_initial_data()
    first = record_inbound_message("+41790000034", "Bonjour.")
    second = record_inbound_message("+41790000035", "Bonjour.")
    with connect() as conn:
        for index, lead_id in enumerate((first["lead_id"], second["lead_id"]), start=1):
            conn.execute(
                """
                UPDATE leads
                SET source = 'schooldrive_webhook',
                    schooldrive_lead_id = ?,
                    phone_e164 = '+41790000034',
                    schooldrive_is_archived = 0,
                    course_category_short_title = 'APP',
                    is_full = 0,
                    lead_status = 'eligible',
                    contact_status = 'contact_allowed'
                WHERE id = ?
                """,
                (f"subscription:strict-duplicate-{index}", lead_id),
            )

    assert pre_cutover_check._strict_duplicate_pilotable_person_category_count() == 1

    with connect() as conn:
        conn.execute(
            "UPDATE leads SET schooldrive_is_archived = 1 WHERE id = ?",
            (second["lead_id"],),
        )

    assert pre_cutover_check._strict_duplicate_pilotable_person_category_count() == 0


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
