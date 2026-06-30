from __future__ import annotations

from datetime import timedelta

import pytest

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db, seed_initial_data
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now
from sales_cockpit.store import record_inbound_message
from scripts import cleanup_schooldrive_staging, pre_cutover_check, sync_sequence_template_mappings


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


def test_sequence_template_mapping_sync_uses_twilio_sid(tmp_path) -> None:
    source_db = tmp_path / "staging.db"
    target_db = tmp_path / "prod.db"
    _create_mapping_sync_db(source_db, with_template_sid="HXreal000000000000000000000000000001", with_mapping=True)
    _create_mapping_sync_db(target_db, with_template_sid="HXreal000000000000000000000000000001", with_mapping=False)

    with sync_sequence_template_mappings.connect(source_db, query_only=True) as source_conn:
        with sync_sequence_template_mappings.connect(target_db) as target_conn:
            plan = sync_sequence_template_mappings.build_plan(
                source_conn,
                target_conn,
                expected_active_count=1,
                expected_splits={"APP": 1},
            )

            assert plan.source_count == 1
            assert plan.unchanged == 0
            assert len(plan.upserts) == 1
            assert plan.upserts[0].action == "insert"

            sync_sequence_template_mappings.apply_plan(target_conn, plan, deactivate_extra=False)

    with sync_sequence_template_mappings.connect(target_db, query_only=True) as conn:
        row = conn.execute(
            """
            SELECT stm.sequence_code, stm.sequence_step_index, stm.lead_type, stm.course_category,
                   stm.note, stm.active, wt.twilio_content_sid
            FROM sequence_template_mappings stm
            JOIN whatsapp_templates wt ON wt.id = stm.template_id
            """
        ).fetchone()

    assert dict(row) == {
        "sequence_code": "initial_no_reply",
        "sequence_step_index": 1,
        "lead_type": "lead",
        "course_category": "APP",
        "note": "validated staging mapping",
        "active": 1,
        "twilio_content_sid": "HXreal000000000000000000000000000001",
    }


def test_sequence_template_mapping_sync_blocks_missing_target_sid(tmp_path) -> None:
    source_db = tmp_path / "staging.db"
    target_db = tmp_path / "prod.db"
    _create_mapping_sync_db(source_db, with_template_sid="HXsource0000000000000000000000000001", with_mapping=True)
    _create_mapping_sync_db(target_db, with_template_sid="HXother00000000000000000000000000001", with_mapping=False)

    with sync_sequence_template_mappings.connect(source_db, query_only=True) as source_conn:
        with sync_sequence_template_mappings.connect(target_db) as target_conn:
            with pytest.raises(sync_sequence_template_mappings.SyncError, match="no approved real template"):
                sync_sequence_template_mappings.build_plan(
                    source_conn,
                    target_conn,
                    expected_active_count=1,
                    expected_splits={"APP": 1},
                )


def _create_mapping_sync_db(
    path,
    *,
    with_template_sid: str,
    with_mapping: bool,
) -> None:
    with sync_sequence_template_mappings.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sequences (
                code TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE sequence_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_code TEXT NOT NULL,
                step_index INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                action_type TEXT NOT NULL DEFAULT 'follow_up',
                UNIQUE(sequence_code, step_index)
            );
            CREATE TABLE whatsapp_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                twilio_content_sid TEXT,
                status TEXT NOT NULL DEFAULT 'draft'
            );
            CREATE TABLE sequence_template_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_code TEXT NOT NULL,
                sequence_step_index INTEGER NOT NULL,
                lead_type TEXT NOT NULL DEFAULT 'all',
                course_category TEXT NOT NULL DEFAULT 'all',
                template_id INTEGER NOT NULL REFERENCES whatsapp_templates(id) ON DELETE CASCADE,
                note TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_by_user_id INTEGER,
                updated_by_user_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sequence_code, sequence_step_index, lead_type, course_category)
            );
            INSERT INTO sequences (code, active) VALUES ('initial_no_reply', 1);
            INSERT INTO sequence_steps (sequence_code, step_index, active, action_type)
            VALUES ('initial_no_reply', 1, 1, 'follow_up');
            """
        )
        template_id = conn.execute(
            """
            INSERT INTO whatsapp_templates (twilio_content_sid, status)
            VALUES (?, 'approved')
            """,
            (with_template_sid,),
        ).lastrowid
        if with_mapping:
            conn.execute(
                """
                INSERT INTO sequence_template_mappings (
                    sequence_code, sequence_step_index, lead_type, course_category,
                    template_id, note, active
                )
                VALUES ('initial_no_reply', 1, 'lead', 'APP', ?, 'validated staging mapping', 1)
                """,
                (template_id,),
            )
