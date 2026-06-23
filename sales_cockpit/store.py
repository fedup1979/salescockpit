from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from sales_cockpit.business_rules import (
    RESOLUTION_REASONS,
    STOP_CONTACT_STATUSES,
    STOP_QUALIFICATION_STATUSES,
)
from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db, insert_event, row_to_dict, rows_to_dicts
from sales_cockpit.security import verify_password
from sales_cockpit.services.twilio_content import (
    TwilioContentError,
    TwilioContentTemplate,
    create_twilio_text_template,
    list_twilio_templates,
    submit_twilio_template_for_whatsapp_approval,
)
from sales_cockpit.services.twilio_client import (
    TwilioConfigurationError,
    TwilioMessageError,
    get_whatsapp_client,
)
from sales_cockpit.services.front_import import build_front_cutover_plan, list_front_import_records
from sales_cockpit.services.whatsapp_rules import calculate_window, iso_utc, parse_dt, utc_now


IDENTITY_STATUS_VERIFIED = "verified"
IDENTITY_STATUS_NEEDS_IDENTIFICATION = "needs_identification"
IDENTITY_STATUS_AMBIGUOUS = "ambiguous_identity"
IDENTITY_REVIEW_STATUSES = {
    IDENTITY_STATUS_NEEDS_IDENTIFICATION,
    IDENTITY_STATUS_AMBIGUOUS,
}
SCHOOLDRIVE_PENDING_AUTORESPONDER_STATUSES = {
    "queued",
    "sending",
    "moderation_pending",
}
VALID_ACTION_TYPES = {"reply", "follow_up", "setting_call", "closing_call", "contact_review", "other"}
VALID_TASK_STATUSES = {"open", "in_progress", "planned", "blocked", "done", "cancelled"}
VALID_CONTACT_STATUSES = {"contact_allowed", "do_not_contact"}
VALID_LEAD_STATUSES = {"eligible", "not_relevant", "will_sign", "signed"}
VALID_SEQUENCE_CODES = {
    "lead_no_reply",
    "setter_no_next_step",
    "setting_call_not_reached",
    "closing_call_not_reached",
    "post_setting_undecided",
    "post_closing_undecided",
    "closer_will_sign",
    "course_start",
}
ZURICH_TZ = ZoneInfo("Europe/Zurich")
BUSINESS_HOURS_BY_ROLE = {
    "company": (8, 20),
    "setter1": (8, 17),
    "setter2": (12, 16),
    "closer": (11, 20),
}
MAX_FREEFORM_ATTACHMENTS = 5
MAX_FREEFORM_ATTACHMENT_BYTES = 10 * 1024 * 1024


def bootstrap() -> None:
    init_db()


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(email) = lower(?) AND active = 1", (email,)
        ).fetchone()
    user = row_to_dict(row)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    log_user_activity(
        user["id"],
        "login",
        entity_type="user",
        entity_id=user["id"],
    )
    user.pop("password_hash", None)
    user["full_name"] = normalize_user_display_name(user.get("email"), user.get("full_name"))
    return user


def list_users(active_only: bool = True) -> list[dict[str, Any]]:
    query = "SELECT id, email, full_name, role, active FROM users"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY role, full_name"
    with connect() as conn:
        rows = conn.execute(query).fetchall()
    users = rows_to_dicts(rows)
    for user in users:
        user["full_name"] = normalize_user_display_name(user.get("email"), user.get("full_name"))
    return users


def normalize_user_display_name(email: str | None, full_name: str | None) -> str:
    if (email or "").lower() == "setter2@essr.ch":
        return "Tanjona"
    if (full_name or "").strip().lower() == "setter 2":
        return "Tanjona"
    return (full_name or "").strip() or "Non assigné"


def _insert_internal_note_message(
    conn: Any,
    lead_id: int,
    conversation_id: int | None,
    user_id: int | None,
    body: str,
    created_at: str,
) -> int | None:
    body = body.strip()
    if not body or not conversation_id:
        return None
    cursor = conn.execute(
        """
        INSERT INTO messages (
            conversation_id, lead_id, direction, channel, body, sender_user_id, created_at
        ) VALUES (?, ?, 'manual_note', 'sales_cockpit_internal_note', ?, ?, ?)
        """,
        (conversation_id, lead_id, body, user_id, created_at),
    )
    return int(cursor.lastrowid)


def log_user_activity(
    user_id: int | None,
    event_type: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    lead_id: int | None = None,
    conversation_id: int | None = None,
    action_id: int | None = None,
    metadata: dict | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, lead_id,
                conversation_id, action_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                event_type,
                entity_type,
                entity_id,
                lead_id,
                conversation_id,
                action_id,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )


def create_bug_report(
    user_id: int,
    page: str,
    title: str,
    description: str,
    expected_behavior: str = "",
    actual_behavior: str = "",
    severity: str = "normal",
    conversation_id: int | None = None,
    action_id: int | None = None,
    metadata: dict | None = None,
) -> tuple[bool, str]:
    title = title.strip()
    description = description.strip()
    if not title or not description:
        return False, "Ajoutez un titre et une description."
    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bug_reports (
                user_id, page, conversation_id, action_id, title, description,
                expected_behavior, actual_behavior, severity, status,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                user_id,
                page,
                conversation_id,
                action_id,
                title,
                description,
                expected_behavior.strip() or None,
                actual_behavior.strip() or None,
                severity,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id,
                conversation_id, action_id, metadata_json, created_at
            ) VALUES (?, 'bug_report_created', 'bug_report', ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                cursor.lastrowid,
                conversation_id,
                action_id,
                json.dumps({"page": page, "severity": severity, **(metadata or {})}, ensure_ascii=False),
                now,
            ),
        )
        admin_action_id = _ensure_admin_action(
            conn,
            "bug_report",
            f"Traiter le bug : {title}",
            description,
            conversation_id=conversation_id,
            task_id=action_id,
            bug_report_id=int(cursor.lastrowid),
            created_by_user_id=user_id,
            metadata={"page": page, "severity": severity},
        )
        if admin_action_id:
            conn.execute(
                """
                INSERT INTO user_activity_log (
                    user_id, event_type, entity_type, entity_id,
                    conversation_id, action_id, metadata_json, created_at
                ) VALUES (?, 'admin_action_created', 'admin_action', ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    admin_action_id,
                    conversation_id,
                    action_id,
                    json.dumps({"source": "bug_report", "bug_report_id": int(cursor.lastrowid)}, ensure_ascii=False),
                    now,
                ),
            )
    return True, "Signalement enregistré."


def list_bug_reports(status: str = "all") -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if status != "all":
        filters.append("br.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                br.*,
                u.full_name AS user_name
            FROM bug_reports br
            LEFT JOIN users u ON u.id = br.user_id
            {where}
            ORDER BY datetime(br.created_at) DESC, br.id DESC
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def list_user_activity_log(limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                al.id,
                al.created_at,
                al.event_type,
                al.entity_type,
                al.entity_id,
                al.lead_id,
                al.conversation_id,
                al.action_id,
                al.metadata_json,
                u.full_name AS user_name,
                u.email AS user_email
            FROM user_activity_log al
            LEFT JOIN users u ON u.id = al.user_id
            ORDER BY datetime(al.created_at) DESC, al.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


ADMIN_ACTION_OPEN_STATUSES = {"open", "in_progress", "blocked"}
SAFEGUARD_DEFAULTS = {
    "outbound_global_block": "false",
    "outbound_max_per_lead_day": "3",
    "outbound_max_per_lead_week": "8",
    "outbound_max_global_day": "200",
    "outbound_min_followup_hours": "24",
}


def _admin_user_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE role = 'admin' AND active = 1
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    return int(row["id"]) if row else None


def _ensure_admin_action(
    conn: Any,
    action_type: str,
    title: str,
    description: str | None = None,
    lead_id: int | None = None,
    conversation_id: int | None = None,
    task_id: int | None = None,
    template_request_id: int | None = None,
    bug_report_id: int | None = None,
    created_by_user_id: int | None = None,
    assigned_to_user_id: int | None = None,
    due_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int | None:
    filters = ["type = ?", "status IN ('open', 'in_progress', 'blocked')"]
    params: list[Any] = [action_type]
    unique_fields = {
        "template_request_id": template_request_id,
        "bug_report_id": bug_report_id,
        "task_id": task_id if action_type not in {"template_request", "bug_report"} else None,
        "lead_id": lead_id if action_type in {"course_full_review", "default_session_review"} else None,
    }
    for field, value in unique_fields.items():
        if value is not None:
            filters.append(f"{field} = ?")
            params.append(value)
    if len(filters) > 2:
        existing = conn.execute(
            f"SELECT id FROM admin_actions WHERE {' AND '.join(filters)} LIMIT 1",
            params,
        ).fetchone()
        if existing:
            return int(existing["id"])

    now = iso_utc()
    assignee_id = assigned_to_user_id or _admin_user_id(conn)
    if not assignee_id:
        return None
    cursor = conn.execute(
        """
        INSERT INTO admin_actions (
            type, title, description, status, lead_id, conversation_id, task_id,
            template_request_id, bug_report_id, assigned_to_user_id,
            created_by_user_id, due_at, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_type,
            title,
            description,
            lead_id,
            conversation_id,
            task_id,
            template_request_id,
            bug_report_id,
            assignee_id,
            created_by_user_id,
            due_at or now,
            json.dumps(metadata or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def list_admin_actions(status: str = "open") -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if status == "open":
        filters.append("aa.status IN ('open', 'in_progress', 'blocked')")
    elif status != "all":
        filters.append("aa.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                aa.*,
                assignee.full_name AS assigned_to_name,
                creator.full_name AS created_by_name,
                l.first_name,
                l.last_name,
                tr.status AS template_request_status,
                br.status AS bug_report_status
            FROM admin_actions aa
            LEFT JOIN users assignee ON assignee.id = aa.assigned_to_user_id
            LEFT JOIN users creator ON creator.id = aa.created_by_user_id
            LEFT JOIN leads l ON l.id = aa.lead_id
            LEFT JOIN template_requests tr ON tr.id = aa.template_request_id
            LEFT JOIN bug_reports br ON br.id = aa.bug_report_id
            {where}
            ORDER BY
                CASE aa.status
                    WHEN 'open' THEN 0
                    WHEN 'in_progress' THEN 1
                    WHEN 'blocked' THEN 2
                    WHEN 'done' THEN 3
                    ELSE 4
                END,
                datetime(coalesce(aa.due_at, aa.created_at)) ASC,
                aa.id DESC
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def complete_admin_action(action_id: int, user_id: int, outcome: str = "done") -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        action = row_to_dict(
            conn.execute("SELECT * FROM admin_actions WHERE id = ?", (action_id,)).fetchone()
        )
        if not action:
            return False, "Action admin introuvable."
        if action.get("status") == "done":
            return True, "Action admin déjà terminée."
        conn.execute(
            """
            UPDATE admin_actions
            SET status = 'done', outcome = ?, completed_by_user_id = ?,
                completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (outcome, user_id, now, now, action_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id,
                lead_id, conversation_id, action_id, metadata_json, created_at
            ) VALUES (?, 'admin_action_completed', 'admin_action', ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                action_id,
                action.get("lead_id"),
                action.get("conversation_id"),
                action.get("task_id"),
                json.dumps({"type": action.get("type"), "outcome": outcome}, ensure_ascii=False),
                now,
            ),
        )
    return True, "Action admin terminée."


def get_outbound_safeguards() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT key, value
            FROM app_metadata
            WHERE key LIKE 'safeguard_%'
            """
        ).fetchall()
    values = dict(SAFEGUARD_DEFAULTS)
    for row in rows:
        key = str(row["key"]).replace("safeguard_", "", 1)
        values[key] = row["value"]
    return {
        "outbound_global_block": str(values["outbound_global_block"]).lower() == "true",
        "outbound_max_per_lead_day": int(values["outbound_max_per_lead_day"]),
        "outbound_max_per_lead_week": int(values["outbound_max_per_lead_week"]),
        "outbound_max_global_day": int(values["outbound_max_global_day"]),
        "outbound_min_followup_hours": int(values["outbound_min_followup_hours"]),
    }


def update_outbound_safeguards(user_id: int, values: dict[str, Any]) -> tuple[bool, str]:
    parsed = {
        "outbound_global_block": "true" if bool(values.get("outbound_global_block")) else "false",
        "outbound_max_per_lead_day": str(max(1, int(values.get("outbound_max_per_lead_day") or 3))),
        "outbound_max_per_lead_week": str(max(1, int(values.get("outbound_max_per_lead_week") or 8))),
        "outbound_max_global_day": str(max(1, int(values.get("outbound_max_global_day") or 200))),
        "outbound_min_followup_hours": str(max(1, int(values.get("outbound_min_followup_hours") or 24))),
    }
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        for key, value in parsed.items():
            conn.execute(
                """
                INSERT INTO app_metadata (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (f"safeguard_{key}", value, now),
            )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, metadata_json, created_at
            ) VALUES (?, 'outbound_safeguards_updated', 'settings', ?, ?)
            """,
            (user_id, json.dumps(parsed, ensure_ascii=False), now),
        )
    return True, "Garde-fous enregistrés."


def get_integration_readiness() -> dict[str, Any]:
    settings = get_settings()
    with connect() as conn:
        schooldrive_status_counts = _count_by(conn, "schooldrive_webhook_events", "status")
        schooldrive_latest = rows_to_dicts(
            conn.execute(
                """
                SELECT event_id, schooldrive_id, status, ignored_reason,
                       aggregated_updated_at, received_at
                FROM schooldrive_webhook_events
                ORDER BY datetime(received_at) DESC, id DESC
                LIMIT 10
                """
            ).fetchall()
        )
        schooldrive_lead_count = _scalar_count(
            conn,
            "SELECT COUNT(*) FROM leads WHERE source = 'schooldrive_webhook'",
        )

        front_match_counts = _count_by(conn, "front_conversations", "match_status")
        front_migration_counts = _count_by(conn, "front_conversations", "migration_status")
        front_message_count = _scalar_count(conn, "SELECT COUNT(*) FROM front_messages")
        front_attached_count = _scalar_count(
            conn,
            "SELECT COUNT(*) FROM messages WHERE channel = 'front_history'",
        )
        front_latest = rows_to_dicts(
            conn.execute(
                """
                SELECT
                    front_conversation_id, phone_e164, match_status,
                    migration_status, migration_action_type,
                    subject, updated_at
                FROM front_conversations
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT 10
                """
            ).fetchall()
        )

        twilio_status_counts = rows_to_dicts(
            conn.execute(
                """
                SELECT coalesce(twilio_status, 'unknown') AS status, COUNT(*) AS count
                FROM messages
                WHERE channel = 'whatsapp_twilio'
                  AND direction = 'outbound'
                GROUP BY coalesce(twilio_status, 'unknown')
                ORDER BY count DESC, status
                """
            ).fetchall()
        )
        twilio_latest = rows_to_dicts(
            conn.execute(
                """
                SELECT
                    m.id, m.direction, m.twilio_message_sid, m.twilio_status,
                    m.twilio_error_code, m.created_at, substr(m.body, 1, 120) AS body_preview,
                    l.first_name, l.last_name
                FROM messages m
                LEFT JOIN leads l ON l.id = m.lead_id
                WHERE m.channel = 'whatsapp_twilio'
                ORDER BY datetime(m.created_at) DESC, m.id DESC
                LIMIT 10
                """
            ).fetchall()
        )

        schooldrive_waiting_first_autoresponder_count = _scalar_count(
            conn,
            """
            SELECT COUNT(*)
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            WHERE c.status = 'open'
              AND l.source = 'schooldrive_webhook'
              AND NOT EXISTS (
                SELECT 1
                FROM tasks t
                WHERE t.conversation_id = c.id
                  AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
              )
              AND NOT EXISTS (
                SELECT 1
                FROM schooldrive_whatsapp_autoresponders a
                WHERE a.lead_id = l.id
                  AND a.status = 'sent'
                  AND a.sent_at IS NOT NULL
              )
            """,
        )
        conversations_without_action = _scalar_count(
            conn,
            """
            SELECT COUNT(*)
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            WHERE c.status = 'open'
              AND NOT EXISTS (
                SELECT 1
                FROM tasks t
                WHERE t.conversation_id = c.id
                  AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
              )
              AND NOT (
                l.source = 'schooldrive_webhook'
                AND NOT EXISTS (
                  SELECT 1
                  FROM schooldrive_whatsapp_autoresponders a
                  WHERE a.lead_id = l.id
                    AND a.status = 'sent'
                    AND a.sent_at IS NOT NULL
                )
              )
            """,
        )
        resolved_conversations_with_action_count = _scalar_count(
            conn,
            """
            SELECT COUNT(*)
            FROM conversations c
            WHERE c.status = 'resolved'
              AND EXISTS (
                SELECT 1
                FROM tasks t
                WHERE t.conversation_id = c.id
                  AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
              )
            """,
        )
        conversations_with_multiple_main_actions = _scalar_count(
            conn,
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    c.id,
                    COUNT(*) AS total_actions,
                    SUM(CASE WHEN t.type = 'reply' THEN 1 ELSE 0 END) AS reply_actions,
                    SUM(CASE WHEN t.type IN ('setting_call', 'closing_call') THEN 1 ELSE 0 END) AS call_actions,
                    SUM(CASE WHEN t.type = 'follow_up' THEN 1 ELSE 0 END) AS followup_actions
                FROM conversations c
                JOIN tasks t ON t.conversation_id = c.id
                WHERE c.status = 'open'
                  AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
                  AND t.type IN ('reply', 'follow_up', 'setting_call', 'closing_call', 'contact_review', 'other')
                GROUP BY c.id
                HAVING total_actions > 1
                   AND NOT (
                        total_actions = 2
                        AND reply_actions = 1
                        AND call_actions = 1
                        AND followup_actions = 0
                   )
            )
            """,
        )
        open_action_count = _scalar_count(
            conn,
            "SELECT COUNT(*) FROM tasks WHERE status IN ('planned', 'open', 'in_progress', 'blocked')",
        )
        blocked_action_count = _scalar_count(
            conn,
            "SELECT COUNT(*) FROM tasks WHERE status = 'blocked'",
        )
        open_bug_count = _scalar_count(conn, "SELECT COUNT(*) FROM bug_reports WHERE status = 'open'")
        pending_template_request_count = _scalar_count(
            conn,
            "SELECT COUNT(*) FROM template_requests WHERE status IN ('to_create', 'submitted')",
        )
        obsolete_sequence_reference_count = sum(
            [
                _scalar_count(
                    conn,
                    """
                    SELECT COUNT(*)
                    FROM tasks
                    WHERE sequence_code = 'post_call_undecided'
                      AND status IN ('planned', 'open', 'in_progress', 'blocked')
                    """,
                ),
                _scalar_count(
                    conn,
                    """
                    SELECT COUNT(*)
                    FROM template_requests
                    WHERE sequence_code = 'post_call_undecided'
                      AND status IN ('to_create', 'submitted')
                    """,
                ),
                _scalar_count(
                    conn,
                    "SELECT COUNT(*) FROM sequence_steps WHERE sequence_code = 'post_call_undecided' AND active = 1",
                ),
                _scalar_count(
                    conn,
                    "SELECT COUNT(*) FROM sequence_template_mappings WHERE sequence_code = 'post_call_undecided' AND active = 1",
                ),
            ]
        )
        active_followup_missing_step_count = _scalar_count(
            conn,
            """
            SELECT COUNT(*)
            FROM tasks t
            LEFT JOIN sequence_steps ss
              ON ss.sequence_code = t.sequence_code
             AND ss.step_index = t.sequence_step_index
             AND ss.active = 1
            WHERE t.type = 'follow_up'
              AND t.status IN ('planned', 'open', 'in_progress', 'blocked')
              AND t.sequence_code IS NOT NULL
              AND ss.id IS NULL
            """,
        )

    twilio_mode = (settings.twilio_mode or "mock").lower()
    twilio_live_ready = bool(
        settings.twilio_account_sid
        and settings.twilio_auth_token
        and (settings.twilio_whatsapp_sender or settings.twilio_messaging_service_sid)
    )
    twilio_ready = twilio_mode == "mock" or twilio_live_ready
    if twilio_mode == "mock":
        twilio_detail = "Mode mock, aucun envoi WhatsApp réel"
    elif twilio_live_ready:
        twilio_detail = "Configuration présente"
    else:
        twilio_detail = "Sender non configuré"

    backup = _latest_backup_status(settings.environment)
    environment = (settings.environment or "local").lower()
    external_environment = environment not in {"local", "test"}
    api_security_ok = not external_environment or bool(settings.api_token)
    mock_webhook_security_ok = not external_environment or bool(
        settings.mock_webhook_token or settings.api_token
    )
    production_seed_ok = environment not in {"prod", "production"} or not settings.seed_demo_data
    workflow_ok = (
        conversations_without_action == 0
        and resolved_conversations_with_action_count == 0
        and conversations_with_multiple_main_actions == 0
    )
    checks = [
        _readiness_check(
            "SchoolDrive",
            bool(schooldrive_latest),
            "Webhook reçu" if schooldrive_latest else "Aucun webhook reçu",
            "warning",
        ),
        _readiness_check(
            "Front",
            bool(front_match_counts),
            "Zone tampon alimentée" if front_match_counts else "Zone tampon vide",
            "info",
        ),
        _readiness_check(
            "Twilio",
            twilio_ready,
            twilio_detail,
            "warning",
        ),
        _readiness_check(
            "Backup",
            bool(backup.get("exists")),
            "Backup trouvé" if backup.get("exists") else "Aucun backup trouvé",
            "warning",
        ),
        _readiness_check(
            "Workflow",
            workflow_ok,
            "Aucune conversation active sans action"
            if workflow_ok
            else (
                f"{conversations_without_action} sans action, "
                f"{resolved_conversations_with_action_count} terminée(s) avec action, "
                f"{conversations_with_multiple_main_actions} doublon(s) d'action"
            ),
            "danger",
        ),
        _readiness_check(
            "API security",
            api_security_ok and mock_webhook_security_ok,
            "API et webhook mock protégés"
            if api_security_ok and mock_webhook_security_ok
            else "Token API ou token mock manquant",
            "danger",
        ),
        _readiness_check(
            "Seed data",
            production_seed_ok,
            "Configuration seed compatible avec l'environnement"
            if production_seed_ok
            else "Données démo activées en production",
            "danger",
        ),
    ]

    return {
        "environment": settings.environment,
        "checks": checks,
        "schooldrive": {
            "token_configured": bool(settings.schooldrive_webhook_token),
            "lead_count": schooldrive_lead_count,
            "status_counts": schooldrive_status_counts,
            "latest_events": schooldrive_latest,
        },
        "front": {
            "token_configured": bool(settings.front_api_token),
            "match_counts": front_match_counts,
            "migration_counts": front_migration_counts,
            "message_count": front_message_count,
            "attached_message_count": front_attached_count,
            "latest_records": front_latest,
        },
        "twilio": {
            "mode": settings.twilio_mode,
            "content_read_only": bool(settings.twilio_content_read_only),
            "account_configured": bool(settings.twilio_account_sid),
            "sender": settings.twilio_whatsapp_sender or "",
            "messaging_service_sid": settings.twilio_messaging_service_sid or "",
            "webhook_url": settings.twilio_webhook_url or "",
            "status_callback_configured": bool(settings.twilio_status_callback_url),
            "status_callback_url": settings.twilio_status_callback_url or "",
            "validate_signature": bool(settings.twilio_validate_signature),
            "status_counts": twilio_status_counts,
            "latest_messages": twilio_latest,
        },
        "backup": backup,
        "workflow": {
            "open_action_count": open_action_count,
            "blocked_action_count": blocked_action_count,
            "open_bug_count": open_bug_count,
            "pending_template_request_count": pending_template_request_count,
            "obsolete_sequence_reference_count": obsolete_sequence_reference_count,
            "active_followup_missing_step_count": active_followup_missing_step_count,
            "schooldrive_waiting_first_autoresponder_count": schooldrive_waiting_first_autoresponder_count,
            "open_conversations_without_action": conversations_without_action,
            "resolved_conversations_with_action_count": resolved_conversations_with_action_count,
            "conversations_with_multiple_main_actions": conversations_with_multiple_main_actions,
        },
        "security": {
            "api_token_configured": bool(settings.api_token),
            "mock_webhook_token_configured": bool(settings.mock_webhook_token),
            "seed_demo_data": bool(settings.seed_demo_data),
        },
    }


def _scalar_count(conn: Any, query: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _count_by(conn: Any, table_name: str, column_name: str) -> dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT coalesce({column_name}, 'unknown') AS key, COUNT(*) AS count
        FROM {table_name}
        GROUP BY coalesce({column_name}, 'unknown')
        ORDER BY count DESC, key
        """
    ).fetchall()
    return {str(row["key"]): int(row["count"]) for row in rows}


def _readiness_check(
    name: str,
    ok: bool,
    detail: str,
    fail_level: str = "warning",
) -> dict[str, str]:
    return {
        "name": name,
        "state": "ready" if ok else fail_level,
        "detail": detail,
    }


def _latest_backup_status(environment: str) -> dict[str, Any]:
    settings = get_settings()
    candidates = [
        settings.root_dir.parent.parent / "backups" / environment,
        settings.root_dir / "backups" / environment,
        Path("backups") / environment,
    ]
    for directory in candidates:
        try:
            backups = sorted(
                directory.glob("*.db.gz"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            backups = []
        if backups:
            latest = backups[0]
            return {
                "exists": True,
                "path": str(latest),
                "updated_at": iso_utc(datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)),
                "size_bytes": latest.stat().st_size,
            }
    return {
        "exists": False,
        "path": "",
        "updated_at": "",
        "size_bytes": 0,
        "searched": [str(path) for path in candidates],
    }


def followups_are_blocked(record: dict[str, Any]) -> bool:
    return (
        record.get("lead_status") in STOP_QUALIFICATION_STATUSES
        or record.get("contact_status") in STOP_CONTACT_STATUSES
    )


def ingest_schooldrive_snapshot(envelope: dict[str, Any]) -> dict[str, Any]:
    event_id = str(envelope.get("event_id") or "").strip()
    environment = str(envelope.get("environment") or "").strip()
    occurred_at = _normalize_required_iso(envelope.get("occurred_at"), "occurred_at")
    data = envelope.get("data") or {}
    schooldrive_id = str(data.get("schooldrive_id") or "").strip()
    lead_type = str(data.get("lead_type") or "").strip()
    aggregated_updated_at = _normalize_required_iso(
        data.get("aggregated_updated_at"), "data.aggregated_updated_at"
    )

    if not event_id:
        raise ValueError("event_id is required.")
    if not schooldrive_id:
        raise ValueError("data.schooldrive_id is required.")
    if lead_type not in {"lead", "presubscription"}:
        raise ValueError("data.lead_type must be lead or presubscription.")

    now = iso_utc()
    payload_json = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
    settings = get_settings()
    with connect() as conn:
        duplicate = conn.execute(
            "SELECT lead_id, status FROM schooldrive_webhook_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if duplicate:
            return {
                "status": "duplicate",
                "accepted": False,
                "lead_id": duplicate["lead_id"],
                "schooldrive_id": schooldrive_id,
            }

        existing = row_to_dict(
            conn.execute(
                """
                SELECT
                    id, schooldrive_aggregated_updated_at,
                    schooldrive_last_event_occurred_at, schooldrive_last_event_id
                FROM leads
                WHERE schooldrive_lead_id = ?
                """,
                (schooldrive_id,),
            ).fetchone()
        )
        if existing and not _schooldrive_snapshot_is_newer(
            incoming_aggregated_at=aggregated_updated_at,
            incoming_occurred_at=occurred_at,
            incoming_event_id=event_id,
            current_aggregated_at=existing.get("schooldrive_aggregated_updated_at"),
            current_occurred_at=existing.get("schooldrive_last_event_occurred_at"),
            current_event_id=existing.get("schooldrive_last_event_id"),
        ):
            conn.execute(
                """
                INSERT INTO schooldrive_webhook_events (
                    event_id, environment, schooldrive_id, lead_id, occurred_at,
                    aggregated_updated_at, status, ignored_reason, payload_json, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'ignored', 'stale_snapshot', ?, ?)
                """,
                (
                    event_id,
                    environment,
                    schooldrive_id,
                    existing["id"],
                    occurred_at,
                    aggregated_updated_at,
                    payload_json,
                    now,
                ),
            )
            return {
                "status": "ignored",
                "accepted": False,
                "ignored_reason": "stale_snapshot",
                "lead_id": existing["id"],
                "schooldrive_id": schooldrive_id,
            }

        if not existing:
            ignored_reason = _new_schooldrive_snapshot_ignore_reason(data, settings)
            if ignored_reason:
                _insert_schooldrive_ignored_event(
                    conn,
                    event_id=event_id,
                    environment=environment,
                    schooldrive_id=schooldrive_id,
                    lead_id=None,
                    occurred_at=occurred_at,
                    aggregated_updated_at=aggregated_updated_at,
                    ignored_reason=ignored_reason,
                    payload_json=payload_json,
                    received_at=now,
                )
                return {
                    "status": "ignored",
                    "accepted": False,
                    "ignored_reason": ignored_reason,
                    "lead_id": None,
                    "schooldrive_id": schooldrive_id,
                }

        lead_id, conversation_id, created = _upsert_schooldrive_lead(
            conn,
            data=data,
            event_id=event_id,
            occurred_at=occurred_at,
            aggregated_updated_at=aggregated_updated_at,
            payload_json=payload_json,
        )
        _replace_schooldrive_autoresponders(
            conn,
            lead_id=lead_id,
            conversation_id=conversation_id,
            schooldrive_id=schooldrive_id,
            autoresponders=data.get("whatsapp_autoresponders") or [],
            occurred_at=occurred_at,
            aggregated_updated_at=aggregated_updated_at,
        )
        if data.get("is_archived"):
            _apply_schooldrive_archive(
                conn,
                lead_id=lead_id,
                conversation_id=conversation_id,
                archive_reason=data.get("archive_reason"),
            )
        else:
            skip_automatic_followups = _apply_schooldrive_business_signals(
                conn,
                lead_id=lead_id,
                conversation_id=conversation_id,
                data=data,
            )
            if not skip_automatic_followups:
                _ensure_initial_schooldrive_followup(
                    conn,
                    lead_id=lead_id,
                    conversation_id=conversation_id,
                )
                if _latest_sent_schooldrive_autoresponder_at(conn, lead_id):
                    _ensure_course_start_followup(
                        conn,
                        lead_id=lead_id,
                        conversation_id=conversation_id,
                    )

        conn.execute(
            """
            INSERT INTO schooldrive_webhook_events (
                event_id, environment, schooldrive_id, lead_id, occurred_at,
                aggregated_updated_at, status, payload_json, received_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'accepted', ?, ?)
            """,
            (
                event_id,
                environment,
                schooldrive_id,
                lead_id,
                occurred_at,
                aggregated_updated_at,
                payload_json,
                now,
            ),
        )
        insert_event(
            conn,
            lead_id,
            "schooldrive_snapshot_ingested",
            new={
                "schooldrive_id": schooldrive_id,
                "event_id": event_id,
                "created": created,
                "aggregated_updated_at": aggregated_updated_at,
                "whatsapp_autoresponders": len(data.get("whatsapp_autoresponders") or []),
            },
            metadata={"conversation_id": conversation_id},
        )
    return {
        "status": "created" if created else "updated",
        "accepted": True,
        "lead_id": lead_id,
        "conversation_id": conversation_id,
        "schooldrive_id": schooldrive_id,
    }


def _normalize_required_iso(value: Any, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} is required.")
    try:
        return iso_utc(parse_dt(str(value)))
    except Exception as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp.") from exc


def _normalize_optional_iso(value: Any) -> str | None:
    if not value:
        return None
    return iso_utc(parse_dt(str(value)))


def _schooldrive_snapshot_is_newer(
    incoming_aggregated_at: str,
    incoming_occurred_at: str,
    incoming_event_id: str,
    current_aggregated_at: str | None,
    current_occurred_at: str | None,
    current_event_id: str | None,
) -> bool:
    if not current_aggregated_at:
        return True
    incoming = (
        parse_dt(incoming_aggregated_at),
        parse_dt(incoming_occurred_at),
        incoming_event_id,
    )
    current = (
        parse_dt(current_aggregated_at),
        parse_dt(current_occurred_at) if current_occurred_at else parse_dt(current_aggregated_at),
        current_event_id or "",
    )
    return incoming > current


def _clean_schooldrive_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _schooldrive_course_fields(data: dict[str, Any]) -> dict[str, str | None]:
    course = data.get("course") or {}
    product = data.get("product") or {}
    if not isinstance(course, dict):
        course = {}
    if not isinstance(product, dict):
        product = {}

    category_raw = course.get("category")
    category_id = None
    category_short_name = None
    category_name = None
    if isinstance(category_raw, dict):
        category_id = _clean_schooldrive_text(category_raw.get("id"))
        category_short_name = _clean_schooldrive_text(
            category_raw.get("short_name")
            or category_raw.get("short_title")
            or category_raw.get("system_id")
        )
        category_name = _clean_schooldrive_text(category_raw.get("name"))
    else:
        category_short_name = _clean_schooldrive_text(category_raw)

    course_id = _clean_schooldrive_text(
        course.get("id")
        or course.get("course_id")
        or category_id
        or category_short_name
    )
    course_title = _clean_schooldrive_text(
        course.get("short_name")
        or course.get("course_name")
        or course.get("session_name")
        or course.get("name")
        or category_name
        or category_short_name
    )

    roadmap_id = _clean_schooldrive_text(product.get("roadmap_descriptive_id"))
    if not course and roadmap_id:
        course_id = roadmap_id
        course_title = f"Roadmap {roadmap_id}"

    return {
        "course_id": course_id,
        "course_category_short_title": category_short_name,
        "course_title": course_title,
    }


def _normalize_schooldrive_course_start(value: Any) -> str | None:
    text = _clean_schooldrive_text(value)
    if not text:
        return None
    try:
        return iso_utc(parse_dt(text))
    except Exception:
        pass
    try:
        return iso_utc(parse_dt(f"{text}T08:00:00Z"))
    except Exception:
        return None


def _upsert_schooldrive_lead(
    conn: Any,
    data: dict[str, Any],
    event_id: str,
    occurred_at: str,
    aggregated_updated_at: str,
    payload_json: str,
) -> tuple[int, int, bool]:
    now = iso_utc()
    schooldrive_id = str(data.get("schooldrive_id") or "").strip()
    person = data.get("person") or {}
    first_name = str(person.get("first_name") or "").strip() or "Inconnu(e)"
    last_name = str(person.get("last_name") or "").strip()
    phone = str(person.get("phone") or "").strip() or None
    email = str(person.get("email") or "").strip() or None
    lead_type = str(data.get("lead_type") or "lead").strip()
    course_fields = _schooldrive_course_fields(data)
    course_id = course_fields["course_id"]
    category = course_fields["course_category_short_title"]
    course_name = course_fields["course_title"]
    source_type = "paid_ads" if lead_type == "lead" else "organic"
    archived_at = _normalize_optional_iso(data.get("archived_at"))
    is_archived = 1 if bool(data.get("is_archived")) else 0
    archive_reason = str(data.get("archive_reason") or "").strip() or None
    url = str(data.get("url") or "").strip() or None
    schooldrive_status = str(data.get("status") or "").strip() or None

    existing = row_to_dict(
        conn.execute(
            "SELECT id FROM leads WHERE schooldrive_lead_id = ?",
            (schooldrive_id,),
        ).fetchone()
    )
    if existing:
        lead_id = int(existing["id"])
        conn.execute(
            """
            UPDATE leads
            SET first_name = ?, last_name = ?, email = ?, phone_e164 = ?, phone_raw = ?,
                course_id = ?, course_category_short_title = ?, course_title = ?,
                lead_type = ?, source = 'schooldrive_webhook', acquisition_type = ?,
                schooldrive_url = ?, schooldrive_status = ?,
                schooldrive_aggregated_updated_at = ?,
                schooldrive_last_event_occurred_at = ?,
                schooldrive_last_event_id = ?,
                schooldrive_is_archived = ?, schooldrive_archived_at = ?,
                schooldrive_archive_reason = ?, schooldrive_payload_json = ?,
                identity_status = 'verified',
                identity_review_note = NULL,
                identity_candidates_json = NULL,
                last_schooldrive_sync_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                first_name,
                last_name,
                email,
                phone,
                phone,
                course_id,
                category,
                course_name,
                lead_type,
                source_type,
                url,
                schooldrive_status,
                aggregated_updated_at,
                occurred_at,
                event_id,
                is_archived,
                archived_at,
                archive_reason,
                payload_json,
                now,
                now,
                lead_id,
            ),
        )
        created = False
    else:
        setter_id = _default_active_user_id(conn, "setter")
        closer_id = default_closer_user_id(conn)
        cursor = conn.execute(
            """
            INSERT INTO leads (
                schooldrive_lead_id, first_name, last_name, email, phone_e164, phone_raw,
                course_id, course_category_short_title, course_title, lead_type,
                source, acquisition_type, lead_status, contact_status, sales_stage,
                temperature, setter_user_id, closer_user_id, schooldrive_url,
                schooldrive_status, schooldrive_aggregated_updated_at,
                schooldrive_last_event_occurred_at, schooldrive_last_event_id,
                schooldrive_is_archived, schooldrive_archived_at,
                schooldrive_archive_reason, schooldrive_payload_json,
                identity_status, identity_review_note, identity_candidates_json,
                last_schooldrive_sync_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'schooldrive_webhook', ?,
                'eligible', 'contact_allowed', 'new', 'warm',
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                schooldrive_id,
                first_name,
                last_name,
                email,
                phone,
                phone,
                course_id,
                category,
                course_name,
                lead_type,
                source_type,
                setter_id,
                closer_id,
                url,
                schooldrive_status,
                aggregated_updated_at,
                occurred_at,
                event_id,
                is_archived,
                archived_at,
                archive_reason,
                payload_json,
                IDENTITY_STATUS_VERIFIED,
                None,
                None,
                now,
                now,
                now,
            ),
        )
        lead_id = int(cursor.lastrowid)
        created = True

    conversation = conn.execute(
        "SELECT id FROM conversations WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
        (lead_id,),
    ).fetchone()
    if conversation:
        conversation_id = int(conversation["id"])
        conn.execute(
            """
            UPDATE conversations
            SET recipient_phone_e164 = coalesce(?, recipient_phone_e164), updated_at = ?
            WHERE id = ?
            """,
            (phone, now, conversation_id),
        )
    else:
        conversation_id = int(
            conn.execute(
                """
                INSERT INTO conversations (lead_id, recipient_phone_e164, status, created_at, updated_at)
                VALUES (?, ?, 'open', ?, ?)
                """,
                (lead_id, phone, now, now),
            ).lastrowid
        )
    return lead_id, conversation_id, created


def _replace_schooldrive_autoresponders(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    schooldrive_id: str,
    autoresponders: list[dict[str, Any]],
    occurred_at: str,
    aggregated_updated_at: str,
) -> None:
    now = iso_utc()
    conn.execute("DELETE FROM schooldrive_whatsapp_autoresponders WHERE lead_id = ?", (lead_id,))
    conn.execute(
        """
        DELETE FROM messages
        WHERE lead_id = ? AND conversation_id = ? AND channel = 'schooldrive_autoresponder'
        """,
        (lead_id, conversation_id),
    )
    for item in autoresponders:
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            continue
        status = str(item.get("status") or "").strip() or "unknown"
        template = (
            str(
                item.get("template")
                or item.get("short_name")
                or item.get("whatsapp_template_id")
                or ""
            ).strip()
            or "template inconnu"
        )
        sent_at = _normalize_optional_iso(item.get("sent_at"))
        item_json = json.dumps(item, ensure_ascii=False, sort_keys=True)
        conn.execute(
            """
            INSERT INTO schooldrive_whatsapp_autoresponders (
                lead_id, schooldrive_id, message_id, autoresponder_id, template,
                status, sent_at, payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lead_id,
                schooldrive_id,
                message_id,
                item.get("autoresponder_id"),
                template,
                status,
                sent_at,
                item_json,
                now,
                now,
            ),
        )
        message_time = sent_at or aggregated_updated_at or occurred_at
        body = _schooldrive_autoresponder_message_body(
            template,
            status,
            item.get("whatsapp_send_body"),
        )
        conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body,
                twilio_status, sent_at, created_at
            ) VALUES (?, ?, 'outbound', 'schooldrive_autoresponder', ?, ?, ?, ?)
            """,
            (conversation_id, lead_id, body, status, sent_at, message_time),
        )

    row = conn.execute(
        """
        SELECT MAX(sent_at) AS last_outbound_at
        FROM messages
        WHERE conversation_id = ? AND direction = 'outbound' AND sent_at IS NOT NULL
        """,
        (conversation_id,),
    ).fetchone()
    conn.execute(
        """
        UPDATE conversations
        SET last_outbound_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (row["last_outbound_at"] if row else None, now, conversation_id),
    )


def _schooldrive_autoresponder_message_body(
    template: str,
    status: str,
    whatsapp_send_body: Any = None,
) -> str:
    if status == "sent":
        body = str(whatsapp_send_body or "").strip()
        if body:
            return body
        return f"WhatsApp automatique SchoolDrive envoyé : {template}"
    if status in {"queued", "sending", "moderation_pending"}:
        return f"WhatsApp automatique SchoolDrive en attente : {template} ({status})"
    return f"WhatsApp automatique SchoolDrive non envoyé : {template} ({status})"


def _latest_sent_schooldrive_autoresponder_at(conn: Any, lead_id: int) -> str | None:
    row = conn.execute(
        """
        SELECT MIN(sent_at) AS sent_at
        FROM schooldrive_whatsapp_autoresponders
        WHERE lead_id = ? AND status = 'sent' AND sent_at IS NOT NULL
        """,
        (lead_id,),
    ).fetchone()
    return row["sent_at"] if row else None


def _ensure_initial_schooldrive_followup(
    conn: Any,
    lead_id: int,
    conversation_id: int,
) -> None:
    sent_at = _latest_sent_schooldrive_autoresponder_at(conn, lead_id)
    if not sent_at:
        return
    lead = row_to_dict(
        conn.execute(
            """
            SELECT first_name, last_name, lead_status, contact_status, course_category_short_title
            FROM leads
            WHERE id = ?
            """,
            (lead_id,),
        ).fetchone()
    )
    if not lead or followups_are_blocked(lead):
        return
    if not _course_category_is_supported(conn, lead.get("course_category_short_title")):
        _ensure_unconfigured_course_category_review(
            conn,
            lead_id=lead_id,
            conversation_id=conversation_id,
            lead=lead,
        )
        return
    active = _first_active_action_for_lead(conn, lead_id)
    first_step = _get_sequence_step(conn, "lead_no_reply", 1)
    if not first_step:
        return
    due_at = _due_for_sequence_step(sent_at, first_step)
    setter2_id = setter2_user_id(conn)
    if not setter2_id:
        return
    if active:
        if active.get("type") == "follow_up" and active.get("trigger_reason") in {
            "schooldrive_initial_autoresponder_sent",
            "schooldrive_initial_followup_updated",
        }:
            conn.execute(
                """
                UPDATE tasks
                SET assigned_to_user_id = ?, due_at = ?, updated_at = ?,
                    trigger_reason = 'schooldrive_initial_followup_updated'
                WHERE id = ?
                """,
                (setter2_id, due_at, iso_utc(), active["id"]),
            )
        return
    existing_initial_followup = conn.execute(
        """
        SELECT id
        FROM tasks
        WHERE lead_id = ?
          AND trigger_reason IN (
            'schooldrive_initial_autoresponder_sent',
            'schooldrive_initial_followup_updated'
          )
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if existing_initial_followup:
        return
    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=conversation_id,
        action_type="follow_up",
        title=f"Relancer {lead_full_name(lead)}",
        assigned_to_user_id=setter2_id,
        created_by_user_id=None,
        urgency="normal",
        due_at=due_at,
        status="planned",
        trigger_reason="schooldrive_initial_autoresponder_sent",
        sequence_code="lead_no_reply",
        sequence_step_index=1,
        metadata=_sequence_anchor_metadata(sent_at, "Premier WhatsApp automatique SchoolDrive"),
    )
    insert_event(
        conn,
        lead_id,
        "followup_scheduled_from_schooldrive_autoresponder",
        new={"task_id": action_id, "due_at": due_at, "assigned_to_user_id": setter2_id},
        metadata={"conversation_id": conversation_id},
    )
    _ensure_course_start_followup(conn, lead_id, conversation_id)


def _course_start_anchor_for_lead(conn: Any, lead_id: int) -> tuple[str | None, str | None]:
    lead = row_to_dict(
        conn.execute(
            """
            SELECT course_category_short_title, schooldrive_payload_json
            FROM leads
            WHERE id = ?
            """,
            (lead_id,),
        ).fetchone()
    )
    if not lead:
        return None, None

    payload_start_date = None
    try:
        payload = json.loads(lead.get("schooldrive_payload_json") or "{}")
        payload_start_date = (
            ((payload.get("data") or {}).get("course") or {}).get("start_date")
            or None
        )
    except (TypeError, json.JSONDecodeError):
        payload_start_date = None

    normalized_payload_start = _normalize_schooldrive_course_start(payload_start_date)
    if normalized_payload_start:
        return normalized_payload_start, "Date de cours SchoolDrive"

    category = (lead.get("course_category_short_title") or "").strip().upper()
    if not category:
        return None, None
    row = conn.execute(
        """
        SELECT default_start_date, default_course_name
        FROM course_default_sessions
        WHERE course_category = ? AND active = 1
        """,
        (category,),
    ).fetchone()
    if not row:
        return None, None
    return f"{row['default_start_date']}T08:00:00Z", f"Session de référence {row['default_course_name']}"


def _first_relevant_course_start_step(
    conn: Any,
    anchor_iso: str,
    now: datetime,
) -> tuple[dict[str, Any], str] | None:
    rows = conn.execute(
        """
        SELECT *
        FROM sequence_steps
        WHERE sequence_code = 'course_start' AND active = 1
        ORDER BY step_index
        """
    ).fetchall()
    steps = rows_to_dicts(rows)
    if not steps:
        return None

    anchor = parse_dt(anchor_iso)
    if not anchor or anchor < now:
        return None

    fallback: tuple[dict[str, Any], str] | None = None
    for step in steps:
        due_at = _due_for_sequence_step(anchor_iso, step)
        due_dt = parse_dt(due_at)
        if not due_dt:
            continue
        if due_dt >= now:
            return step, due_at
        fallback = (step, iso_utc(now))
    return fallback


def _ensure_course_start_followup(
    conn: Any,
    lead_id: int,
    conversation_id: int,
) -> None:
    lead = row_to_dict(
        conn.execute(
            """
            SELECT first_name, last_name, lead_status, contact_status, course_category_short_title
            FROM leads
            WHERE id = ?
            """,
            (lead_id,),
        ).fetchone()
    )
    if not lead or followups_are_blocked(lead):
        return
    if not _course_category_is_supported(conn, lead.get("course_category_short_title")):
        return

    active_call = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("setting_call", "closing_call"),
    )
    if active_call:
        return

    existing_course = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("follow_up",),
        sequence_codes=("course_start",),
    )
    if existing_course:
        return

    anchor_iso, anchor_label = _course_start_anchor_for_lead(conn, lead_id)
    if not anchor_iso:
        return
    step_and_due = _first_relevant_course_start_step(conn, anchor_iso, utc_now())
    if not step_and_due:
        anchor_dt = parse_dt(anchor_iso)
        if anchor_dt and anchor_dt < utc_now() and (anchor_label or "").startswith("Session de référence"):
            _ensure_default_session_review(
                conn,
                lead_id=lead_id,
                conversation_id=conversation_id,
                course_category=lead.get("course_category_short_title"),
                anchor_label=anchor_label,
                anchor_iso=anchor_iso,
            )
        return
    step, due_at = step_and_due

    active_followup = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("follow_up",),
    )
    course_due = parse_dt(due_at)
    should_replace_followup = False
    if active_followup and active_followup.get("sequence_code") != "course_start":
        followup_due = parse_dt(active_followup.get("due_at"))
        if course_due and followup_due:
            should_replace_followup = abs((course_due - followup_due).total_seconds()) <= 24 * 3600
        if course_due and course_due <= utc_now() + timedelta(hours=24):
            should_replace_followup = True
        if not should_replace_followup:
            return
        _complete_open_actions_for_lead(
            conn,
            lead_id,
            user_id=None,
            outcome="Relance annulée : relance début de cours prioritaire",
            included_types=("follow_up",),
            excluded_sequence_codes=("course_start",),
        )

    setter2_id = setter2_user_id(conn)
    if not setter2_id:
        return
    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=conversation_id,
        action_type="follow_up",
        title=f"Relancer {lead_full_name(lead)} avant début de cours",
        assigned_to_user_id=setter2_id,
        created_by_user_id=None,
        urgency="high",
        due_at=due_at,
        status="planned" if course_due and course_due > utc_now() else "open",
        trigger_reason="course_start_approaching",
        sequence_code="course_start",
        sequence_step_index=step["step_index"],
        metadata=_sequence_anchor_metadata(anchor_iso, anchor_label or "Début de cours"),
    )
    insert_event(
        conn,
        lead_id,
        "course_start_followup_scheduled",
        new={
            "task_id": action_id,
            "due_at": due_at,
            "step_index": step["step_index"],
            "assigned_to_user_id": setter2_id,
        },
        metadata={"conversation_id": conversation_id, "anchor_at": anchor_iso},
    )


def _ensure_default_session_review(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    course_category: str | None,
    anchor_label: str | None,
    anchor_iso: str,
) -> None:
    category = (course_category or "").strip().upper() or "catégorie inconnue"
    admin_action_id = _ensure_admin_action(
        conn,
        "default_session_review",
        f"Mettre à jour la session de référence {category}",
        (
            f"La session de référence utilisée pour {category} est dépassée "
            f"({anchor_label or anchor_iso}). Sélectionner la prochaine session pertinente."
        ),
        lead_id=lead_id,
        conversation_id=conversation_id,
        metadata={
            "course_category": category,
            "anchor_label": anchor_label,
            "anchor_iso": anchor_iso,
        },
    )
    if admin_action_id:
        insert_event(
            conn,
            lead_id,
            "default_session_review_created",
            new={"admin_action_id": admin_action_id, "course_category": category},
            metadata={"conversation_id": conversation_id},
        )


def _course_category_is_supported(conn: Any, category: str | None) -> bool:
    normalized = (category or "").strip().upper()
    if not normalized:
        return False
    row = conn.execute(
        """
        SELECT id
        FROM course_categories
        WHERE course_category = ? AND active = 1
        """,
        (normalized,),
    ).fetchone()
    return bool(row)


def _ensure_unconfigured_course_category_review(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    lead: dict[str, Any],
) -> None:
    existing = conn.execute(
        """
        SELECT id
        FROM tasks
        WHERE lead_id = ?
          AND status IN ('open', 'planned', 'in_progress', 'blocked')
          AND trigger_reason = 'unconfigured_course_category'
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if existing:
        return
    assignee_id = setter1_user_id(conn) or _default_active_user_id(conn, "setter")
    if not assignee_id:
        return
    now = iso_utc()
    category = (lead.get("course_category_short_title") or "non renseignée").strip()
    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=conversation_id,
        action_type="other",
        title=f"Revoir catégorie {category} pour {lead_full_name(lead)}",
        assigned_to_user_id=assignee_id,
        created_by_user_id=None,
        urgency="normal",
        due_at=now,
        status="open",
        trigger_reason="unconfigured_course_category",
        description=(
            "Catégorie de cours non pilotée dans Sales Cockpit. "
            "Lire la conversation et décider du suivi manuel."
        ),
    )
    insert_event(
        conn,
        lead_id,
        "unconfigured_course_category_review_created",
        new={"task_id": action_id, "course_category": category},
        metadata={"conversation_id": conversation_id},
    )


def _apply_schooldrive_archive(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    archive_reason: Any,
) -> None:
    now = iso_utc()
    reason = str(archive_reason or "").strip() or "Archivé dans SchoolDrive"
    _complete_open_actions_for_lead(
        conn,
        lead_id,
        user_id=None,
        outcome="Archivé dans SchoolDrive",
    )
    conn.execute(
        """
        UPDATE conversations
        SET status = 'resolved', resolution_reason = 'handled_elsewhere',
            resolution_note = ?, resolved_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (reason, now, now, conversation_id),
    )
    _insert_internal_note_message(
        conn,
        lead_id,
        conversation_id,
        None,
        f"Archivé dans SchoolDrive : {reason}",
        now,
    )


def _apply_schooldrive_business_signals(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    data: dict[str, Any],
) -> bool:
    now = iso_utc()
    signed, signed_source = _schooldrive_signed_signal(data)
    if signed:
        _complete_open_actions_for_lead(
            conn,
            lead_id,
            user_id=None,
            outcome=f"Signature confirmée par SchoolDrive ({signed_source})",
        )
        conn.execute(
            "UPDATE leads SET lead_status = 'signed', updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
        conn.execute(
            """
            UPDATE conversations
            SET status = 'resolved', resolution_reason = 'signed',
                resolution_note = ?, resolved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (f"Signature confirmée par SchoolDrive ({signed_source}).", now, now, conversation_id),
        )
        _insert_internal_note_message(
            conn,
            lead_id,
            conversation_id,
            None,
            f"SchoolDrive : signature confirmée ({signed_source}). Relances arrêtées.",
            now,
        )
        return True

    do_not_contact, dnc_source = _schooldrive_do_not_contact_signal(data)
    if do_not_contact:
        _complete_open_actions_for_lead(
            conn,
            lead_id,
            user_id=None,
            outcome=f"Ne plus contacter confirmé par SchoolDrive ({dnc_source})",
        )
        conn.execute(
            "UPDATE leads SET contact_status = 'do_not_contact', lead_status = 'eligible', updated_at = ? WHERE id = ?",
            (now, lead_id),
        )
        conn.execute(
            """
            UPDATE conversations
            SET status = 'resolved', resolution_reason = 'do_not_contact',
                resolution_note = ?, resolved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (f"Blocage importé depuis SchoolDrive : {dnc_source}.", now, now, conversation_id),
        )
        _insert_internal_note_message(
            conn,
            lead_id,
            conversation_id,
            None,
            f"SchoolDrive : Ne plus contacter ({dnc_source}). Tous les canaux commerciaux sont bloqués.",
            now,
        )
        return True

    course_full, course_full_source = _schooldrive_course_full_signal(data)
    if course_full:
        _complete_open_actions_for_lead(
            conn,
            lead_id,
            user_id=None,
            outcome="Relances annulées : cours complet dans SchoolDrive",
            included_types=("follow_up",),
        )
        active_call = _first_active_action_for_lead(
            conn,
            lead_id,
            action_types=("setting_call", "closing_call"),
        )
        if active_call:
            metadata = _task_metadata(active_call)
            metadata["schooldrive_course_full"] = True
            metadata["schooldrive_course_full_source"] = course_full_source
            description = active_call.get("description") or ""
            prefix = "SchoolDrive indique que la session est complète : proposer une autre session."
            conn.execute(
                """
                UPDATE tasks
                SET description = ?,
                    metadata_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    f"{prefix}\n\n{description}".strip(),
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    active_call["id"],
                ),
            )
            _insert_internal_note_message(
                conn,
                lead_id,
                conversation_id,
                None,
                f"SchoolDrive : cours complet ({course_full_source}). Relances annulées ; l'appel planifié reste prioritaire et doit servir à proposer une autre session.",
                now,
            )
            insert_event(
                conn,
                lead_id,
                "schooldrive_course_full_call_flagged",
                new={"task_id": active_call["id"], "source": course_full_source},
                metadata={"conversation_id": conversation_id},
            )
        else:
            _ensure_course_full_review(
                conn,
                lead_id=lead_id,
                conversation_id=conversation_id,
                source=course_full_source,
            )
        return True

    return False


def _schooldrive_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "y"}
    return False


def _schooldrive_signed_signal(data: dict[str, Any]) -> tuple[bool, str]:
    signed = data.get("signed")
    if isinstance(signed, dict):
        for key in ("is_signed", "signed", "value"):
            if _schooldrive_bool(signed.get(key)):
                return True, f"signed.{key}"
    for key in ("is_signed", "signed"):
        if _schooldrive_bool(data.get(key)):
            return True, key
    commercial = data.get("commercial") or {}
    if isinstance(commercial, dict) and _schooldrive_bool(commercial.get("is_signed")):
        return True, "commercial.is_signed"
    return False, ""


def _schooldrive_do_not_contact_signal(data: dict[str, Any]) -> tuple[bool, str]:
    contact = data.get("contact") or {}
    candidates: list[tuple[str, Any]] = [
        ("data.do_not_contact", data.get("do_not_contact")),
        ("data.do_not_relaunch", data.get("do_not_relaunch")),
        ("data.email_opt_out", data.get("email_opt_out")),
        ("data.whatsapp_opt_out", data.get("whatsapp_opt_out")),
        ("data.phone_opt_out", data.get("phone_opt_out")),
        ("data.blacklisted", data.get("blacklisted")),
    ]
    if isinstance(contact, dict):
        candidates.extend(
            [
                ("contact.do_not_contact", contact.get("do_not_contact")),
                ("contact.do_not_relaunch", contact.get("do_not_relaunch")),
                ("contact.email_opt_out", contact.get("email_opt_out")),
                ("contact.whatsapp_opt_out", contact.get("whatsapp_opt_out")),
                ("contact.phone_opt_out", contact.get("phone_opt_out")),
                ("contact.blacklisted", contact.get("blacklisted")),
            ]
        )
    for source, value in candidates:
        if _schooldrive_bool(value):
            return True, source
    return False, ""


def _schooldrive_course_full_signal(data: dict[str, Any]) -> tuple[bool, str]:
    course = data.get("course") or {}
    if not isinstance(course, dict):
        return False, ""
    for key in ("is_full", "course_full", "session_full"):
        if _schooldrive_bool(course.get(key)):
            return True, f"course.{key}"
    for key in ("capacity_status", "session_status", "status"):
        if str(course.get(key) or "").strip().lower() in {"full", "complete", "complet", "sold_out"}:
            return True, f"course.{key}"
    seats = course.get("available_seats")
    if seats is not None:
        try:
            if int(seats) <= 0:
                return True, "course.available_seats"
        except (TypeError, ValueError):
            pass
    return False, ""


def _ensure_course_full_review(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    source: str,
) -> None:
    existing = conn.execute(
        """
        SELECT id
        FROM tasks
        WHERE lead_id = ?
          AND status IN ('open', 'planned', 'in_progress', 'blocked')
          AND trigger_reason = 'schooldrive_course_full'
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    if existing:
        return
    lead = row_to_dict(conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone())
    if not lead:
        return
    assignee_id = setter1_user_id(conn) or _default_active_user_id(conn, "setter")
    if not assignee_id:
        return
    now = iso_utc()
    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=conversation_id,
        action_type="other",
        title=f"Proposer une autre session à {lead_full_name(lead)}",
        assigned_to_user_id=assignee_id,
        created_by_user_id=None,
        urgency="high",
        due_at=now,
        status="open",
        trigger_reason="schooldrive_course_full",
        description="SchoolDrive indique que la session est complète. Lire le dossier et proposer une autre session.",
        metadata={"schooldrive_source": source},
    )
    _insert_internal_note_message(
        conn,
        lead_id,
        conversation_id,
        None,
        f"SchoolDrive : cours complet ({source}). Relances annulées, proposer une autre session.",
        now,
    )
    insert_event(
        conn,
        lead_id,
        "schooldrive_course_full_review_created",
        new={"task_id": action_id, "source": source},
        metadata={"conversation_id": conversation_id},
    )


def resolution_reason_requires_note(reason: str | None) -> bool:
    return any(
        item["value"] == reason and item["requires_note"]
        for item in RESOLUTION_REASONS
    )


def lead_full_name(record: dict[str, Any]) -> str:
    first_name = str(record.get("first_name") or "").strip()
    last_name = str(record.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if not full_name or full_name.lower() == "whatsapp unknown":
        return "Inconnu(e)"
    return full_name


def setter2_user_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM users
        WHERE lower(email) = 'setter2@essr.ch' AND active = 1
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])
    return _default_active_user_id(conn, "setter")


def setter1_user_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM users
        WHERE role = 'setter'
          AND lower(email) != 'setter2@essr.ch'
          AND active = 1
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])
    return _default_active_user_id(conn, "setter")


def _is_setter1_user(conn: Any, user_id: int | None) -> bool:
    if not user_id:
        return False
    row = conn.execute(
        """
        SELECT role, email
        FROM users
        WHERE id = ? AND active = 1
        """,
        (user_id,),
    ).fetchone()
    return bool(
        row
        and row["role"] == "setter"
        and str(row["email"] or "").lower() != "setter2@essr.ch"
    )


def default_closer_user_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM users
        WHERE lower(email) = 'yasmine@essr.ch' AND active = 1
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])
    return _default_active_user_id(conn, "closer")


def list_conversations(
    search: str = "",
    stage: str = "all",
    queue: str = "all",
    responsibility: str = "all",
    limit: int | None = 300,
    offset: int = 0,
) -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if search:
        like = f"%{search.lower()}%"
        filters.append(
            """
            (
                lower(l.first_name || ' ' || l.last_name) LIKE ?
                OR lower(coalesce(l.email, '')) LIKE ?
                OR lower(coalesce(l.phone_e164, '')) LIKE ?
                OR lower(coalesce(l.course_category_short_title, '')) LIKE ?
                OR lower(coalesce(l.course_title, '')) LIKE ?
                OR lower(coalesce(l.lead_type, '')) LIKE ?
                OR lower(coalesce(last_msg.body, '')) LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like, like, like])
    if stage != "all":
        filters.append("l.sales_stage = ?")
        params.append(stage)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    limit_clause = ""
    if limit is not None:
        safe_limit = max(1, min(int(limit), 1000))
        safe_offset = max(0, int(offset))
        limit_clause = "LIMIT ? OFFSET ?"
        params.extend([safe_limit, safe_offset])

    query = f"""
        SELECT
            c.id AS conversation_id,
            l.id AS lead_id,
            l.schooldrive_lead_id,
            l.schooldrive_url,
            l.first_name,
            l.last_name,
            l.email,
            l.phone_e164,
            l.course_id,
            l.course_category_short_title,
            l.course_title,
            l.lead_type,
            l.acquisition_type,
            l.lead_status,
            l.contact_status,
            l.sales_stage,
            l.temperature,
            l.identity_status,
            l.identity_review_note,
            l.identity_candidates_json,
            setter.full_name AS setter_name,
            closer.full_name AS closer_name,
            c.last_inbound_at,
            c.last_outbound_at,
            c.status AS conversation_status,
            last_msg.body AS last_message_body,
            last_msg.direction AS last_message_direction,
            last_msg.created_at AS last_message_at,
            next_task.id AS next_action_id,
            next_task.type AS next_action_type,
            next_task.title AS next_action_title,
            next_task.description AS next_action_description,
            next_task.due_at AS next_action_due_at,
            next_task.urgency AS next_action_urgency,
            next_task.status AS next_action_status,
            next_task.assigned_to_user_id AS next_action_assigned_to_user_id,
            next_assignee.full_name AS next_action_assigned_to_name,
            next_assignee.role AS next_action_assigned_to_role,
            next_assignee.email AS next_action_assigned_to_email,
            (
                SELECT COUNT(*) FROM tasks t
                WHERE t.lead_id = l.id AND t.status IN ('open', 'in_progress', 'planned', 'blocked')
            ) AS open_tasks
        FROM conversations c
        JOIN leads l ON l.id = c.lead_id
        LEFT JOIN users setter ON setter.id = l.setter_user_id
        LEFT JOIN users closer ON closer.id = l.closer_user_id
        LEFT JOIN tasks next_task ON next_task.id = (
            SELECT t.id FROM tasks t
            WHERE t.lead_id = l.id AND t.status IN ('open', 'in_progress', 'planned', 'blocked')
            ORDER BY
                CASE WHEN t.due_at IS NULL THEN 1 ELSE 0 END,
                datetime(t.due_at) ASC,
                CASE t.urgency WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                t.id ASC
            LIMIT 1
        )
        LEFT JOIN users next_assignee ON next_assignee.id = next_task.assigned_to_user_id
        LEFT JOIN messages last_msg ON last_msg.id = (
            SELECT m.id FROM messages m
            WHERE m.conversation_id = c.id
            ORDER BY datetime(m.created_at) DESC, m.id DESC
            LIMIT 1
        )
        {where}
        ORDER BY datetime(coalesce(last_msg.created_at, c.updated_at)) DESC, c.id DESC
        {limit_clause}
    """
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    conversations = rows_to_dicts(rows)
    for conv in conversations:
        state = calculate_window(conv["last_inbound_at"])
        conv["window_state"] = state.state
        conv["window_is_open"] = state.is_open
        conv["window_closes_at"] = iso_utc(state.closes_at) if state.closes_at else None
        conv["work_queue"] = classify_work_queue(conv)

    if queue != "all":
        conversations = [conv for conv in conversations if conv["work_queue"] == queue]
    if responsibility != "all":
        conversations = [
            conv
            for conv in conversations
            if conversation_matches_responsibility(conv, responsibility)
        ]
    return conversations


def classify_work_queue(conv: dict[str, Any]) -> str:
    if followups_are_blocked(conv) and conv.get("next_action_type") != "contact_review":
        return "resolved"
    if conv.get("conversation_status") == "resolved":
        return "resolved"

    due_at = parse_dt(conv.get("next_action_due_at"))
    if due_at and due_at > utc_now():
        return "waiting"

    if conv.get("next_action_id"):
        return "todo"

    if conv.get("last_message_direction") == "inbound":
        return "todo"

    return "waiting"


def conversation_matches_responsibility(conv: dict[str, Any], responsibility: str) -> bool:
    if responsibility == "setter":
        return (
            conv.get("next_action_assigned_to_role") == "setter"
            or bool(conv.get("setter_name") and not conv.get("next_action_assigned_to_role"))
        )
    if responsibility == "closer":
        return (
            conv.get("next_action_assigned_to_role") == "closer"
            or bool(conv.get("closer_name") and not conv.get("next_action_assigned_to_role"))
        )
    return True


def get_conversation(conversation_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                c.*,
                l.schooldrive_lead_id,
                l.schooldrive_url,
                l.first_name,
                l.last_name,
                l.email,
                l.phone_e164,
                l.phone_raw,
                l.course_id,
                l.course_category_short_title,
                l.course_title,
                l.lead_type,
                l.acquisition_type,
                l.lead_status,
                l.contact_status,
                l.sales_stage,
                l.temperature,
                l.identity_status,
                l.identity_review_note,
                l.identity_candidates_json,
                l.setter_user_id,
                l.closer_user_id,
                setter.full_name AS setter_name,
                closer.full_name AS closer_name
            FROM conversations c
            JOIN leads l ON l.id = c.lead_id
            LEFT JOIN users setter ON setter.id = l.setter_user_id
            LEFT JOIN users closer ON closer.id = l.closer_user_id
            WHERE c.id = ?
            """,
            (conversation_id,),
        ).fetchone()
    conv = row_to_dict(row)
    if not conv:
        return None
    state = calculate_window(conv["last_inbound_at"])
    conv["window_state"] = state.state
    conv["window_is_open"] = state.is_open
    conv["window_reason"] = state.reason
    conv["window_closes_at"] = iso_utc(state.closes_at) if state.closes_at else None
    return conv


def get_next_action_for_lead(lead_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                t.*,
                u.full_name AS assigned_to_name,
                u.role AS assigned_to_role,
                u.email AS assigned_to_email
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE t.lead_id = ? AND t.status IN ('open', 'in_progress', 'planned', 'blocked')
            ORDER BY
                CASE t.type
                    WHEN 'reply' THEN 0
                    WHEN 'contact_review' THEN 1
                    ELSE 2
                END,
                CASE t.urgency WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                CASE WHEN t.due_at IS NULL THEN 1 ELSE 0 END,
                datetime(t.due_at) ASC,
                t.id ASC
            LIMIT 1
            """,
            (lead_id,),
        ).fetchone()
    return row_to_dict(row)


def list_actions_for_lead(lead_id: int, status: str = "all") -> list[dict[str, Any]]:
    filters = ["t.lead_id = ?"]
    params: list[Any] = [lead_id]
    if status != "all":
        filters.append("t.status = ?")
        params.append(status)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.*,
                u.full_name AS assigned_to_name,
                u.role AS assigned_to_role,
                u.email AS assigned_to_email
            FROM tasks t
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            WHERE {' AND '.join(filters)}
            ORDER BY
                CASE t.status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'done' THEN 2 ELSE 3 END,
                datetime(coalesce(t.due_at, t.created_at)) DESC,
                t.id DESC
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def create_next_action(
    lead_id: int,
    conversation_id: int | None,
    action_type: str,
    title: str,
    assigned_to_user_id: int,
    created_by_user_id: int,
    urgency: str = "normal",
    due_at: str | None = None,
    description: str | None = None,
    trigger_reason: str | None = None,
    sequence_code: str | None = None,
    sequence_step_index: int | None = None,
    previous_action_id: int | None = None,
    status: str = "open",
    blocked_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    with connect() as conn:
        if conversation_id is not None:
            conversation = conn.execute(
                "SELECT status FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation and conversation["status"] != "open":
                raise ValueError("Conversation terminée : réactivez-la avant de créer une action.")
        action_id = _insert_next_action(
            conn,
            lead_id=lead_id,
            conversation_id=conversation_id,
            action_type=action_type,
            title=title,
            assigned_to_user_id=assigned_to_user_id,
            created_by_user_id=created_by_user_id,
            urgency=urgency,
            due_at=due_at or iso_utc(),
            description=description,
            trigger_reason=trigger_reason,
            sequence_code=sequence_code,
            sequence_step_index=sequence_step_index,
            previous_action_id=previous_action_id,
            status=status,
            blocked_reason=blocked_reason,
            metadata=metadata,
        )
        insert_event(
            conn,
            lead_id,
            "next_action_created",
            user_id=created_by_user_id,
            new={
                "task_id": action_id,
                "type": action_type,
                "title": title,
                "assigned_to_user_id": assigned_to_user_id,
                "due_at": due_at,
                "urgency": urgency,
                "trigger_reason": trigger_reason,
                "sequence_code": sequence_code,
                "sequence_step_index": sequence_step_index,
            },
        )
    return action_id


def schedule_followup(
    conversation_id: int,
    user_id: int,
    assigned_to_user_id: int,
    due_at: str,
    urgency: str = "normal",
    notes: str | None = None,
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if followups_are_blocked(conv):
        return False, "Ce statut bloque les relances commerciales."
    if conv.get("status") != "open":
        return False, "Conversation terminée : réactivez-la avant de planifier une relance."

    full_name = lead_full_name(conv)
    title = f"Relancer {full_name}"
    with connect() as conn:
        _complete_open_actions_for_lead(
            conn,
            conv["lead_id"],
            user_id,
            outcome="Relance planifiée",
        )
        action_id = _insert_next_action(
            conn,
            lead_id=conv["lead_id"],
            conversation_id=conversation_id,
            action_type="follow_up",
            title=title,
            assigned_to_user_id=assigned_to_user_id,
            created_by_user_id=user_id,
            urgency=urgency,
            due_at=due_at,
            description=notes,
            trigger_reason="manual_followup_scheduled",
        )
        conn.execute(
            "UPDATE conversations SET status = 'open', updated_at = ? WHERE id = ?",
            (iso_utc(), conversation_id),
        )
        insert_event(
            conn,
            conv["lead_id"],
            "followup_scheduled",
            user_id=user_id,
            new={
                "task_id": action_id,
                "assigned_to_user_id": assigned_to_user_id,
                "due_at": due_at,
                "urgency": urgency,
                "notes": notes,
            },
        )
    return True, "Relance planifiée."

def assign_standard_next_action(
    conversation_id: int,
    user_id: int,
    action_type: str,
    assigned_to_user_id: int,
    due_at: str,
    note: str,
) -> tuple[bool, str]:
    allowed_types = {"reply", "follow_up", "setting_call", "closing_call"}
    if action_type not in allowed_types:
        return False, "Action standard invalide."

    note = note.strip()
    if not note:
        return False, "Une note est obligatoire pour attribuer une action."

    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if conv.get("status") != "open":
        return False, "Conversation terminée : réactivez-la avant de créer une action."
    if conv.get("contact_status") in STOP_CONTACT_STATUSES:
        return False, "Contact bloqué : le statut Ne plus contacter doit être levé avant de créer une action."
    if action_type == "follow_up" and followups_are_blocked(conv):
        return False, "Ce statut bloque les relances commerciales."

    with connect() as conn:
        assignee = row_to_dict(
            conn.execute(
                "SELECT id, full_name, role, email FROM users WHERE id = ? AND active = 1",
                (assigned_to_user_id,),
            ).fetchone()
        )
        if not assignee:
            return False, "Responsable invalide."

        assignee_role = assignee.get("role")
        assignee_email = str(assignee.get("email") or "").lower()
        if action_type in {"reply", "setting_call"} and (
            assignee_role != "setter" or assignee_email == "setter2@essr.ch"
        ):
            return False, "Cette action doit être attribuée à Setter I."
        if action_type == "follow_up" and assignee_role != "setter":
            return False, "Une relance doit être attribuée à un setter."
        if action_type == "closing_call" and assignee_role != "closer":
            return False, "Un appel closing doit être attribué à un closer."

        now = iso_utc()
        full_name = lead_full_name(conv)
        titles = {
            "reply": f"Répondre à {full_name}",
            "follow_up": f"Relancer {full_name}",
            "setting_call": f"Documenter l'appel setting de {full_name}",
            "closing_call": f"Documenter l'appel closing de {full_name}",
        }
        trigger_reasons = {
            "reply": "standard_reply_assigned",
            "follow_up": "standard_followup_scheduled",
            "setting_call": "standard_setting_call_scheduled",
            "closing_call": "standard_closing_call_scheduled",
        }

        active_call = _first_active_action_for_lead(
            conn,
            conv["lead_id"],
            action_types=("setting_call", "closing_call"),
        )
        if action_type == "follow_up" and active_call:
            return (
                False,
                "Un appel est déjà planifié. Modifiez l'appel ou créez une réponse urgente, mais ne planifiez pas une relance parallèle.",
            )
        excluded_types = (
            ("setting_call", "closing_call")
            if action_type == "reply" and active_call
            else ()
        )

        _complete_open_actions_for_lead(
            conn,
            conv["lead_id"],
            user_id,
            outcome=f"Action remplacée par {action_type}",
            excluded_types=excluded_types,
        )

        if action_type in {"reply", "setting_call"}:
            next_stage = "appointment_booked" if action_type == "setting_call" else conv.get("sales_stage")
            conn.execute(
                """
                UPDATE leads
                SET setter_user_id = ?,
                    sales_stage = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (assigned_to_user_id, next_stage, now, conv["lead_id"]),
            )
        elif action_type == "closing_call":
            conn.execute(
                """
                UPDATE leads
                SET closer_user_id = ?,
                    sales_stage = 'closing',
                    lead_status = 'eligible',
                    updated_at = ?
                WHERE id = ?
                """,
                (assigned_to_user_id, now, conv["lead_id"]),
            )

        action_id = _insert_next_action(
            conn,
            lead_id=conv["lead_id"],
            conversation_id=conversation_id,
            action_type=action_type,
            title=titles[action_type],
            assigned_to_user_id=assigned_to_user_id,
            created_by_user_id=user_id,
            urgency="normal",
            due_at=due_at,
            description=note,
            trigger_reason=trigger_reasons[action_type],
            call_cycle_id=str(uuid4()) if action_type in {"setting_call", "closing_call"} else None,
            call_attempt_index=1 if action_type in {"setting_call", "closing_call"} else None,
        )
        _insert_internal_note_message(
            conn,
            conv["lead_id"],
            conversation_id,
            user_id,
            f"Action programmée ({action_type}) pour {assignee['full_name']} : {note}",
            now,
        )
        insert_event(
            conn,
            conv["lead_id"],
            "standard_next_action_assigned",
            user_id=user_id,
            new={
                "task_id": action_id,
                "type": action_type,
                "assigned_to_user_id": assigned_to_user_id,
                "due_at": due_at,
                "note": note,
            },
        )
    return True, "Action programmée."


def reschedule_call_action(
    task_id: int,
    user_id: int,
    due_at: str,
    note: str,
) -> tuple[bool, str]:
    note = note.strip()
    if not note:
        return False, "Ajoutez une note pour expliquer le déplacement du RDV."
    now = iso_utc()
    with connect() as conn:
        task = row_to_dict(
            conn.execute(
                """
                SELECT t.*, l.first_name, l.last_name
                FROM tasks t
                JOIN leads l ON l.id = t.lead_id
                WHERE t.id = ?
                  AND t.type IN ('setting_call', 'closing_call')
                  AND t.status IN ('open', 'planned', 'in_progress')
                """,
                (task_id,),
            ).fetchone()
        )
        if not task:
            return False, "Appel planifié introuvable."
        previous_due_at = task.get("due_at")
        conn.execute(
            """
            UPDATE tasks
            SET due_at = ?, status = 'planned', updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                due_at,
                now,
                json.dumps(
                    {
                        "rescheduled_from": previous_due_at,
                        "rescheduled_note": note,
                    },
                    ensure_ascii=False,
                ),
                task_id,
            ),
        )
        if task.get("conversation_id"):
            _insert_internal_note_message(
                conn,
                task["lead_id"],
                task["conversation_id"],
                user_id,
                f"RDV déplacé au {due_at} : {note}",
                now,
            )
        insert_event(
            conn,
            task["lead_id"],
            "call_rescheduled",
            user_id=user_id,
            previous={"task_id": task_id, "due_at": previous_due_at},
            new={"task_id": task_id, "due_at": due_at, "note": note},
            metadata={"conversation_id": task.get("conversation_id")},
        )
    return True, "RDV déplacé."


def cancel_call_action_without_replacement(
    task_id: int,
    user_id: int,
    note: str,
) -> tuple[bool, str]:
    note = note.strip()
    if not note:
        return False, "Ajoutez une note pour expliquer l'annulation du RDV."
    now = iso_utc()
    with connect() as conn:
        task = row_to_dict(
            conn.execute(
                """
                SELECT t.*, l.first_name, l.last_name
                FROM tasks t
                JOIN leads l ON l.id = t.lead_id
                WHERE t.id = ?
                  AND t.type IN ('setting_call', 'closing_call')
                  AND t.status IN ('open', 'planned', 'in_progress')
                """,
                (task_id,),
            ).fetchone()
        )
        if not task:
            return False, "Appel planifié introuvable."
        conn.execute(
            """
            UPDATE tasks
            SET status = 'cancelled', cancelled_reason = 'appointment_cancelled_without_replacement',
                outcome = 'cancelled_without_replacement', completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, task_id),
        )
        sequence_code = (
            "post_setting_undecided"
            if task["type"] == "setting_call"
            else "post_closing_undecided"
        )
        first_step = _get_sequence_step(conn, sequence_code, 1)
        next_action_id = None
        if first_step and task.get("conversation_id"):
            next_action_id = _insert_next_action(
                conn,
                lead_id=task["lead_id"],
                conversation_id=task["conversation_id"],
                action_type="follow_up",
                title=f"Relancer {lead_full_name(task)}",
                assigned_to_user_id=setter2_user_id(conn) or task.get("assigned_to_user_id") or user_id,
                created_by_user_id=user_id,
                urgency="normal",
                due_at=_due_for_sequence_step(now, first_step),
                description=note,
                trigger_reason="appointment_cancelled_without_replacement",
                sequence_code=sequence_code,
                sequence_step_index=1,
                previous_action_id=task_id,
                metadata=_sequence_anchor_metadata(now, "RDV annulé sans remplacement"),
            )
        if task.get("conversation_id"):
            _insert_internal_note_message(
                conn,
                task["lead_id"],
                task["conversation_id"],
                user_id,
                f"RDV annulé sans nouveau RDV : {note}",
                now,
            )
        insert_event(
            conn,
            task["lead_id"],
            "call_cancelled_without_replacement",
            user_id=user_id,
            previous={"task_id": task_id, "type": task["type"]},
            new={"sequence_code": sequence_code, "next_action_id": next_action_id},
            metadata={"conversation_id": task.get("conversation_id"), "note": note},
        )
    return True, "RDV annulé. Le flux indécis correspondant a été lancé."


def handoff_to_closer(
    conversation_id: int,
    user_id: int,
    closer_user_id: int,
    appointment_note: str = "",
    notes: str = "",
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if conv.get("status") != "open":
        return False, "Conversation terminée : réactivez-la avant de passer au closer."

    with connect() as conn:
        closer = row_to_dict(
            conn.execute(
                "SELECT id, full_name, role FROM users WHERE id = ? AND active = 1",
                (closer_user_id,),
            ).fetchone()
        )
        if not closer or closer["role"] != "closer":
            return False, "Closer invalide."

        full_name = lead_full_name(conv)
        description_parts = []
        if appointment_note.strip():
            description_parts.append(f"RDV / contexte : {appointment_note.strip()}")
        if notes.strip():
            description_parts.append(f"Remarques setter : {notes.strip()}")
        description = "\n".join(description_parts) or None
        now = iso_utc()

        _complete_open_actions_for_lead(
            conn,
            conv["lead_id"],
            user_id,
            outcome="Passé au closer",
        )
        conn.execute(
            """
            UPDATE leads
            SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'eligible', updated_at = ?
            WHERE id = ?
            """,
            (closer_user_id, now, conv["lead_id"]),
        )
        conn.execute(
            "UPDATE conversations SET status = 'open', updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        action_id = _insert_next_action(
            conn,
            lead_id=conv["lead_id"],
            conversation_id=conversation_id,
            action_type="closing_call",
            title=f"Documenter l'appel closing de {full_name}",
            assigned_to_user_id=closer_user_id,
            created_by_user_id=user_id,
            urgency="high",
            due_at=now,
            description=description,
            trigger_reason="handoff_to_closer",
        )
        insert_event(
            conn,
            conv["lead_id"],
            "lead_handed_off_to_closer",
            user_id=user_id,
            previous={
                "sales_stage": conv["sales_stage"],
                "lead_status": conv["lead_status"],
                "closer_user_id": conv.get("closer_user_id"),
            },
            new={
                "sales_stage": "closing",
                "lead_status": "eligible",
                "closer_user_id": closer_user_id,
                "task_id": action_id,
                "appointment_note": appointment_note,
                "notes": notes,
            },
        )
    return True, f"Appel closing créé pour {closer['full_name']}."


def set_conversation_status(
    conversation_id: int,
    user_id: int,
    status: str,
    resolution_reason: str | None = None,
    resolution_note: str | None = None,
    reopen_action_type: str | None = None,
    reopen_assigned_to_user_id: int | None = None,
    reopen_due_at: str | None = None,
    reopen_reason: str | None = None,
) -> tuple[bool, str]:
    if status not in {"open", "resolved"}:
        return False, "Statut de conversation invalide."
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    previous_status = conv["status"]
    if previous_status == status:
        return True, "La conversation a déjà ce statut."

    valid_resolution_reasons = {item["value"] for item in RESOLUTION_REASONS}
    if status == "resolved":
        if not resolution_reason or resolution_reason not in valid_resolution_reasons:
            return False, "Choisissez un motif de résolution."
        if not (resolution_note or "").strip():
            return False, "Une note est obligatoire pour clore la conversation."
    if status == "open" and previous_status == "resolved" and not reopen_action_type:
        return False, "Choisissez une prochaine action pour rouvrir la conversation."
    if status == "open" and previous_status == "resolved" and not (reopen_reason or "").strip():
        return False, "Une note est obligatoire pour réactiver la conversation."

    now = iso_utc()
    created_action_id = None
    with connect() as conn:
        if status == "resolved":
            conn.execute(
                """
                UPDATE conversations
                SET status = 'resolved',
                    resolution_reason = ?,
                    resolution_note = ?,
                    resolved_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    resolution_reason,
                    (resolution_note or "").strip() or None,
                    now,
                    now,
                    conversation_id,
                ),
            )
            if resolution_reason == "do_not_contact":
                conn.execute(
                    """
                    UPDATE leads
                    SET contact_status = 'do_not_contact', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, conv["lead_id"]),
                )
            elif resolution_reason in {"not_relevant", "signed"}:
                conn.execute(
                    """
                    UPDATE leads
                    SET lead_status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (resolution_reason, now, conv["lead_id"]),
                )
            _complete_open_actions_for_lead(
                conn,
                conv["lead_id"],
                user_id,
                outcome=f"Conversation résolue : {resolution_reason}",
            )
            _insert_internal_note_message(
                conn,
                conv["lead_id"],
                conversation_id,
                user_id,
                f"Clôture de conversation ({resolution_reason}) : {(resolution_note or '').strip()}",
                now,
            )
        else:
            conn.execute(
                """
                UPDATE conversations
                SET status = 'open',
                    resolution_reason = NULL,
                    resolution_note = NULL,
                    reopened_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, conversation_id),
            )
            full_name = lead_full_name(conv)
            action_type = reopen_action_type or "reply"
            assigned_to_user_id = reopen_assigned_to_user_id or user_id
            action_labels = {
                "reply": "Répondre à",
                "follow_up": "Relancer",
                "setting_call": "Documenter l'appel setting de",
                "closing_call": "Documenter l'appel closing de",
            }
            prefix = action_labels.get(action_type, "Traiter")
            created_action_id = _insert_next_action(
                conn,
                lead_id=conv["lead_id"],
                conversation_id=conversation_id,
                action_type=action_type,
                title=f"{prefix} {full_name}",
                assigned_to_user_id=assigned_to_user_id,
                created_by_user_id=user_id,
                urgency="normal" if reopen_due_at else "high",
                due_at=reopen_due_at or now,
                description=(reopen_reason or "").strip() or "Conversation rouverte.",
                trigger_reason="conversation_reopened",
                metadata={"reopen_reason": reopen_reason},
            )
            _insert_internal_note_message(
                conn,
                conv["lead_id"],
                conversation_id,
                user_id,
                f"Réactivation de conversation : {(reopen_reason or '').strip()}",
                now,
            )
        insert_event(
            conn,
            conv["lead_id"],
            "conversation_status_changed",
            user_id=user_id,
            previous={"status": previous_status},
            new={
                "status": status,
                "resolution_reason": resolution_reason,
                "reopen_action_type": reopen_action_type,
            },
            metadata={
                "conversation_id": conversation_id,
                "resolution_note": resolution_note,
                "reopen_reason": reopen_reason,
                "created_action_id": created_action_id,
            },
        )

    label = "rouverte" if status == "open" else "terminée"
    return True, f"Conversation {label}."


def _insert_next_action(
    conn: Any,
    lead_id: int,
    conversation_id: int | None,
    action_type: str,
    title: str,
    assigned_to_user_id: int,
    created_by_user_id: int | None,
    urgency: str,
    due_at: str,
    description: str | None = None,
    trigger_reason: str | None = None,
    sequence_code: str | None = None,
    sequence_step_index: int | None = None,
    previous_action_id: int | None = None,
    status: str = "open",
    blocked_reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    call_cycle_id: str | None = None,
    call_attempt_index: int | None = None,
) -> int:
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(f"Unsupported action type: {action_type}")
    if status not in VALID_TASK_STATUSES:
        raise ValueError(f"Unsupported task status: {status}")
    if sequence_code and sequence_code not in VALID_SEQUENCE_CODES:
        raise ValueError(f"Unsupported sequence code: {sequence_code}")
    metadata_payload = dict(metadata or {})
    if sequence_code and sequence_step_index and "sequence_anchor_at" not in metadata_payload and previous_action_id:
        previous = row_to_dict(
            conn.execute(
                "SELECT metadata_json FROM tasks WHERE id = ?",
                (previous_action_id,),
            ).fetchone()
        )
        if previous:
            try:
                previous_metadata = json.loads(previous.get("metadata_json") or "{}")
            except json.JSONDecodeError:
                previous_metadata = {}
            if previous_metadata.get("sequence_anchor_at"):
                metadata_payload["sequence_anchor_at"] = previous_metadata["sequence_anchor_at"]
            if previous_metadata.get("sequence_anchor_label"):
                metadata_payload["sequence_anchor_label"] = previous_metadata["sequence_anchor_label"]
    cursor = conn.execute(
        """
        INSERT INTO tasks (
            lead_id, conversation_id, type, title, description, assigned_to_user_id,
            created_by_user_id, due_at, urgency, status, trigger_reason, sequence_code,
            sequence_step_index, previous_action_id, blocked_reason, call_cycle_id,
            call_attempt_index, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            conversation_id,
            action_type,
            title,
            description,
            assigned_to_user_id,
            created_by_user_id,
            due_at,
            urgency,
            status,
            trigger_reason,
            sequence_code,
            sequence_step_index,
            previous_action_id,
            blocked_reason,
            call_cycle_id,
            call_attempt_index,
            json.dumps(metadata_payload, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid)


def _complete_open_actions_for_lead(
    conn: Any,
    lead_id: int,
    user_id: int | None,
    outcome: str,
    excluded_types: tuple[str, ...] = (),
    included_types: tuple[str, ...] | None = None,
    excluded_sequence_codes: tuple[str, ...] = (),
) -> None:
    params: list[Any] = [lead_id]
    exclusion = ""
    inclusion = ""
    sequence_exclusion = ""
    if included_types:
        placeholders = ", ".join("?" for _ in included_types)
        inclusion = f" AND type IN ({placeholders})"
        params.extend(included_types)
    if excluded_types:
        placeholders = ", ".join("?" for _ in excluded_types)
        exclusion = f" AND type NOT IN ({placeholders})"
        params.extend(excluded_types)
    if excluded_sequence_codes:
        placeholders = ", ".join("?" for _ in excluded_sequence_codes)
        sequence_exclusion = (
            f" AND (sequence_code IS NULL OR sequence_code NOT IN ({placeholders}))"
        )
        params.extend(excluded_sequence_codes)

    rows = conn.execute(
        f"""
        SELECT id FROM tasks
        WHERE lead_id = ? AND status IN ('open', 'in_progress', 'planned', 'blocked')
        {inclusion}{exclusion}{sequence_exclusion}
        """,
        params,
    ).fetchall()
    task_ids = [row["id"] for row in rows]
    if not task_ids:
        return

    now = iso_utc()
    placeholders = ", ".join("?" for _ in task_ids)
    conn.execute(
        f"""
        UPDATE tasks
        SET status = 'done', outcome = ?, completed_at = ?, updated_at = ?
        WHERE id IN ({placeholders})
        """,
        [outcome, now, now, *task_ids],
    )
    insert_event(
        conn,
        lead_id,
        "next_actions_completed",
        user_id=user_id,
        previous={"task_ids": task_ids},
        new={"status": "done", "outcome": outcome},
    )


def _first_active_action_for_lead(
    conn: Any,
    lead_id: int,
    action_types: tuple[str, ...] | None = None,
    include_blocked: bool = True,
    sequence_codes: tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    statuses = "('open', 'in_progress', 'planned', 'blocked')" if include_blocked else "('open', 'in_progress', 'planned')"
    filters = ["lead_id = ?", f"status IN {statuses}"]
    params: list[Any] = [lead_id]
    if action_types:
        placeholders = ", ".join("?" for _ in action_types)
        filters.append(f"type IN ({placeholders})")
        params.extend(action_types)
    if sequence_codes:
        placeholders = ", ".join("?" for _ in sequence_codes)
        filters.append(f"sequence_code IN ({placeholders})")
        params.extend(sequence_codes)
    row = conn.execute(
        f"""
        SELECT *
        FROM tasks
        WHERE {' AND '.join(filters)}
        ORDER BY
            CASE type
                WHEN 'reply' THEN 0
                WHEN 'follow_up' THEN 1
                WHEN 'setting_call' THEN 2
                WHEN 'closing_call' THEN 3
                ELSE 4
            END,
            datetime(coalesce(due_at, created_at)) ASC,
            id ASC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row_to_dict(row)


def _has_blocked_followup(conn: Any, lead_id: int) -> bool:
    row = conn.execute(
        """
        SELECT id FROM tasks
        WHERE lead_id = ?
          AND type = 'follow_up'
          AND status = 'blocked'
        LIMIT 1
        """,
        (lead_id,),
    ).fetchone()
    return bool(row)


def _blocked_followup_allows_template(conn: Any, lead_id: int, template_id: int) -> bool:
    action = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("follow_up",),
        include_blocked=True,
    )
    if not action or action.get("status") != "blocked":
        return True
    linked_request = conn.execute(
        """
        SELECT id
        FROM template_requests
        WHERE task_id = ?
          AND status = 'approved'
          AND template_id = ?
        LIMIT 1
        """,
        (action["id"], template_id),
    ).fetchone()
    if linked_request:
        return True
    recommended = _recommended_template_mapping_for_action(conn, action["id"])
    return bool(recommended and int(recommended["template_id"]) == int(template_id))


def _due_after(base_iso: str, delay: str) -> str:
    base = parse_dt(base_iso) or utc_now()
    normalized = delay.strip().lower()
    if normalized.startswith("+72h"):
        return iso_utc(base + timedelta(hours=72))
    if normalized.startswith("+24h"):
        return iso_utc(base + timedelta(hours=24))
    if normalized.startswith("+2h"):
        return iso_utc(base + timedelta(hours=2))
    if normalized.startswith("+7j"):
        return iso_utc(base + timedelta(days=7))
    if normalized.startswith("+30j"):
        return iso_utc(base + timedelta(days=30))
    return iso_utc(base)


def _format_sequence_delay(direction: str, amount: int, unit: str) -> str:
    unit_label = "j" if unit == "days" else "h"
    prefix = "-" if direction == "before" else "+"
    return f"T{prefix}{amount}{unit_label}"


def _sequence_offset_delta(amount: int, unit: str) -> timedelta:
    return timedelta(days=amount) if unit == "days" else timedelta(hours=amount)


def _business_window(role_key: str) -> tuple[int, int]:
    return BUSINESS_HOURS_BY_ROLE.get(role_key) or BUSINESS_HOURS_BY_ROLE["company"]


def _normalize_business_start(local_dt: datetime, role_key: str) -> datetime:
    start_hour, end_hour = _business_window(role_key)
    current = local_dt
    while True:
        if current.weekday() >= 5:
            days_until_monday = 7 - current.weekday()
            current = (current + timedelta(days=days_until_monday)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            continue
        day_start = current.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        day_end = current.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        if current < day_start:
            return day_start
        if current >= day_end:
            current = (current + timedelta(days=1)).replace(
                hour=start_hour, minute=0, second=0, microsecond=0
            )
            continue
        return current


def _add_business_hours(anchor_iso: str, hours: int, role_key: str) -> str:
    anchor = parse_dt(anchor_iso) or utc_now()
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    current = _normalize_business_start(anchor.astimezone(ZURICH_TZ), role_key)
    remaining = timedelta(hours=max(0, int(hours)))
    while remaining > timedelta(0):
        _start_hour, end_hour = _business_window(role_key)
        day_end = current.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        available = day_end - current
        if remaining <= available:
            return iso_utc((current + remaining).astimezone(timezone.utc))
        remaining -= max(available, timedelta(0))
        current = _normalize_business_start(
            (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            role_key,
        )
    return iso_utc(current.astimezone(timezone.utc))


def _due_for_sequence_step(anchor_iso: str, step: dict[str, Any]) -> str:
    anchor = parse_dt(anchor_iso) or utc_now()
    amount = int(step.get("offset_amount") or 0)
    unit = step.get("offset_unit") or "hours"
    delta = _sequence_offset_delta(amount, unit)
    if step.get("offset_direction") == "before":
        return iso_utc(anchor - delta)
    return iso_utc(anchor + delta)


def _due_for_call_retry_step(anchor_iso: str, step: dict[str, Any], role_key: str) -> str:
    if step.get("step_index") in {1, 2} and step.get("offset_direction") != "before":
        amount = int(step.get("offset_amount") or 0)
        if (step.get("offset_unit") or "hours") == "days":
            amount *= 24
        return _add_business_hours(anchor_iso, amount, role_key)
    return _due_for_sequence_step(anchor_iso, step)


def _get_sequence_step(
    conn: Any,
    sequence_code: str,
    step_index: int,
) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM sequence_steps
            WHERE sequence_code = ? AND step_index = ? AND active = 1
            """,
            (sequence_code, step_index),
        ).fetchone()
    )


def _sequence_anchor_metadata(anchor_at: str, label: str | None = None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"sequence_anchor_at": anchor_at}
    if label:
        metadata["sequence_anchor_label"] = label
    return metadata


def _task_metadata(action: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(action.get("metadata_json") or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return metadata if isinstance(metadata, dict) else {}


def _sequence_anchor_from_action(action: dict[str, Any], fallback_iso: str) -> str:
    metadata = _task_metadata(action)
    return metadata.get("sequence_anchor_at") or fallback_iso


def _next_sequence_step(
    conn: Any,
    sequence_code: str | None,
    current_step_index: int | None,
) -> dict[str, Any] | None:
    if not sequence_code:
        return None
    return row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM sequence_steps
            WHERE sequence_code = ?
              AND step_index > ?
              AND active = 1
            ORDER BY step_index
            LIMIT 1
            """,
            (sequence_code, current_step_index or 0),
        ).fetchone()
    )


def _close_outbound_action_and_chain(
    conn: Any,
    conv: dict[str, Any],
    user_id: int,
    message_id: int,
    sent_at: str,
    action_outcome: str | None = None,
    next_due_at: str | None = None,
    assigned_to_user_id: int | None = None,
    note: str = "",
) -> None:
    action = _first_active_action_for_lead(
        conn,
        conv["lead_id"],
        action_types=("reply", "follow_up"),
        include_blocked=True,
    )
    if not action:
        return

    note = note.strip()
    persisted_outcome = action_outcome or "Message WhatsApp envoyé"
    conn.execute(
        """
        UPDATE tasks
        SET status = 'done',
            outcome = ?,
            proof_message_id = ?,
            completed_at = ?,
            updated_at = ?,
            metadata_json = ?
        WHERE id = ?
        """,
        (
            persisted_outcome,
            message_id,
            sent_at,
            sent_at,
            json.dumps({"completion_note": note}, ensure_ascii=False),
            action["id"],
        ),
    )
    insert_event(
        conn,
        conv["lead_id"],
        "action_completed_by_outbound_message",
        user_id=user_id,
        previous={"task_id": action["id"], "type": action["type"]},
        new={
            "status": "done",
            "outcome": persisted_outcome,
            "proof_message_id": message_id,
            "note": note,
        },
    )
    if note:
        _insert_internal_note_message(
            conn,
            conv["lead_id"],
            conv["id"],
            user_id,
            f"Note après envoi WhatsApp : {note}",
            sent_at,
        )

    full_name = lead_full_name(conv)
    if action["type"] == "reply":
        if action_outcome == "setting_booked":
            assignee_id = (
                assigned_to_user_id
                if _is_setter1_user(conn, assigned_to_user_id)
                else setter1_user_id(conn)
            ) or action.get("assigned_to_user_id") or user_id
            _complete_open_actions_for_lead(
                conn,
                conv["lead_id"],
                user_id,
                outcome="Appel setting remplacé",
                included_types=("setting_call",),
            )
            next_action_id = _insert_next_action(
                conn,
                lead_id=conv["lead_id"],
                conversation_id=conv["id"],
                action_type="setting_call",
                title=f"Documenter l'appel setting de {full_name}",
                assigned_to_user_id=assignee_id,
                created_by_user_id=user_id,
                urgency="high",
                due_at=next_due_at or sent_at,
                description=note or None,
                trigger_reason="setting_appointment_booked",
                previous_action_id=action["id"],
                call_cycle_id=str(uuid4()),
                call_attempt_index=1,
            )
            conn.execute("UPDATE tasks SET next_action_id = ? WHERE id = ?", (next_action_id, action["id"]))
            return

        if action_outcome == "closing_booked":
            closer_id = assigned_to_user_id or default_closer_user_id(conn)
            if not closer_id:
                return
            _complete_open_actions_for_lead(
                conn,
                conv["lead_id"],
                user_id,
                outcome="Appel closing remplacé",
                included_types=("closing_call",),
            )
            conn.execute(
                """
                UPDATE leads
                SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'eligible', updated_at = ?
                WHERE id = ?
                """,
                (closer_id, sent_at, conv["lead_id"]),
            )
            next_action_id = _insert_next_action(
                conn,
                lead_id=conv["lead_id"],
                conversation_id=conv["id"],
                action_type="closing_call",
                title=f"Documenter l'appel closing de {full_name}",
                assigned_to_user_id=closer_id,
                created_by_user_id=user_id,
                urgency="high",
                due_at=next_due_at or sent_at,
                description=note or None,
                trigger_reason="closing_appointment_booked_from_reply",
                previous_action_id=action["id"],
                call_cycle_id=str(uuid4()),
                call_attempt_index=1,
            )
            conn.execute("UPDATE tasks SET next_action_id = ? WHERE id = ?", (next_action_id, action["id"]))
            return

        if action_outcome in {"not_relevant", "do_not_contact"}:
            if action_outcome == "do_not_contact":
                conn.execute(
                    "UPDATE leads SET contact_status = 'do_not_contact', updated_at = ? WHERE id = ?",
                    (sent_at, conv["lead_id"]),
                )
            else:
                conn.execute(
                    "UPDATE leads SET lead_status = 'not_relevant', updated_at = ? WHERE id = ?",
                    (sent_at, conv["lead_id"]),
                )
            _complete_open_actions_for_lead(
                conn,
                conv["lead_id"],
                user_id,
                outcome=f"Statut terminal : {action_outcome}",
            )
            conn.execute(
                """
                UPDATE conversations
                SET status = 'resolved',
                    resolution_reason = ?,
                    resolution_note = ?,
                    resolved_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (action_outcome, note or None, sent_at, sent_at, conv["id"]),
            )
            insert_event(
                conn,
                conv["lead_id"],
                "conversation_resolved_by_reply_outcome",
                user_id=user_id,
                metadata={"outcome": action_outcome, "message_id": message_id},
            )
            return

        active_call = _first_active_action_for_lead(
            conn,
            conv["lead_id"],
            action_types=("setting_call", "closing_call"),
        )
        if active_call:
            insert_event(
                conn,
                conv["lead_id"],
                "reply_completed_planned_call_kept",
                user_id=user_id,
                previous={"reply_task_id": action["id"]},
                new={"kept_call_task_id": active_call["id"], "kept_call_type": active_call["type"]},
                metadata={"conversation_id": conv["id"]},
            )
            return

        first_step = _get_sequence_step(conn, "setter_no_next_step", 1)
        if not first_step:
            return
        assignee_id = setter2_user_id(conn) or user_id
        next_action_id = _insert_next_action(
            conn,
            lead_id=conv["lead_id"],
            conversation_id=conv["id"],
            action_type="follow_up",
            title=f"Relancer {full_name}",
            assigned_to_user_id=assignee_id,
            created_by_user_id=user_id,
            urgency="normal",
            due_at=_due_for_sequence_step(sent_at, first_step),
            trigger_reason="reply_sent_no_setting_booked",
            sequence_code="setter_no_next_step",
            sequence_step_index=1,
            previous_action_id=action["id"],
            metadata=_sequence_anchor_metadata(sent_at, "Dernier message setter sans rendez-vous"),
        )
        conn.execute("UPDATE tasks SET next_action_id = ? WHERE id = ?", (next_action_id, action["id"]))
        return

    if action["type"] == "follow_up":
        next_step = _next_sequence_step(
            conn,
            action.get("sequence_code"),
            action.get("sequence_step_index"),
        )
        if not next_step:
            conn.execute(
                """
                UPDATE conversations
                SET status = 'resolved',
                    resolution_reason = 'sequence_completed_no_reply',
                    resolved_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (sent_at, sent_at, conv["id"]),
            )
            insert_event(
                conn,
                conv["lead_id"],
                "conversation_resolved_by_sequence_completion",
                user_id=user_id,
                metadata={"completed_action_id": action["id"]},
            )
            return

        sequence_anchor_at = _sequence_anchor_from_action(action, sent_at)
        assignee_id = setter2_user_id(conn) or user_id
        next_action_id = _insert_next_action(
            conn,
            lead_id=conv["lead_id"],
            conversation_id=conv["id"],
            action_type="follow_up",
            title=f"Relancer {full_name}",
            assigned_to_user_id=assignee_id,
            created_by_user_id=user_id,
            urgency="normal",
            due_at=_due_for_sequence_step(sequence_anchor_at, next_step),
            trigger_reason="follow_up_sequence_continues",
            sequence_code=next_step["sequence_code"],
            sequence_step_index=next_step["step_index"],
            previous_action_id=action["id"],
            metadata=_sequence_anchor_metadata(sequence_anchor_at),
        )
        conn.execute("UPDATE tasks SET next_action_id = ? WHERE id = ?", (next_action_id, action["id"]))


def _default_active_user_id(conn: Any, role: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM users WHERE role = ? AND active = 1 ORDER BY id LIMIT 1",
        (role,),
    ).fetchone()
    return int(row["id"]) if row else None


def _upsert_reply_action_for_inbound(
    conn: Any,
    lead_id: int,
    conversation_id: int,
    setter_user_id: int | None,
) -> None:
    setter_id = setter_user_id or _default_active_user_id(conn, "setter")
    if not setter_id:
        return

    now = iso_utc()
    lead = row_to_dict(
        conn.execute(
            "SELECT first_name, last_name, setter_user_id, contact_status FROM leads WHERE id = ?",
            (lead_id,),
        ).fetchone()
    )
    if not lead:
        return

    conn.execute(
        """
        UPDATE leads
        SET setter_user_id = coalesce(setter_user_id, ?), updated_at = ?
        WHERE id = ?
        """,
        (setter_id, now, lead_id),
    )
    _complete_open_actions_for_lead(
        conn,
        lead_id,
        user_id=None,
        outcome="Nouveau message reçu",
        included_types=("follow_up",),
    )

    if lead.get("contact_status") in STOP_CONTACT_STATUSES:
        title = f"Revoir le statut de contact de {lead_full_name(lead)}"
        existing_review = conn.execute(
            """
            SELECT id FROM tasks
            WHERE lead_id = ? AND conversation_id = ? AND type = 'contact_review'
              AND status IN ('open', 'in_progress', 'planned', 'blocked')
            ORDER BY id DESC
            LIMIT 1
            """,
            (lead_id, conversation_id),
        ).fetchone()
        if existing_review:
            conn.execute(
                """
                UPDATE tasks
                SET title = ?, assigned_to_user_id = ?, due_at = ?,
                    urgency = 'urgent', updated_at = ?
                WHERE id = ?
                """,
                (title, setter_id, now, now, existing_review["id"]),
            )
            return

        action_id = _insert_next_action(
            conn,
            lead_id=lead_id,
            conversation_id=conversation_id,
            action_type="contact_review",
            title=title,
            assigned_to_user_id=setter_id,
            created_by_user_id=None,
            urgency="urgent",
            due_at=now,
            description=(
                "Le prospect est marqué Ne plus contacter mais vient d'écrire. "
                "Lire le message et décider s'il faut maintenir ou lever le blocage."
            ),
            trigger_reason="do_not_contact_prospect_replied",
        )
        insert_event(
            conn,
            lead_id,
            "contact_review_created_from_inbound",
            new={
                "task_id": action_id,
                "assigned_to_user_id": setter_id,
                "conversation_id": conversation_id,
            },
        )
        return

    title = f"Répondre à {lead_full_name(lead)}"
    existing = conn.execute(
        """
        SELECT id FROM tasks
        WHERE lead_id = ? AND conversation_id = ? AND type = 'reply'
          AND status IN ('open', 'in_progress', 'planned', 'blocked')
        ORDER BY id DESC
        LIMIT 1
        """,
        (lead_id, conversation_id),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE tasks
            SET title = ?, assigned_to_user_id = ?, due_at = ?, urgency = 'urgent', updated_at = ?
            WHERE id = ?
            """,
            (title, setter_id, now, now, existing["id"]),
        )
    else:
        action_id = _insert_next_action(
            conn,
            lead_id=lead_id,
            conversation_id=conversation_id,
            action_type="reply",
            title=title,
            assigned_to_user_id=setter_id,
            created_by_user_id=None,
            urgency="urgent",
            due_at=now,
        )
        insert_event(
            conn,
            lead_id,
            "reply_action_created_from_inbound",
            new={
                "task_id": action_id,
                "assigned_to_user_id": setter_id,
                "conversation_id": conversation_id,
            },
        )


def _phone_match_candidates(conn: Any, from_phone: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            l.id AS lead_id,
            (
                SELECT c2.id FROM conversations c2
                WHERE c2.lead_id = l.id
                ORDER BY c2.id DESC
                LIMIT 1
            ) AS conversation_id,
            l.schooldrive_lead_id,
            l.first_name,
            l.last_name,
            l.phone_e164,
            l.phone_raw,
            l.course_category_short_title,
            l.course_title,
            l.source,
            l.identity_status,
            l.setter_user_id
        FROM leads l
        WHERE l.phone_e164 = ?
           OR l.phone_raw = ?
           OR EXISTS (
                SELECT 1 FROM conversations c
                WHERE c.lead_id = l.id AND c.recipient_phone_e164 = ?
           )
        ORDER BY
            CASE WHEN l.identity_status IN ('needs_identification', 'ambiguous_identity') THEN 0 ELSE 1 END,
            l.id DESC
        """,
        (from_phone, from_phone, from_phone),
    ).fetchall()
    return rows_to_dicts(rows)


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    name = lead_full_name(candidate)
    return {
        "lead_id": candidate.get("lead_id"),
        "schooldrive_lead_id": candidate.get("schooldrive_lead_id"),
        "name": name,
        "phone_e164": candidate.get("phone_e164") or candidate.get("phone_raw"),
        "course": candidate.get("course_title")
        or candidate.get("course_category_short_title")
        or None,
        "identity_status": candidate.get("identity_status") or IDENTITY_STATUS_VERIFIED,
    }


def _insert_schooldrive_ignored_event(
    conn: Any,
    *,
    event_id: str,
    environment: str,
    schooldrive_id: str,
    lead_id: int | None,
    occurred_at: str,
    aggregated_updated_at: str,
    ignored_reason: str,
    payload_json: str,
    received_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO schooldrive_webhook_events (
            event_id, environment, schooldrive_id, lead_id, occurred_at,
            aggregated_updated_at, status, ignored_reason, payload_json, received_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'ignored', ?, ?, ?)
        """,
        (
            event_id,
            environment,
            schooldrive_id,
            lead_id,
            occurred_at,
            aggregated_updated_at,
            ignored_reason,
            payload_json,
            received_at,
        ),
    )


def _new_schooldrive_snapshot_ignore_reason(
    data: dict[str, Any],
    settings: Any,
) -> str | None:
    if data.get("is_archived"):
        return "archived_without_existing_record"
    if (
        _schooldrive_signed_signal(data)[0]
        or _schooldrive_do_not_contact_signal(data)[0]
        or _schooldrive_course_full_signal(data)[0]
    ):
        return None

    person = data.get("person") or {}
    has_identity = any(
        str(person.get(key) or "").strip()
        for key in ("first_name", "last_name", "phone", "email")
    )
    if not has_identity:
        return "missing_identity"

    autoresponders = data.get("whatsapp_autoresponders") or []
    if not autoresponders:
        return "waiting_for_first_autoresponder"

    sent_at_values: list[datetime] = []
    has_pending = False
    for item in autoresponders:
        status = str(item.get("status") or "").strip()
        if status == "sent":
            sent_at = parse_dt(str(item.get("sent_at") or "")) if item.get("sent_at") else None
            if sent_at:
                sent_at_values.append(sent_at)
        if status in SCHOOLDRIVE_PENDING_AUTORESPONDER_STATUSES:
            has_pending = True

    if sent_at_values:
        min_sent_at = _schooldrive_min_sent_at(settings)
        if min_sent_at and max(sent_at_values) < min_sent_at:
            return "sent_autoresponder_before_ingest_window"
        return None

    if has_pending:
        return None

    return "no_sent_or_pending_autoresponder"


def _schooldrive_min_sent_at(settings: Any) -> datetime | None:
    raw_value = str(getattr(settings, "schooldrive_ingest_min_sent_at", "") or "").strip()
    if not raw_value:
        return None
    parsed = parse_dt(raw_value)
    if not parsed:
        raise ValueError("SALES_COCKPIT_SCHOOLDRIVE_INGEST_MIN_SENT_AT must be ISO 8601.")
    return parsed


def _select_inbound_match(
    conn: Any,
    from_phone: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    candidates = _phone_match_candidates(conn, from_phone)
    review_records = [
        candidate
        for candidate in candidates
        if candidate.get("identity_status") in IDENTITY_REVIEW_STATUSES
    ]
    if review_records:
        return review_records[0], candidates, "existing_identity_review"
    if len(candidates) == 1:
        return candidates[0], candidates, "matched"
    if not candidates:
        return None, candidates, "no_match"
    return None, candidates, "ambiguous"


def _ensure_conversation_for_lead(
    conn: Any,
    lead_id: int,
    from_phone: str,
    now: str,
    conversation_id: int | None = None,
) -> int:
    if conversation_id:
        return int(conversation_id)
    return int(
        conn.execute(
            """
            INSERT INTO conversations (lead_id, recipient_phone_e164, last_inbound_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, from_phone, now, now, now),
        ).lastrowid
    )


def _create_temporary_identity_lead(
    conn: Any,
    from_phone: str,
    setter_user_id: int | None,
    candidates: list[dict[str, Any]],
    match_status: str,
    now: str,
) -> tuple[int, int, str]:
    identity_status = (
        IDENTITY_STATUS_AMBIGUOUS
        if match_status == "ambiguous"
        else IDENTITY_STATUS_NEEDS_IDENTIFICATION
    )
    candidate_payload = (
        json.dumps([_candidate_summary(candidate) for candidate in candidates], ensure_ascii=False)
        if candidates
        else None
    )
    source = (
        "twilio_inbound_ambiguous"
        if identity_status == IDENTITY_STATUS_AMBIGUOUS
        else "twilio_inbound_unmatched"
    )
    cursor = conn.execute(
        """
        INSERT INTO leads (
            first_name, last_name, phone_e164, phone_raw, source,
            acquisition_type, lead_status, contact_status, sales_stage,
            temperature, setter_user_id, identity_status, identity_candidates_json,
            created_at, updated_at
        ) VALUES ('Inconnu(e)', '', ?, ?, ?, 'unknown', 'eligible',
            'contact_allowed', 'new', 'warm', ?, ?, ?, ?, ?)
        """,
        (
            from_phone,
            from_phone,
            source,
            setter_user_id,
            identity_status,
            candidate_payload,
            now,
            now,
        ),
    )
    lead_id = int(cursor.lastrowid)
    conversation_id = int(
        conn.execute(
            """
            INSERT INTO conversations (lead_id, recipient_phone_e164, last_inbound_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, from_phone, now, now, now),
        ).lastrowid
    )
    insert_event(
        conn,
        lead_id,
        "identity_review_required",
        new={
            "identity_status": identity_status,
            "phone_e164": from_phone,
            "candidate_count": len(candidates),
        },
        metadata={
            "conversation_id": conversation_id,
            "candidates": [_candidate_summary(candidate) for candidate in candidates],
        },
    )
    return lead_id, conversation_id, identity_status


def list_messages(conversation_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.*, u.full_name AS sender_name, u.email AS sender_email, wt.name AS template_name
            FROM messages m
            LEFT JOIN users u ON u.id = m.sender_user_id
            LEFT JOIN whatsapp_templates wt ON wt.id = m.template_id
            WHERE m.conversation_id = ?
            ORDER BY datetime(m.created_at), m.id
            """,
            (conversation_id,),
        ).fetchall()
        messages = rows_to_dicts(rows)
        message_ids = [item["id"] for item in messages]
        attachments_by_message: dict[int, list[dict[str, Any]]] = {message_id: [] for message_id in message_ids}
        if message_ids:
            placeholders = ",".join("?" for _ in message_ids)
            attachment_rows = conn.execute(
                f"""
                SELECT *
                FROM attachments
                WHERE message_id IN ({placeholders})
                ORDER BY id
                """,
                message_ids,
            ).fetchall()
            for attachment in rows_to_dicts(attachment_rows):
                attachment["public_url"] = _attachment_public_url(attachment)
                attachments_by_message.setdefault(int(attachment["message_id"]), []).append(attachment)
    for message in messages:
        message["attachments"] = attachments_by_message.get(int(message["id"]), [])
    return messages


def list_templates(search: str = "", approved_only: bool = False) -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if approved_only:
        filters.append("status = 'approved'")
        if (get_settings().twilio_mode or "mock").lower() != "mock":
            filters.append(
                "twilio_content_sid IS NOT NULL AND twilio_content_sid NOT LIKE 'HX_MOCK_%'"
            )
    if search:
        like = f"%{search.lower()}%"
        filters.append("(lower(name) LIKE ? OR lower(body) LIKE ? OR lower(category) LIKE ?)")
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM whatsapp_templates
            {where}
            ORDER BY
                CASE status WHEN 'approved' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                updated_at DESC,
                name
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def get_template(template_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        template = row_to_dict(
            conn.execute("SELECT * FROM whatsapp_templates WHERE id = ?", (template_id,)).fetchone()
        )
        if not template:
            return None
        rows = conn.execute(
            "SELECT * FROM template_placeholders WHERE template_id = ? ORDER BY id",
            (template_id,),
        ).fetchall()
    template["placeholders"] = rows_to_dicts(rows)
    return template


def _is_admin_user(conn: Any, user_id: int) -> bool:
    row = conn.execute(
        "SELECT role FROM users WHERE id = ? AND active = 1",
        (user_id,),
    ).fetchone()
    return bool(row and row["role"] == "admin")


def _require_admin_user(conn: Any, user_id: int) -> tuple[bool, str]:
    if _is_admin_user(conn, user_id):
        return True, ""
    return False, "Seuls les admins peuvent créer ou synchroniser des modèles WhatsApp."


def create_template(
    user_id: int,
    name: str,
    body: str,
    status: str = "draft",
    language: str = "fr",
    category: str = "utility",
    placeholders: dict[str, str] | None = None,
    twilio_content_sid: str | None = None,
    twilio_content_type: str | None = None,
    twilio_payload: dict[str, Any] | None = None,
) -> int:
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            raise PermissionError(message)
        cursor = conn.execute(
            """
            INSERT INTO whatsapp_templates (
                twilio_content_sid, twilio_content_type, twilio_payload_json,
                last_twilio_sync_at, name, language, category, body, status,
                created_by_user_id, submitted_at, approved_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                twilio_content_sid,
                twilio_content_type,
                json.dumps(twilio_payload or {}, ensure_ascii=False) if twilio_payload else None,
                iso_utc() if twilio_payload else None,
                name,
                language,
                category,
                body,
                status,
                user_id,
                iso_utc() if status == "pending" else None,
                iso_utc() if status == "approved" else None,
            ),
        )
        template_id = cursor.lastrowid
        for key, example in (placeholders or {}).items():
            conn.execute(
                """
                INSERT INTO template_placeholders (
                    template_id, placeholder_key, source_field, example_value, required
                ) VALUES (?, ?, ?, ?, 1)
                """,
                (template_id, key, key, example),
            )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json
            ) VALUES (?, 'template_created', 'whatsapp_template', ?, ?)
            """,
            (
                user_id,
                template_id,
                json.dumps(
                    {
                        "name": name,
                        "status": status,
                        "language": language,
                        "category": category,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return int(template_id)


def sync_twilio_templates(user_id: int) -> tuple[bool, str]:
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message

    try:
        remote_templates = list_twilio_templates()
    except TwilioContentError as exc:
        return False, str(exc)

    now = iso_utc()
    created = 0
    updated = 0
    with connect() as conn:
        for remote in remote_templates:
            changed = _upsert_twilio_template(conn, remote, user_id, now)
            if changed == "created":
                created += 1
            elif changed == "updated":
                updated += 1
        unblocked = _auto_approve_linked_template_requests(conn, user_id, now)
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, metadata_json, created_at
            ) VALUES (?, 'twilio_templates_synced', 'whatsapp_template', ?, ?)
            """,
            (
                user_id,
                json.dumps(
                    {
                        "created": created,
                        "updated": updated,
                        "total": len(remote_templates),
                        "unblocked_template_requests": unblocked,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, f"Synchronisation Twilio terminée : {created} créé(s), {updated} mis à jour, {unblocked} demande(s) débloquée(s)."


def create_and_submit_twilio_template(
    user_id: int,
    name: str,
    body: str,
    language: str = "fr",
    category: str = "utility",
    placeholders: dict[str, str] | None = None,
    submit_for_approval: bool = True,
) -> tuple[bool, str, int | None]:
    if get_settings().twilio_content_read_only:
        return False, "Compte Twilio en lecture seule : création et soumission désactivées.", None
    name = name.strip()
    body = body.strip()
    if not name or not body:
        return False, "Ajoutez un nom et un corps de modèle.", None
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message, None
    variables = {
        key: value or _placeholder_example(key)
        for key, value in (placeholders or {}).items()
        if key
    }
    try:
        remote = create_twilio_text_template(
            name=name,
            body=body,
            language=language,
            variables=variables,
        )
        approval_result = None
        if submit_for_approval:
            approval_result = submit_twilio_template_for_whatsapp_approval(
                content_sid=remote.content_sid,
                approval_name=name,
                category=category,
            )
            remote = TwilioContentTemplate(
                content_sid=remote.content_sid,
                name=remote.name,
                language=remote.language,
                category=(approval_result.get("category") or category).lower(),
                body=remote.body,
                status=_map_twilio_local_status(str(approval_result.get("status") or "pending")),
                rejection_reason=approval_result.get("rejection_reason") or None,
                content_type=remote.content_type,
                variables=remote.variables,
                payload={**remote.payload, "approval_submission": approval_result},
            )
    except TwilioContentError as exc:
        return False, str(exc), None

    now = iso_utc()
    with connect() as conn:
        template_id = _upsert_twilio_template(conn, remote, user_id, now, return_id=True)
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'twilio_template_created', 'whatsapp_template', ?, ?, ?)
            """,
            (
                user_id,
                template_id,
                json.dumps(
                    {
                        "name": name,
                        "content_sid": remote.content_sid,
                        "submitted": submit_for_approval,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    if submit_for_approval:
        return True, "Modèle créé dans Twilio et soumis pour approbation WhatsApp.", template_id
    return True, "Modèle créé dans Twilio, non soumis.", template_id


def _upsert_twilio_template(
    conn: Any,
    remote: TwilioContentTemplate,
    user_id: int,
    now: str,
    return_id: bool = False,
) -> str | int:
    existing = row_to_dict(
        conn.execute(
            "SELECT * FROM whatsapp_templates WHERE twilio_content_sid = ?",
            (remote.content_sid,),
        ).fetchone()
    )
    if not existing:
        existing = row_to_dict(
            conn.execute(
                """
                SELECT *
                FROM whatsapp_templates
                WHERE twilio_content_sid IS NULL
                  AND lower(name) = lower(?)
                ORDER BY id
                LIMIT 1
                """,
                (remote.name,),
            ).fetchone()
        )

    payload_json = json.dumps(remote.payload or {}, ensure_ascii=False)
    rejection_reason = remote.rejection_reason
    if existing:
        template_id = int(existing["id"])
        conn.execute(
            """
            UPDATE whatsapp_templates
            SET twilio_content_sid = ?,
                twilio_content_type = ?,
                twilio_payload_json = ?,
                last_twilio_sync_at = ?,
                name = ?,
                language = ?,
                category = ?,
                body = ?,
                status = ?,
                rejection_reason = ?,
                submitted_at = CASE WHEN ? = 'pending' AND submitted_at IS NULL THEN ? ELSE submitted_at END,
                approved_at = CASE WHEN ? = 'approved' THEN coalesce(approved_at, ?) ELSE approved_at END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                remote.content_sid,
                remote.content_type,
                payload_json,
                now,
                remote.name,
                remote.language,
                remote.category,
                remote.body,
                remote.status,
                rejection_reason,
                remote.status,
                now,
                remote.status,
                now,
                now,
                template_id,
            ),
        )
        _replace_template_placeholders(conn, template_id, remote.variables)
        return template_id if return_id else "updated"

    cursor = conn.execute(
        """
        INSERT INTO whatsapp_templates (
            twilio_content_sid, twilio_content_type, twilio_payload_json,
            last_twilio_sync_at, name, language, category, body, status,
            rejection_reason, created_by_user_id, submitted_at, approved_at,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            remote.content_sid,
            remote.content_type,
            payload_json,
            now,
            remote.name,
            remote.language,
            remote.category,
            remote.body,
            remote.status,
            rejection_reason,
            user_id,
            now if remote.status == "pending" else None,
            now if remote.status == "approved" else None,
            now,
            now,
        ),
    )
    template_id = int(cursor.lastrowid)
    _replace_template_placeholders(conn, template_id, remote.variables)
    return template_id if return_id else "created"


def _auto_approve_linked_template_requests(conn: Any, user_id: int, now: str) -> int:
    approved_request_ids: set[int] = set()
    requests = rows_to_dicts(
        conn.execute(
            """
            SELECT tr.*
            FROM template_requests tr
            JOIN whatsapp_templates wt ON wt.id = tr.template_id
            WHERE tr.status IN ('to_create', 'submitted')
              AND wt.status = 'approved'
              AND wt.twilio_content_sid IS NOT NULL
              AND wt.twilio_content_sid LIKE 'HX%'
              AND wt.twilio_content_sid NOT LIKE 'HX_MOCK_%'
            """
        ).fetchall()
    )
    for request in requests:
        _approve_template_request(conn, request, user_id, int(request["template_id"]), now)
        approved_request_ids.add(int(request["id"]))

    unlinked_requests = rows_to_dicts(
        conn.execute(
            """
            SELECT *
            FROM template_requests
            WHERE status IN ('to_create', 'submitted')
              AND template_id IS NULL
            """
        ).fetchall()
    )
    approved_templates = rows_to_dicts(
        conn.execute(
            """
            SELECT id, name, twilio_content_sid
            FROM whatsapp_templates
            WHERE status = 'approved'
              AND twilio_content_sid IS NOT NULL
              AND twilio_content_sid LIKE 'HX%'
              AND twilio_content_sid NOT LIKE 'HX_MOCK_%'
            """
        ).fetchall()
    )
    for request in unlinked_requests:
        request_text = f"{request.get('reason') or ''} {request.get('context') or ''}".lower()
        for template in approved_templates:
            template_name = str(template.get("name") or "").strip().lower()
            content_sid = str(template.get("twilio_content_sid") or "").strip().lower()
            if not template_name:
                continue
            if template_name in request_text or (content_sid and content_sid in request_text):
                _approve_template_request(conn, request, user_id, int(template["id"]), now)
                approved_request_ids.add(int(request["id"]))
                break
    return len(approved_request_ids)


def _approve_template_request(
    conn: Any,
    request: dict[str, Any],
    user_id: int,
    template_id: int,
    now: str,
) -> None:
    conn.execute(
        """
        UPDATE template_requests
        SET status = 'approved',
            template_id = ?,
            updated_at = ?,
            resolved_at = coalesce(resolved_at, ?)
        WHERE id = ?
        """,
        (template_id, now, now, request["id"]),
    )
    if request.get("task_id"):
        conn.execute(
            """
            UPDATE tasks
            SET status = 'open',
                due_at = ?,
                blocked_reason = NULL,
                updated_at = ?
            WHERE id = ?
              AND status = 'blocked'
            """,
            (now, now, request["task_id"]),
        )
    conn.execute(
        """
        UPDATE admin_actions
        SET status = 'done',
            outcome = 'template_request_approved',
            completed_by_user_id = ?,
            completed_at = ?,
            updated_at = ?
        WHERE template_request_id = ?
          AND status IN ('open', 'in_progress', 'blocked')
        """,
        (user_id, now, now, request["id"]),
    )
    insert_event(
        conn,
        request["lead_id"],
        "template_request_approved",
        user_id=user_id,
        previous={"status": request.get("status"), "template_id": request.get("template_id")},
        new={"status": "approved", "template_id": template_id, "task_id": request.get("task_id")},
    )


def _replace_template_placeholders(
    conn: Any,
    template_id: int,
    variables: dict[str, str],
) -> None:
    conn.execute("DELETE FROM template_placeholders WHERE template_id = ?", (template_id,))
    for key, example in variables.items():
        conn.execute(
            """
            INSERT INTO template_placeholders (
                template_id, placeholder_key, source_field, example_value, required
            ) VALUES (?, ?, ?, ?, 1)
            """,
            (template_id, key, key, example),
        )


def _map_twilio_local_status(status: str) -> str:
    value = status.strip().lower()
    if value == "approved":
        return "approved"
    if value in {"received", "pending"}:
        return "pending"
    if value == "rejected":
        return "rejected"
    return "draft"


def _placeholder_example(key: str) -> str:
    examples = {
        "first_name": "Camille",
        "course_title": "APP",
        "course_name": "APP GE P26",
        "1": "Camille",
        "2": "APP",
    }
    return examples.get(key, key)


def list_sequences() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM sequences
            WHERE active = 1
            ORDER BY code
            """
        ).fetchall()
    return rows_to_dicts(rows)


def list_sequence_steps(
    sequence_code: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if active_only:
        filters.append("active = 1")
    if sequence_code:
        filters.append("sequence_code = ?")
        params.append(sequence_code)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM sequence_steps
            {where}
            ORDER BY sequence_code, step_index
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def add_sequence_step(
    user_id: int,
    sequence_code: str,
    meaning: str,
    action_type: str = "follow_up",
    offset_direction: str = "after",
    offset_amount: int = 72,
    offset_unit: str = "hours",
) -> tuple[bool, str]:
    sequence_code = (sequence_code or "").strip()
    meaning = (meaning or "").strip()
    ok_step, message, normalized = _normalize_sequence_step_admin_values(
        action_type,
        offset_direction,
        offset_amount,
        offset_unit,
    )
    if not ok_step:
        return False, message
    if not sequence_code:
        return False, "Flux obligatoire."
    if not meaning:
        return False, "Description de l'événement obligatoire."
    action_type = normalized["action_type"]
    offset_direction = normalized["offset_direction"]
    offset_amount = normalized["offset_amount"]
    offset_unit = normalized["offset_unit"]
    requires_template = 1 if action_type == "follow_up" else 0
    delay = _format_sequence_delay(offset_direction, offset_amount, offset_unit)
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        sequence = conn.execute(
            "SELECT id FROM sequences WHERE code = ? AND active = 1",
            (sequence_code,),
        ).fetchone()
        if not sequence:
            return False, "Flux introuvable."
        next_index = conn.execute(
            """
            SELECT coalesce(max(step_index), 0) + 1 AS next_index
            FROM sequence_steps
            WHERE sequence_code = ?
            """,
            (sequence_code,),
        ).fetchone()["next_index"]
        conn.execute(
            """
            INSERT INTO sequence_steps (
                sequence_id, sequence_code, step_index, delay, action_type,
                offset_direction, offset_amount, offset_unit, template_name,
                requires_template, meaning, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 1, ?)
            """,
            (
                sequence["id"],
                sequence_code,
                next_index,
                delay,
                action_type,
                offset_direction,
                offset_amount,
                offset_unit,
                requires_template,
                meaning,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'sequence_step_added', 'sequence_step', ?, ?, ?)
            """,
            (
                user_id,
                next_index,
                json.dumps(
                    {
                        "sequence_code": sequence_code,
                        "step_index": next_index,
                        "delay": delay,
                        "action_type": action_type,
                        "offset_direction": offset_direction,
                        "offset_amount": offset_amount,
                        "offset_unit": offset_unit,
                        "requires_template": bool(requires_template),
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Étape ajoutée. Elle s'appliquera aux nouveaux flux."


def upsert_sequence_step(
    user_id: int,
    sequence_code: str,
    step_index: int,
    meaning: str,
    action_type: str = "follow_up",
    offset_direction: str = "after",
    offset_amount: int = 72,
    offset_unit: str = "hours",
) -> tuple[bool, str]:
    sequence_code = (sequence_code or "").strip()
    meaning = (meaning or "").strip()
    ok_step, message, normalized = _normalize_sequence_step_admin_values(
        action_type,
        offset_direction,
        offset_amount,
        offset_unit,
    )
    if not ok_step:
        return False, message
    if not sequence_code:
        return False, "Flux obligatoire."
    if not step_index:
        return False, "Étape obligatoire."
    if not meaning:
        return False, "Description de l'événement obligatoire."
    action_type = normalized["action_type"]
    offset_direction = normalized["offset_direction"]
    offset_amount = normalized["offset_amount"]
    offset_unit = normalized["offset_unit"]
    requires_template = 1 if action_type == "follow_up" else 0
    delay = _format_sequence_delay(offset_direction, offset_amount, offset_unit)
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        step = conn.execute(
            """
            SELECT id
            FROM sequence_steps
            WHERE sequence_code = ? AND step_index = ?
            """,
            (sequence_code, step_index),
        ).fetchone()
        if not step:
            return False, "Étape de flux introuvable."
        conn.execute(
            """
            UPDATE sequence_steps
            SET delay = ?,
                action_type = ?,
                offset_direction = ?,
                offset_amount = ?,
                offset_unit = ?,
                meaning = ?,
                requires_template = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                delay,
                action_type,
                offset_direction,
                offset_amount,
                offset_unit,
                meaning,
                requires_template,
                now,
                step["id"],
            ),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'sequence_step_updated', 'sequence_step', ?, ?, ?)
            """,
            (
                user_id,
                step["id"],
                json.dumps(
                    {
                        "sequence_code": sequence_code,
                        "step_index": step_index,
                        "delay": delay,
                        "action_type": action_type,
                        "offset_direction": offset_direction,
                        "offset_amount": offset_amount,
                        "offset_unit": offset_unit,
                        "requires_template": bool(requires_template),
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Étape enregistrée. Elle s'appliquera aux nouveaux flux."


def reactivate_sequence_step(user_id: int, step_id: int) -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        step = conn.execute(
            "SELECT id, sequence_code, step_index FROM sequence_steps WHERE id = ? AND active = 0",
            (step_id,),
        ).fetchone()
        if not step:
            return False, "Étape inactive introuvable."
        conn.execute(
            "UPDATE sequence_steps SET active = 1, updated_at = ? WHERE id = ?",
            (now, step_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'sequence_step_reactivated', 'sequence_step', ?, ?, ?)
            """,
            (
                user_id,
                step_id,
                json.dumps(
                    {
                        "sequence_code": step["sequence_code"],
                        "step_index": step["step_index"],
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Étape réactivée."


def deactivate_sequence_step(user_id: int, step_id: int) -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        step = conn.execute(
            "SELECT id, sequence_code, step_index FROM sequence_steps WHERE id = ? AND active = 1",
            (step_id,),
        ).fetchone()
        if not step:
            return False, "Étape active introuvable."
        conn.execute(
            "UPDATE sequence_steps SET active = 0, updated_at = ? WHERE id = ?",
            (now, step_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'sequence_step_deactivated', 'sequence_step', ?, ?, ?)
            """,
            (
                user_id,
                step_id,
                json.dumps(
                    {
                        "sequence_code": step["sequence_code"],
                        "step_index": step["step_index"],
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Étape désactivée. Elle ne sera pas utilisée pour les nouveaux flux."


def _normalize_sequence_step_admin_values(
    action_type: str,
    offset_direction: str,
    offset_amount: int,
    offset_unit: str,
) -> tuple[bool, str, dict[str, Any]]:
    normalized_action = (action_type or "").strip()
    if normalized_action not in {"follow_up", "setting_call", "closing_call", "other"}:
        return False, "Type d'action invalide.", {}
    normalized_direction = (offset_direction or "").strip()
    if normalized_direction not in {"after", "before"}:
        return False, "Point temporel invalide.", {}
    normalized_unit = (offset_unit or "").strip()
    if normalized_unit not in {"hours", "days"}:
        return False, "Unité invalide.", {}
    try:
        amount = int(offset_amount)
    except (TypeError, ValueError):
        return False, "Délai invalide.", {}
    if amount < 0:
        return False, "Le délai ne peut pas être négatif.", {}
    if amount == 0 and normalized_action == "follow_up":
        return False, "Une relance WhatsApp doit avoir un délai supérieur à zéro.", {}
    return True, "", {
        "action_type": normalized_action,
        "offset_direction": normalized_direction,
        "offset_amount": amount,
        "offset_unit": normalized_unit,
    }


def list_course_categories(active_only: bool = True) -> list[dict[str, Any]]:
    filters = []
    if active_only:
        filters.append("active = 1")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM course_categories
            {where}
            ORDER BY course_category
            """
        ).fetchall()
    return rows_to_dicts(rows)


def upsert_course_category(
    user_id: int,
    course_category: str,
    label: str = "",
    note: str = "",
) -> tuple[bool, str]:
    category = (course_category or "").strip().upper()
    clean_label = (label or "").strip() or category
    clean_note = (note or "").strip()
    if not category:
        return False, "Catégorie obligatoire."
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        conn.execute(
            """
            INSERT INTO course_categories (
                course_category, label, active, note,
                created_by_user_id, updated_by_user_id, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
            ON CONFLICT(course_category) DO UPDATE SET
                label = excluded.label,
                note = excluded.note,
                active = 1,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = excluded.updated_at
            """,
            (
                category,
                clean_label,
                clean_note or None,
                user_id,
                user_id,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT id FROM course_categories WHERE course_category = ?",
            (category,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'course_category_upserted', 'course_category', ?, ?, ?)
            """,
            (
                user_id,
                row["id"] if row else None,
                json.dumps(
                    {"course_category": category, "label": clean_label},
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Catégorie enregistrée."


def deactivate_course_category(user_id: int, category_id: int) -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        existing = conn.execute(
            "SELECT id, course_category FROM course_categories WHERE id = ? AND active = 1",
            (category_id,),
        ).fetchone()
        if not existing:
            return False, "Catégorie active introuvable."
        conn.execute(
            """
            UPDATE course_categories
            SET active = 0, updated_by_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (user_id, now, category_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'course_category_deactivated', 'course_category', ?, ?, ?)
            """,
            (
                user_id,
                category_id,
                json.dumps(
                    {"course_category": existing["course_category"]},
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Catégorie désactivée."


def list_sequence_template_mappings() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                stm.*,
                ss.delay,
                ss.meaning,
                wt.name AS template_name,
                wt.status AS template_status,
                wt.language AS template_language,
                wt.category AS template_category,
                wt.body AS template_body,
                wt.twilio_content_type,
                wt.twilio_content_sid
            FROM sequence_template_mappings stm
            LEFT JOIN sequence_steps ss
              ON ss.sequence_code = stm.sequence_code
             AND ss.step_index = stm.sequence_step_index
            LEFT JOIN whatsapp_templates wt ON wt.id = stm.template_id
            WHERE stm.active = 1
            ORDER BY stm.sequence_code, stm.sequence_step_index, stm.lead_type, stm.course_category
            """
        ).fetchall()
    return rows_to_dicts(rows)


def list_course_default_sessions(active_only: bool = True) -> list[dict[str, Any]]:
    filters = []
    if active_only:
        filters.append("active = 1")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM course_default_sessions
            {where}
            ORDER BY course_category
            """
        ).fetchall()
    return rows_to_dicts(rows)


def upsert_course_default_session(
    user_id: int,
    course_category: str,
    default_course_name: str,
    default_start_date: str,
    default_session_name: str = "",
    schooldrive_url: str = "",
    note: str = "",
) -> tuple[bool, str]:
    category = (course_category or "").strip().upper()
    course_name = (default_course_name or "").strip()
    start_date = (default_start_date or "").strip()
    session_name = (default_session_name or "").strip()
    url = (schooldrive_url or "").strip()
    clean_note = (note or "").strip()
    if not category:
        return False, "Catégorie de cours obligatoire."
    if not course_name:
        return False, "Nom du cours ou de la session obligatoire."
    if not start_date:
        return False, "Date de début obligatoire."
    try:
        datetime.fromisoformat(start_date)
    except ValueError:
        return False, "Date de début invalide. Format attendu : AAAA-MM-JJ."
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        conn.execute(
            """
            INSERT INTO course_default_sessions (
                course_category, default_course_name, default_session_name,
                default_start_date, schooldrive_url, note, active,
                created_by_user_id, updated_by_user_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(course_category) DO UPDATE SET
                default_course_name = excluded.default_course_name,
                default_session_name = excluded.default_session_name,
                default_start_date = excluded.default_start_date,
                schooldrive_url = excluded.schooldrive_url,
                note = excluded.note,
                active = 1,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = excluded.updated_at
            """,
            (
                category,
                course_name,
                session_name or None,
                start_date,
                url or None,
                clean_note or None,
                user_id,
                user_id,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT id FROM course_default_sessions WHERE course_category = ?",
            (category,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'course_default_session_upserted', 'course_default_session', ?, ?, ?)
            """,
            (
                user_id,
                row["id"] if row else None,
                json.dumps(
                    {
                        "course_category": category,
                        "default_course_name": course_name,
                        "default_start_date": start_date,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Session par défaut enregistrée."


def deactivate_course_default_session(user_id: int, session_id: int) -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        existing = conn.execute(
            "SELECT id FROM course_default_sessions WHERE id = ? AND active = 1",
            (session_id,),
        ).fetchone()
        if not existing:
            return False, "Session par défaut introuvable."
        conn.execute(
            """
            UPDATE course_default_sessions
            SET active = 0, updated_by_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (user_id, now, session_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, created_at
            ) VALUES (?, 'course_default_session_deactivated', 'course_default_session', ?, ?)
            """,
            (user_id, session_id, now),
        )
    return True, "Session par défaut désactivée."


def upsert_sequence_template_mapping(
    user_id: int,
    sequence_code: str,
    sequence_step_index: int,
    lead_type: str,
    course_category: str,
    template_id: int,
    note: str = "",
) -> tuple[bool, str]:
    sequence_code = sequence_code.strip()
    lead_type = _normalize_mapping_dimension(lead_type)
    course_category = _normalize_mapping_dimension(course_category, uppercase=True)
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        step = conn.execute(
            """
            SELECT id, action_type FROM sequence_steps
            WHERE sequence_code = ? AND step_index = ? AND active = 1
            """,
            (sequence_code, sequence_step_index),
        ).fetchone()
        if not step:
            return False, "Étape de flux introuvable."
        if step["action_type"] != "follow_up":
            return False, "Un template ne peut être recommandé que pour une relance WhatsApp."
        template = conn.execute(
            """
            SELECT id, status, twilio_content_sid
            FROM whatsapp_templates
            WHERE id = ?
            """,
            (template_id,),
        ).fetchone()
        if not template:
            return False, "Modèle WhatsApp introuvable."
        if not _is_approved_real_twilio_template(template):
            return False, "Seuls les templates Twilio approuvés par WhatsApp peuvent être recommandés."
        conn.execute(
            """
            INSERT INTO sequence_template_mappings (
                sequence_code, sequence_step_index, lead_type, course_category,
                template_id, note, active, created_by_user_id, updated_by_user_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(sequence_code, sequence_step_index, lead_type, course_category)
            DO UPDATE SET
                template_id = excluded.template_id,
                note = excluded.note,
                active = 1,
                updated_by_user_id = excluded.updated_by_user_id,
                updated_at = excluded.updated_at
            """,
            (
                sequence_code,
                sequence_step_index,
                lead_type,
                course_category,
                template_id,
                note.strip(),
                user_id,
                user_id,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, metadata_json, created_at
            ) VALUES (?, 'sequence_template_mapping_upserted', 'sequence_template_mapping', ?, ?, ?)
            """,
            (
                user_id,
                template_id,
                json.dumps(
                    {
                        "sequence_code": sequence_code,
                        "sequence_step_index": sequence_step_index,
                        "lead_type": lead_type,
                        "course_category": course_category,
                    },
                    ensure_ascii=False,
                ),
                now,
            ),
        )
    return True, "Mapping modèle enregistré."


def deactivate_sequence_template_mapping(user_id: int, mapping_id: int) -> tuple[bool, str]:
    now = iso_utc()
    with connect() as conn:
        ok, message = _require_admin_user(conn, user_id)
        if not ok:
            return False, message
        existing = conn.execute(
            "SELECT id FROM sequence_template_mappings WHERE id = ? AND active = 1",
            (mapping_id,),
        ).fetchone()
        if not existing:
            return False, "Mapping introuvable."
        conn.execute(
            """
            UPDATE sequence_template_mappings
            SET active = 0, updated_by_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (user_id, now, mapping_id),
        )
        conn.execute(
            """
            INSERT INTO user_activity_log (
                user_id, event_type, entity_type, entity_id, created_at
            ) VALUES (?, 'sequence_template_mapping_deactivated', 'sequence_template_mapping', ?, ?)
            """,
            (user_id, mapping_id, now),
        )
    return True, "Mapping désactivé."


def get_recommended_template_for_action(action_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        mapping = _recommended_template_mapping_for_action(conn, action_id)
    return row_to_dict(mapping)


def _recommended_template_mapping_for_action(conn: Any, action_id: int) -> Any:
    row = conn.execute(
        """
        SELECT
            t.sequence_code,
            t.sequence_step_index,
            l.lead_type,
            l.course_category_short_title
        FROM tasks t
        JOIN leads l ON l.id = t.lead_id
        WHERE t.id = ? AND t.type = 'follow_up'
          AND t.sequence_code IS NOT NULL
          AND t.sequence_step_index IS NOT NULL
        """,
        (action_id,),
    ).fetchone()
    if not row:
        return None
    action = row_to_dict(row)
    lead_type = _normalize_mapping_dimension(action.get("lead_type") or "all")
    course_category = _normalize_mapping_dimension(
        action.get("course_category_short_title") or "all",
        uppercase=True,
    )
    return conn.execute(
        """
        SELECT
            stm.*,
            wt.name AS template_name,
            wt.status AS template_status,
            wt.language AS template_language,
            wt.category AS template_category,
            wt.body AS template_body,
            wt.twilio_content_sid,
            wt.twilio_content_type
        FROM sequence_template_mappings stm
        JOIN whatsapp_templates wt ON wt.id = stm.template_id
        WHERE stm.active = 1
          AND wt.status = 'approved'
          AND wt.twilio_content_sid IS NOT NULL
          AND wt.twilio_content_sid LIKE 'HX%'
          AND wt.twilio_content_sid NOT LIKE 'HX_MOCK_%'
          AND stm.sequence_code = ?
          AND stm.sequence_step_index = ?
          AND stm.lead_type IN ('all', ?)
          AND stm.course_category IN ('all', ?)
        ORDER BY
            CASE WHEN stm.lead_type = ? THEN 1 ELSE 0 END DESC,
            CASE WHEN stm.course_category = ? THEN 1 ELSE 0 END DESC,
            stm.updated_at DESC
        LIMIT 1
        """,
        (
            action["sequence_code"],
            action["sequence_step_index"],
            lead_type,
            course_category,
            lead_type,
            course_category,
        ),
    ).fetchone()


def _is_approved_real_twilio_template(template: Any) -> bool:
    status = template["status"] or ""
    sid = template["twilio_content_sid"] or ""
    sid = str(sid)
    return status == "approved" and sid.startswith("HX") and not sid.startswith("HX_MOCK_")


def _normalize_mapping_dimension(value: str, uppercase: bool = False) -> str:
    normalized = (value or "all").strip()
    if not normalized or normalized.lower() in {"all", "tous", "toutes", "*"}:
        return "all"
    return normalized.upper() if uppercase else normalized.lower()


def list_template_requests(status: str = "all") -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if status != "all":
        filters.append("tr.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                tr.*,
                l.first_name,
                l.last_name,
                l.course_title,
                l.course_category_short_title,
                t.title AS action_title,
                u.full_name AS requested_by_name,
                wt.name AS template_name
            FROM template_requests tr
            JOIN leads l ON l.id = tr.lead_id
            LEFT JOIN tasks t ON t.id = tr.task_id
            LEFT JOIN users u ON u.id = tr.requested_by_user_id
            LEFT JOIN whatsapp_templates wt ON wt.id = tr.template_id
            {where}
            ORDER BY
                CASE tr.status
                    WHEN 'to_create' THEN 0
                    WHEN 'submitted' THEN 1
                    WHEN 'approved' THEN 2
                    WHEN 'rejected' THEN 3
                    ELSE 4
                END,
                datetime(tr.created_at) DESC
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def create_template_request(
    conversation_id: int,
    user_id: int,
    reason: str,
    context: str = "",
    task_id: int | None = None,
    sequence_code: str | None = None,
    sequence_step_index: int | None = None,
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if not reason.strip():
        return False, "Explique pourquoi le modèle manque."

    now = iso_utc()
    with connect() as conn:
        action = None
        if task_id is None:
            action = row_to_dict(
                conn.execute(
                    """
                    SELECT *
                    FROM tasks
                    WHERE lead_id = ?
                      AND type = 'follow_up'
                      AND status IN ('open', 'in_progress', 'planned', 'blocked')
                    ORDER BY
                        datetime(coalesce(due_at, created_at)) ASC,
                        id ASC
                    LIMIT 1
                    """,
                    (conv["lead_id"],),
                ).fetchone()
            )
            task_id = action["id"] if action else None
        else:
            action = row_to_dict(
                conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            )

        cursor = conn.execute(
            """
            INSERT INTO template_requests (
                lead_id, conversation_id, task_id, sequence_code, sequence_step_index,
                course_id, requested_by_user_id, status, reason, context, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'to_create', ?, ?, ?, ?)
            """,
            (
                conv["lead_id"],
                conversation_id,
                task_id,
                sequence_code or (action or {}).get("sequence_code"),
                sequence_step_index or (action or {}).get("sequence_step_index"),
                conv.get("course_id"),
                user_id,
                reason.strip(),
                context.strip() or None,
                now,
                now,
            ),
        )
        request_id = int(cursor.lastrowid)
        if task_id:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'blocked',
                    blocked_reason = 'template_missing',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
        insert_event(
            conn,
            conv["lead_id"],
            "template_request_created",
            user_id=user_id,
            new={
                "template_request_id": request_id,
                "task_id": task_id,
                "sequence_code": sequence_code,
                "sequence_step_index": sequence_step_index,
                "reason": reason,
            },
        )
        admin_action_id = _ensure_admin_action(
            conn,
            "template_request",
            f"Créer / lier modèle WhatsApp pour {lead_full_name(conv)}",
            description=(context.strip() or reason.strip()),
            lead_id=conv["lead_id"],
            conversation_id=conversation_id,
            task_id=task_id,
            template_request_id=request_id,
            created_by_user_id=user_id,
            metadata={
                "sequence_code": sequence_code or (action or {}).get("sequence_code"),
                "sequence_step_index": sequence_step_index or (action or {}).get("sequence_step_index"),
                "reason": reason.strip(),
            },
        )
        if admin_action_id:
            conn.execute(
                """
                INSERT INTO user_activity_log (
                    user_id, event_type, entity_type, entity_id,
                    lead_id, conversation_id, action_id, metadata_json, created_at
                ) VALUES (?, 'admin_action_created', 'admin_action', ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    admin_action_id,
                    conv["lead_id"],
                    conversation_id,
                    task_id,
                    json.dumps({"source": "template_request", "template_request_id": request_id}, ensure_ascii=False),
                    now,
                ),
            )
    if task_id:
        return True, "Demande de modèle créée et relance bloquée."
    return True, "Demande de modèle créée."


def update_template_request_status(
    request_id: int,
    user_id: int,
    status: str,
    template_id: int | None = None,
) -> tuple[bool, str]:
    allowed_statuses = {"to_create", "submitted", "approved", "rejected", "cancelled"}
    if status not in allowed_statuses:
        return False, "Statut de demande invalide."
    now = iso_utc()
    with connect() as conn:
        request = row_to_dict(
            conn.execute("SELECT * FROM template_requests WHERE id = ?", (request_id,)).fetchone()
        )
        if not request:
            return False, "Demande de modèle introuvable."
        effective_template_id = template_id or request.get("template_id")
        if status == "approved":
            if not effective_template_id:
                return False, "Associe d'abord un modèle Twilio approuvé à cette demande."
            template = row_to_dict(
                conn.execute(
                    "SELECT * FROM whatsapp_templates WHERE id = ?",
                    (effective_template_id,),
                ).fetchone()
            )
            if not template or not _is_approved_real_twilio_template(template):
                return False, "La demande ne peut être approuvée qu'avec un modèle WhatsApp Twilio approuvé."
        conn.execute(
            """
            UPDATE template_requests
            SET status = ?, template_id = coalesce(?, template_id),
                updated_at = ?, resolved_at = CASE WHEN ? IN ('approved', 'rejected', 'cancelled') THEN ? ELSE resolved_at END
            WHERE id = ?
            """,
            (status, template_id, now, status, now, request_id),
        )
        if status == "approved" and request.get("task_id"):
            conn.execute(
                """
                UPDATE tasks
                SET status = 'open',
                    due_at = ?,
                    blocked_reason = NULL,
                    updated_at = ?
                WHERE id = ? AND status = 'blocked'
                """,
                (now, now, request["task_id"]),
            )
        if status in {"approved", "rejected", "cancelled"}:
            conn.execute(
                """
                UPDATE admin_actions
                SET status = 'done',
                    outcome = ?,
                    completed_by_user_id = ?,
                    completed_at = ?,
                    updated_at = ?
                WHERE template_request_id = ?
                  AND status IN ('open', 'in_progress', 'blocked')
                """,
                (f"template_request_{status}", user_id, now, now, request_id),
            )
        insert_event(
            conn,
            request["lead_id"],
            "template_request_status_updated",
            user_id=user_id,
            previous={"status": request["status"], "template_id": request.get("template_id")},
            new={"status": status, "template_id": template_id},
        )
    return True, "Demande de modèle mise à jour."


def update_temporary_identity(
    conversation_id: int,
    user_id: int,
    first_name: str,
    last_name: str,
    course_category_short_title: str | None,
    course_title: str | None,
    note: str | None = None,
) -> tuple[bool, str]:
    first_name = first_name.strip() or "Inconnu(e)"
    last_name = last_name.strip()
    category = (course_category_short_title or "").strip() or None
    course = (course_title or "").strip() or None
    note = (note or "").strip() or None
    now = iso_utc()
    with connect() as conn:
        row = row_to_dict(
            conn.execute(
                """
                SELECT
                    c.id AS conversation_id,
                    l.id AS lead_id,
                    l.schooldrive_lead_id,
                    l.first_name,
                    l.last_name,
                    l.course_category_short_title,
                    l.course_title,
                    l.identity_status,
                    l.identity_review_note
                FROM conversations c
                JOIN leads l ON l.id = c.lead_id
                WHERE c.id = ?
                """,
                (conversation_id,),
            ).fetchone()
        )
        if not row:
            return False, "Conversation introuvable."
        if row.get("identity_status") not in IDENTITY_REVIEW_STATUSES and row.get("schooldrive_lead_id"):
            return False, "Cette fiche est déjà reliée à SchoolDrive."

        conn.execute(
            """
            UPDATE leads
            SET first_name = ?, last_name = ?,
                course_category_short_title = ?,
                course_title = ?,
                identity_status = CASE
                    WHEN identity_status = 'ambiguous_identity' THEN 'ambiguous_identity'
                    ELSE 'needs_identification'
                END,
                identity_review_note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                first_name,
                last_name,
                category,
                course,
                note,
                now,
                row["lead_id"],
            ),
        )
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        note_parts = [f"Nom temporaire : {full_name or 'Inconnu(e)'}"]
        if category:
            note_parts.append(f"Catégorie : {category}")
        if course:
            note_parts.append(f"Cours : {course}")
        if note:
            note_parts.append(f"Note : {note}")
        _insert_internal_note_message(
            conn,
            row["lead_id"],
            conversation_id,
            user_id,
            "Identification à vérifier. " + " · ".join(note_parts),
            now,
        )
        insert_event(
            conn,
            row["lead_id"],
            "temporary_identity_updated",
            user_id=user_id,
            previous={
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "course_category_short_title": row.get("course_category_short_title"),
                "course_title": row.get("course_title"),
                "identity_review_note": row.get("identity_review_note"),
            },
            new={
                "first_name": first_name,
                "last_name": last_name,
                "course_category_short_title": category,
                "course_title": course,
                "identity_status": row.get("identity_status")
                or IDENTITY_STATUS_NEEDS_IDENTIFICATION,
                "identity_review_note": note,
            },
            metadata={"conversation_id": conversation_id},
        )
    return True, "Identification temporaire mise à jour."


def update_lead_qualification(
    lead_id: int,
    user_id: int,
    sales_stage: str,
    lead_status: str,
    temperature: str | None = None,
    contact_status: str | None = None,
) -> None:
    now = iso_utc()
    if sales_stage == "won":
        lead_status = "signed"
    elif sales_stage in {"lost", "not_interesting"}:
        lead_status = "not_relevant"
    elif sales_stage == "blacklist":
        contact_status = "do_not_contact"
        lead_status = "eligible"
    if lead_status == "do_not_contact":
        contact_status = "do_not_contact"
        lead_status = "eligible"
    with connect() as conn:
        previous = row_to_dict(
            conn.execute(
                "SELECT sales_stage, temperature, lead_status, contact_status FROM leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
        )
        stage_changed = sales_stage != previous["sales_stage"]
        lead_status_changed = lead_status != previous["lead_status"]
        effective_temperature = temperature or previous["temperature"]
        effective_contact_status = contact_status or previous.get("contact_status") or "contact_allowed"
        conn.execute(
            """
            UPDATE leads
            SET sales_stage = ?, temperature = ?, lead_status = ?,
                contact_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                sales_stage,
                effective_temperature,
                lead_status,
                effective_contact_status,
                now,
                lead_id,
            ),
        )
        if (
            lead_status in STOP_QUALIFICATION_STATUSES
            or effective_contact_status in STOP_CONTACT_STATUSES
        ):
            resolution_reason = (
                "do_not_contact"
                if effective_contact_status in STOP_CONTACT_STATUSES
                else lead_status
            )
            _complete_open_actions_for_lead(
                conn,
                lead_id,
                user_id,
                outcome=f"Statut terminal : {resolution_reason}",
            )
            conn.execute(
                """
                UPDATE conversations
                SET status = 'resolved',
                    resolution_reason = ?,
                    resolved_at = ?,
                    updated_at = ?
                WHERE lead_id = ?
                """,
                (resolution_reason, now, now, lead_id),
            )
        elif stage_changed and sales_stage == "appointment_booked":
            _sync_next_action_for_sales_stage(conn, lead_id, user_id, sales_stage, now)
        elif lead_status == "will_sign" and lead_status_changed:
            _sync_next_action_for_lead_status(conn, lead_id, user_id, lead_status, now)
        elif stage_changed:
            _sync_next_action_for_sales_stage(conn, lead_id, user_id, sales_stage, now)
        insert_event(
            conn,
            lead_id,
            "lead_qualification_updated",
            user_id=user_id,
            previous=previous,
            new={
                "sales_stage": sales_stage,
                "temperature": effective_temperature,
                "lead_status": lead_status,
                "contact_status": effective_contact_status,
            },
        )


def _sync_next_action_for_sales_stage(
    conn: Any,
    lead_id: int,
    user_id: int,
    sales_stage: str,
    now: str,
) -> None:
    row = row_to_dict(
        conn.execute(
            """
            SELECT
                l.id AS lead_id,
                l.first_name,
                l.last_name,
                l.setter_user_id,
                l.closer_user_id,
                c.id AS conversation_id,
                c.status AS conversation_status
            FROM leads l
            LEFT JOIN conversations c ON c.lead_id = l.id
            WHERE l.id = ?
            ORDER BY c.id DESC
            LIMIT 1
            """,
            (lead_id,),
        ).fetchone()
    )
    if not row or row.get("conversation_status") != "open" or not row.get("conversation_id"):
        return

    target_type = None
    assignee_id = None
    urgency = "normal"
    trigger_reason = f"sales_stage_forced_{sales_stage}"
    full_name = lead_full_name(row)

    if sales_stage == "closing":
        target_type = "closing_call"
        assignee_id = row.get("closer_user_id") or default_closer_user_id(conn)
        title = f"Documenter l'appel closing de {full_name}"
        urgency = "high"
    elif sales_stage == "appointment_booked":
        target_type = "setting_call"
        assignee_id = row.get("setter_user_id") or _default_active_user_id(conn, "setter")
        title = f"Documenter l'appel setting de {full_name}"
        urgency = "high"
    elif sales_stage in {"new", "setting"}:
        target_type = "reply"
        assignee_id = row.get("setter_user_id") or _default_active_user_id(conn, "setter")
        title = f"Répondre à {full_name}"
    else:
        return

    if not target_type or not assignee_id:
        return

    active = _first_active_action_for_lead(conn, lead_id)
    if active and active.get("type") == target_type:
        conn.execute(
            """
            UPDATE tasks
            SET assigned_to_user_id = coalesce(assigned_to_user_id, ?),
                due_at = coalesce(due_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (assignee_id, now, now, active["id"]),
        )
        return

    _complete_open_actions_for_lead(
        conn,
        lead_id,
        user_id,
        outcome=f"Forçage parcours : {sales_stage}",
        excluded_types=(target_type,),
    )

    existing = _first_active_action_for_lead(conn, lead_id, action_types=(target_type,))
    if existing:
        return

    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=row["conversation_id"],
        action_type=target_type,
        title=title,
        assigned_to_user_id=assignee_id,
        created_by_user_id=user_id,
        urgency=urgency,
        due_at=now,
        trigger_reason=trigger_reason,
    )
    insert_event(
        conn,
        lead_id,
        "next_action_created_by_sales_stage_force",
        user_id=user_id,
        new={
            "task_id": action_id,
            "sales_stage": sales_stage,
            "action_type": target_type,
            "assigned_to_user_id": assignee_id,
        },
    )


def _sync_next_action_for_lead_status(
    conn: Any,
    lead_id: int,
    user_id: int,
    lead_status: str,
    now: str,
) -> None:
    if lead_status != "will_sign":
        return

    row = row_to_dict(
        conn.execute(
            """
            SELECT
                l.id AS lead_id,
                l.first_name,
                l.last_name,
                c.id AS conversation_id,
                c.status AS conversation_status
            FROM leads l
            LEFT JOIN conversations c ON c.lead_id = l.id
            WHERE l.id = ?
            ORDER BY c.id DESC
            LIMIT 1
            """,
            (lead_id,),
        ).fetchone()
    )
    if not row or row.get("conversation_status") != "open" or not row.get("conversation_id"):
        return

    assignee_id = setter2_user_id(conn) or _default_active_user_id(conn, "setter")
    if not assignee_id:
        return

    active = _first_active_action_for_lead(conn, lead_id)
    if active and active.get("type") == "follow_up":
        conn.execute(
            """
            UPDATE tasks
            SET assigned_to_user_id = ?,
                due_at = coalesce(due_at, ?),
                sequence_code = coalesce(sequence_code, 'closer_will_sign'),
                sequence_step_index = coalesce(sequence_step_index, 1),
                updated_at = ?
            WHERE id = ?
            """,
            (assignee_id, _due_after(now, "+72h"), now, active["id"]),
        )
        return

    _complete_open_actions_for_lead(
        conn,
        lead_id,
        user_id,
        outcome="Qualification : va signer",
        excluded_types=("follow_up",),
    )

    existing = _first_active_action_for_lead(conn, lead_id, action_types=("follow_up",))
    if existing:
        return

    full_name = lead_full_name(row)
    action_id = _insert_next_action(
        conn,
        lead_id=lead_id,
        conversation_id=row["conversation_id"],
        action_type="follow_up",
        title=f"Relancer {full_name}",
        assigned_to_user_id=assignee_id,
        created_by_user_id=user_id,
        urgency="normal",
        due_at=_due_after(now, "+72h"),
        trigger_reason="lead_status_forced_will_sign",
        sequence_code="closer_will_sign",
        sequence_step_index=1,
    )
    insert_event(
        conn,
        lead_id,
        "next_action_created_by_lead_status_force",
        user_id=user_id,
        new={
            "task_id": action_id,
            "type": "follow_up",
            "lead_status": lead_status,
            "assigned_to_user_id": assignee_id,
        },
    )


def _validate_freeform_attachments(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(attachments) > MAX_FREEFORM_ATTACHMENTS:
        raise ValueError(f"Maximum {MAX_FREEFORM_ATTACHMENTS} pièces jointes par message.")
    validated: list[dict[str, Any]] = []
    for item in attachments:
        file_name = _safe_attachment_filename(str(item.get("file_name") or item.get("name") or "piece_jointe"))
        content = item.get("content")
        if content is None:
            content = item.get("bytes")
        if isinstance(content, bytearray):
            content = bytes(content)
        if not isinstance(content, bytes):
            raise ValueError(f"Pièce jointe invalide : {file_name}.")
        if not content:
            raise ValueError(f"Pièce jointe vide : {file_name}.")
        if len(content) > MAX_FREEFORM_ATTACHMENT_BYTES:
            limit_mb = MAX_FREEFORM_ATTACHMENT_BYTES // (1024 * 1024)
            raise ValueError(f"Pièce jointe trop lourde : {file_name}. Limite V1 : {limit_mb} Mo.")
        validated.append(
            {
                "file_name": file_name,
                "mime_type": str(item.get("mime_type") or item.get("type") or "application/octet-stream"),
                "content": content,
            }
        )
    return validated


def _safe_attachment_filename(value: str) -> str:
    name = Path(value).name.strip() or "piece_jointe"
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "piece_jointe"


def _media_public_base_url() -> str:
    settings = get_settings()
    configured = (settings.public_api_base_url or "").strip().rstrip("/")
    if configured:
        return configured
    webhook_url = (settings.twilio_webhook_url or "").strip()
    if not webhook_url:
        return ""
    parsed = urlparse(webhook_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _store_message_attachments(
    conn: Any,
    message_id: int,
    attachments: list[dict[str, Any]],
    media_base_url: str,
) -> list[str]:
    if not attachments:
        return []
    now = iso_utc()
    stored_urls: list[str] = []
    attachment_dir = get_settings().resolved_storage_path / "attachments" / str(message_id)
    attachment_dir.mkdir(parents=True, exist_ok=True)
    for item in attachments:
        token = uuid4().hex
        storage_name = f"{token}_{item['file_name']}"
        storage_path = attachment_dir / storage_name
        storage_path.write_bytes(item["content"])
        cursor = conn.execute(
            """
            INSERT INTO attachments (
                message_id, source, file_name, mime_type, size_bytes,
                storage_url_or_path, created_at
            ) VALUES (?, 'outbound_upload', ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                item["file_name"],
                item["mime_type"],
                len(item["content"]),
                str(storage_path),
                now,
            ),
        )
        attachment = {"id": int(cursor.lastrowid), "storage_url_or_path": str(storage_path)}
        if media_base_url:
            stored_urls.append(_attachment_public_url(attachment, media_base_url))
    return stored_urls


def _attachment_public_url(attachment: dict[str, Any], media_base_url: str | None = None) -> str:
    base_url = (media_base_url if media_base_url is not None else _media_public_base_url()).rstrip("/")
    if not base_url:
        return ""
    path = Path(str(attachment.get("storage_url_or_path") or ""))
    token_name = quote(path.name, safe="")
    attachment_id = attachment.get("id")
    if not attachment_id or not token_name:
        return ""
    return f"{base_url}/media/attachments/{attachment_id}/{token_name}"


def get_attachment_download(attachment_id: int, token_name: str) -> dict[str, Any] | None:
    token_name = Path(token_name).name
    with connect() as conn:
        attachment = row_to_dict(
            conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        )
    if not attachment:
        return None
    path = Path(str(attachment.get("storage_url_or_path") or ""))
    if path.name != token_name or not path.exists() or not path.is_file():
        return None
    return {
        "path": path,
        "mime_type": attachment.get("mime_type") or "application/octet-stream",
        "file_name": attachment.get("file_name") or path.name,
    }


def send_freeform_message(
    conversation_id: int,
    user_id: int,
    body: str,
    action_outcome: str | None = None,
    next_due_at: str | None = None,
    assigned_to_user_id: int | None = None,
    note: str = "",
    attachments: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if conv.get("contact_status") in STOP_CONTACT_STATUSES:
        return False, "Contact bloqué : le statut Ne plus contacter doit être levé avant tout envoi."
    if conv.get("status") == "resolved":
        return False, "Conversation terminée : réactivez-la avant tout envoi."
    body = body.strip()
    with connect() as conn:
        action_kind = _active_outbound_action_kind(conn, conv["lead_id"])
        if action_kind == "follow_up" and _has_blocked_followup(conn, conv["lead_id"]):
            return False, "Relance bloquée : le nouveau modèle doit être approuvé avant l'envoi."
    state = calculate_window(conv["last_inbound_at"])
    if not state.is_open:
        return False, "Fenêtre WhatsApp fermée. Utilisez un modèle approuvé."
    try:
        attachment_items = _validate_freeform_attachments(attachments or [])
    except ValueError as exc:
        return False, str(exc)
    if not body and not attachment_items:
        return False, "Écrivez un message ou ajoutez une pièce jointe avant l'envoi."
    stored_body = body or "[Pièce jointe WhatsApp]"
    media_base_url = _media_public_base_url()
    if attachment_items and (get_settings().twilio_mode or "mock").lower() != "mock" and not media_base_url:
        return False, "Pièce jointe impossible : configure SALES_COCKPIT_PUBLIC_API_BASE_URL pour que Twilio puisse récupérer le média."
    with connect() as conn:
        ok, guard_message = _check_outbound_safeguards(conn, conv, action_kind=action_kind)
        if not ok:
            return False, guard_message

    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, sender_user_id,
                twilio_status, whatsapp_window_state_at_send, created_at
            ) VALUES (?, ?, 'outbound', 'whatsapp_twilio', ?, ?, 'pending_send', ?, ?)
            """,
            (conversation_id, conv["lead_id"], stored_body, user_id, state.state, now),
        )
        message_id = int(cursor.lastrowid)
        media_urls = _store_message_attachments(conn, message_id, attachment_items, media_base_url)

    try:
        result = get_whatsapp_client().send_freeform(conv["recipient_phone_e164"], body, media_urls=media_urls)
    except TwilioConfigurationError as exc:
        _mark_outbound_message_send_error(message_id, None, str(exc))
        return False, str(exc)
    except TwilioMessageError as exc:
        _mark_outbound_message_send_error(message_id, None, str(exc))
        return False, f"Twilio a refusé l'envoi : {exc}"
    now = iso_utc()
    with connect() as conn:
        conn.execute(
            """
            UPDATE messages
            SET twilio_message_sid = ?,
                twilio_status = ?,
                sent_at = ?
            WHERE id = ?
            """,
            (
                result.sid,
                result.status,
                now,
                message_id,
            ),
        )
        conn.execute(
            "UPDATE conversations SET last_outbound_at = ?, updated_at = ? WHERE id = ?",
            (now, now, conversation_id),
        )
        _close_outbound_action_and_chain(
            conn,
            conv,
            user_id,
            message_id,
            now,
            action_outcome=action_outcome,
            next_due_at=next_due_at,
            assigned_to_user_id=assigned_to_user_id,
            note=note,
        )
        insert_event(
            conn,
            conv["lead_id"],
            "whatsapp_freeform_sent",
            user_id=user_id,
            new={"body": stored_body, "twilio_sid": result.sid, "attachment_count": len(attachment_items)},
        )
    if result.provider == "twilio":
        return True, "Message libre envoyé."
    return True, "Message libre envoyé en mode mock."


def send_template_message(
    conversation_id: int,
    user_id: int,
    template_id: int,
    variables: dict[str, str],
    action_outcome: str | None = None,
    next_due_at: str | None = None,
    assigned_to_user_id: int | None = None,
    note: str = "",
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    template = get_template(template_id)
    if not conv:
        return False, "Conversation introuvable."
    if not template:
        return False, "Modèle introuvable."
    if conv.get("contact_status") in STOP_CONTACT_STATUSES:
        return False, "Contact bloqué : le statut Ne plus contacter doit être levé avant tout envoi."
    if conv.get("status") == "resolved":
        return False, "Conversation terminée : réactivez-la avant tout envoi."
    with connect() as conn:
        action_kind = _active_outbound_action_kind(conn, conv["lead_id"])
        if (
            action_kind == "follow_up"
            and _has_blocked_followup(conn, conv["lead_id"])
            and not _blocked_followup_allows_template(conn, conv["lead_id"], template_id)
        ):
            return False, "Relance bloquée : le nouveau modèle doit être approuvé avant l'envoi."
    if template["status"] != "approved":
        return False, "Ce modèle n'est pas approuvé."
    if get_settings().twilio_mode == "live" and not _is_approved_real_twilio_template(template):
        return False, "Envoi live refusé : le modèle n'a pas de SID Twilio WhatsApp approuvé."
    with connect() as conn:
        ok, guard_message = _check_outbound_safeguards(conn, conv, action_kind=action_kind)
        if not ok:
            return False, guard_message

    missing = [
        item["placeholder_key"]
        for item in template["placeholders"]
        if item["required"] and not variables.get(item["placeholder_key"])
    ]
    if missing:
        return False, f"Variables manquantes: {', '.join(missing)}."

    state = calculate_window(conv["last_inbound_at"])
    body = template["body"]
    for key, value in variables.items():
        body = body.replace("{{" + key + "}}", value)

    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, sender_user_id,
                twilio_status, template_id, template_variables_json,
                whatsapp_window_state_at_send, created_at
            ) VALUES (?, ?, 'outbound', 'whatsapp_twilio', ?, ?, 'pending_send', ?, ?, ?, ?)
            """,
            (
                conversation_id,
                conv["lead_id"],
                body,
                user_id,
                template_id,
                json.dumps(variables, ensure_ascii=False),
                state.state,
                now,
            ),
        )
        message_id = int(cursor.lastrowid)

    try:
        result = get_whatsapp_client().send_template(
            conv["recipient_phone_e164"], template["twilio_content_sid"] or "HX_MOCK", variables
        )
    except TwilioConfigurationError as exc:
        _mark_outbound_message_send_error(message_id, None, str(exc))
        return False, str(exc)
    except TwilioMessageError as exc:
        _mark_outbound_message_send_error(message_id, None, str(exc))
        return False, f"Twilio a refusé l'envoi : {exc}"
    with connect() as conn:
        conn.execute(
            """
            UPDATE messages
            SET twilio_message_sid = ?,
                twilio_status = ?,
                sent_at = ?
            WHERE id = ?
            """,
            (result.sid, result.status, now, message_id),
        )
        conn.execute(
            "UPDATE conversations SET last_outbound_at = ?, updated_at = ? WHERE id = ?",
            (now, now, conversation_id),
        )
        _close_outbound_action_and_chain(
            conn,
            conv,
            user_id,
            message_id,
            now,
            action_outcome=action_outcome,
            next_due_at=next_due_at,
            assigned_to_user_id=assigned_to_user_id,
            note=note,
        )
        insert_event(
            conn,
            conv["lead_id"],
            "whatsapp_template_sent",
            user_id=user_id,
            new={"template_id": template_id, "variables": variables, "twilio_sid": result.sid},
        )
    if result.provider == "twilio":
        return True, "Modèle envoyé."
    return True, "Modèle envoyé en mode mock."


def _mark_outbound_message_send_error(
    message_id: int,
    error_code: str | None,
    error_message: str | None,
) -> None:
    now = iso_utc()
    with connect() as conn:
        conn.execute(
            """
            UPDATE messages
            SET twilio_status = 'send_error',
                twilio_error_code = ?,
                twilio_error_message = ?
            WHERE id = ?
              AND twilio_status = 'pending_send'
            """,
            (error_code, error_message, message_id),
        )
        row = row_to_dict(
            conn.execute(
                "SELECT lead_id FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        )
        if row:
            insert_event(
                conn,
                row["lead_id"],
                "whatsapp_send_failed",
                new={
                    "message_id": message_id,
                    "error_code": error_code,
                    "error_message": error_message,
                },
                metadata={"failed_at": now},
            )


def _active_outbound_action_kind(conn: Any, lead_id: int) -> str:
    action = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("reply", "follow_up"),
        include_blocked=True,
    )
    if action and action.get("type") == "follow_up":
        return "follow_up"
    return "reply"


def _check_outbound_safeguards(
    conn: Any,
    conv: dict[str, Any],
    action_kind: str = "follow_up",
) -> tuple[bool, str]:
    settings = get_outbound_safeguards()
    if settings["outbound_global_block"]:
        return False, "Envois bloqués : kill switch WhatsApp activé dans Admin."
    if action_kind != "follow_up":
        return True, ""

    now = utc_now()
    day_start = iso_utc(now.replace(hour=0, minute=0, second=0, microsecond=0))
    week_start = iso_utc(now - timedelta(days=7))
    lead_id = conv["lead_id"]

    lead_day = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM messages
        WHERE lead_id = ?
          AND direction = 'outbound'
          AND channel = 'whatsapp_twilio'
          AND sent_at >= ?
        """,
        (lead_id, day_start),
    ).fetchone()["count"]
    if int(lead_day) >= settings["outbound_max_per_lead_day"]:
        return False, "Envoi bloqué : limite quotidienne de messages atteinte pour ce prospect."

    lead_week = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM messages
        WHERE lead_id = ?
          AND direction = 'outbound'
          AND channel = 'whatsapp_twilio'
          AND sent_at >= ?
        """,
        (lead_id, week_start),
    ).fetchone()["count"]
    if int(lead_week) >= settings["outbound_max_per_lead_week"]:
        return False, "Envoi bloqué : limite hebdomadaire de messages atteinte pour ce prospect."

    global_day = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM messages
        WHERE direction = 'outbound'
          AND channel = 'whatsapp_twilio'
          AND sent_at >= ?
        """,
        (day_start,),
    ).fetchone()["count"]
    if int(global_day) >= settings["outbound_max_global_day"]:
        return False, "Envoi bloqué : limite quotidienne globale atteinte."

    active_followup = _first_active_action_for_lead(
        conn,
        lead_id,
        action_types=("follow_up",),
        include_blocked=True,
    )
    if active_followup:
        last_row = conn.execute(
            """
            SELECT MAX(sent_at) AS last_sent_at
            FROM messages
            WHERE lead_id = ?
              AND direction = 'outbound'
              AND channel = 'whatsapp_twilio'
              AND sent_at IS NOT NULL
            """,
            (lead_id,),
        ).fetchone()
        last_sent_at = last_row["last_sent_at"] if last_row else None
        last_dt = parse_dt(last_sent_at) if last_sent_at else None
        if last_dt and now - last_dt < timedelta(hours=settings["outbound_min_followup_hours"]):
            return False, "Envoi bloqué : délai minimum entre deux relances WhatsApp non respecté."

    return True, ""


def add_manual_note(
    conversation_id: int,
    user_id: int,
    body: str,
    include_in_training: bool,
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, sender_user_id, created_at
            ) VALUES (?, ?, 'manual_note', 'private_whatsapp_manual', ?, ?, ?)
            """,
            (conversation_id, conv["lead_id"], body, user_id, now),
        )
        message_id = cursor.lastrowid
        conn.execute(
            """
            INSERT INTO ai_labels (
                lead_id, conversation_id, message_id, label_type, label_value,
                created_by_user_id, include_in_training, notes
            ) VALUES (?, ?, ?, 'manual_private_whatsapp_note', 'created', ?, ?, ?)
            """,
            (
                conv["lead_id"],
                conversation_id,
                message_id,
                user_id,
                1 if include_in_training else 0,
                body,
            ),
        )
        insert_event(
            conn,
            conv["lead_id"],
            "manual_private_whatsapp_note_created",
            user_id=user_id,
            metadata={"include_in_training": include_in_training},
        )
    return True, "Note privée ajoutée."


def record_inbound_message(
    from_phone: str,
    body: str,
    lead_id: int | None = None,
    twilio_message_sid: str | None = None,
    twilio_status: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = iso_utc()
    with connect() as conn:
        if twilio_message_sid:
            duplicate = conn.execute(
                """
                SELECT id, lead_id, conversation_id
                FROM messages
                WHERE twilio_message_sid = ?
                LIMIT 1
                """,
                (twilio_message_sid,),
            ).fetchone()
            if duplicate:
                return {
                    "lead_id": duplicate["lead_id"],
                    "conversation_id": duplicate["conversation_id"],
                    "message_id": duplicate["id"],
                    "duplicate": True,
                }

        candidates: list[dict[str, Any]] = []
        identity_match_status = "explicit_lead" if lead_id is not None else "unknown"
        identity_candidate_count = 0
        if lead_id is None:
            row, candidates, identity_match_status = _select_inbound_match(conn, from_phone)
            identity_candidate_count = len(candidates)
        else:
            row = conn.execute(
                """
                SELECT l.id AS lead_id, c.id AS conversation_id, l.setter_user_id
                FROM leads l
                JOIN conversations c ON c.lead_id = l.id
                WHERE l.id = ?
                ORDER BY c.id DESC
                LIMIT 1
                """,
                (lead_id,),
            ).fetchone()

        if row:
            found = row_to_dict(row)
            lead_id = found["lead_id"]
            conversation_id = _ensure_conversation_for_lead(
                conn,
                lead_id,
                from_phone,
                now,
                found.get("conversation_id"),
            )
            setter_user_id = found.get("setter_user_id")
        else:
            setter_user_id = _default_active_user_id(conn, "setter")
            lead_id, conversation_id, _identity_status = _create_temporary_identity_lead(
                conn,
                from_phone=from_phone,
                setter_user_id=setter_user_id,
                candidates=candidates if lead_id is None else [],
                match_status=identity_match_status,
                now=now,
            )

        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body,
                twilio_message_sid, twilio_status, received_at, created_at
            ) VALUES (?, ?, 'inbound', 'whatsapp_twilio', ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                lead_id,
                body,
                twilio_message_sid,
                twilio_status or "received",
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE conversations
            SET last_inbound_at = ?, status = 'open', updated_at = ?
            WHERE id = ?
            """,
            (now, now, conversation_id),
        )
        _upsert_reply_action_for_inbound(conn, lead_id, conversation_id, setter_user_id)
        insert_event(
            conn,
            lead_id,
            "whatsapp_inbound_received",
            new={"body": body, "from_phone": from_phone},
            metadata={
                "source": "api",
                "twilio_message_sid": twilio_message_sid,
                "identity_match_status": identity_match_status,
                "identity_candidate_count": identity_candidate_count,
                "raw_payload": raw_payload or {},
            },
        )
        return {
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "message_id": cursor.lastrowid,
            "duplicate": False,
        }


_TWILIO_STATUS_PRIORITY = {
    "accepted": 10,
    "scheduled": 10,
    "queued": 20,
    "sending": 30,
    "sent": 40,
    "failed": 45,
    "undelivered": 45,
    "send_error": 45,
    "delivered": 50,
    "read": 60,
}


def _twilio_status_priority(status: str | None) -> int:
    if not status:
        return 0
    return _TWILIO_STATUS_PRIORITY.get(status.strip().lower(), 0)


def record_twilio_status_callback(
    message_sid: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_sid = message_sid.strip()
    status = status.strip().lower()
    if not message_sid:
        raise ValueError("MessageSid is required.")
    if not status:
        raise ValueError("MessageStatus is required.")

    now = iso_utc()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, lead_id, conversation_id, twilio_status
            FROM messages
            WHERE twilio_message_sid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (message_sid,),
        ).fetchone()
        if not row:
            return {"status": "unknown_message", "message_sid": message_sid}
        current_status = row["twilio_status"]
        if _twilio_status_priority(status) < _twilio_status_priority(current_status):
            insert_event(
                conn,
                row["lead_id"],
                "twilio_message_status_ignored",
                new={
                    "message_id": row["id"],
                    "message_sid": message_sid,
                    "current_status": current_status,
                    "ignored_status": status,
                    "error_code": error_code,
                    "error_message": error_message,
                },
                metadata={
                    "conversation_id": row["conversation_id"],
                    "raw_payload": raw_payload or {},
                    "ignored_at": now,
                    "reason": "status_regression",
                },
            )
            return {
                "status": "stale_status",
                "message_sid": message_sid,
                "current_status": current_status,
                "ignored_status": status,
            }
        conn.execute(
            """
            UPDATE messages
            SET twilio_status = ?, twilio_error_code = ?, twilio_error_message = ?
            WHERE id = ?
            """,
            (status, error_code, error_message, row["id"]),
        )
        insert_event(
            conn,
            row["lead_id"],
            "twilio_message_status_updated",
            new={
                "message_id": row["id"],
                "message_sid": message_sid,
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
            },
            metadata={
                "conversation_id": row["conversation_id"],
                "raw_payload": raw_payload or {},
                "updated_at": now,
            },
        )
    return {"status": "updated", "message_sid": message_sid}


def list_tasks(status: str = "open") -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if status != "all":
        filters.append("t.status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.*,
                l.schooldrive_lead_id,
                l.first_name,
                l.last_name,
                l.phone_e164,
                l.course_id,
                l.course_category_short_title,
                l.course_title,
                l.lead_type,
                l.acquisition_type,
                l.lead_status,
                l.contact_status,
                l.sales_stage,
                l.identity_status,
                l.identity_review_note,
                l.identity_candidates_json,
                u.full_name AS assigned_to_name,
                u.role AS assigned_to_role,
                u.email AS assigned_to_email,
                c.status AS conversation_status,
                c.last_inbound_at,
                c.last_outbound_at,
                last_msg.body AS last_message_body,
                last_msg.direction AS last_message_direction,
                last_msg.created_at AS last_message_at
            FROM tasks t
            JOIN leads l ON l.id = t.lead_id
            LEFT JOIN conversations c ON c.id = t.conversation_id
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
            LEFT JOIN messages last_msg ON last_msg.id = (
                SELECT m.id FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY datetime(m.created_at) DESC, m.id DESC
                LIMIT 1
            )
            {where}
            ORDER BY
                CASE t.urgency WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
                datetime(t.due_at)
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def create_call_task(
    lead_id: int,
    conversation_id: int,
    title: str,
    assigned_to_user_id: int,
    created_by_user_id: int,
    urgency: str,
    due_at: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                lead_id, conversation_id, type, title, assigned_to_user_id,
                created_by_user_id, due_at, urgency, status
            ) VALUES (?, ?, 'setting_call', ?, ?, ?, ?, ?, 'open')
            """,
            (
                lead_id,
                conversation_id,
                title,
                assigned_to_user_id,
                created_by_user_id,
                due_at or iso_utc(utc_now()),
                urgency,
            ),
        )
        insert_event(
            conn,
            lead_id,
            "call_task_created",
            user_id=created_by_user_id,
            new={"title": title, "assigned_to_user_id": assigned_to_user_id, "urgency": urgency},
        )


def complete_task(task_id: int, user_id: int, outcome: str) -> None:
    now = iso_utc()
    with connect() as conn:
        task = row_to_dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
        if not task:
            return
        conn.execute(
            """
            UPDATE tasks
            SET status = 'done', outcome = ?, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (outcome, now, now, task_id),
        )
        insert_event(
            conn,
            task["lead_id"],
            "call_task_completed",
            user_id=user_id,
            previous=task,
            new={"status": "done", "outcome": outcome},
        )


def complete_action_with_workflow(
    task_id: int,
    user_id: int,
    outcome: str,
    note: str = "",
    next_due_at: str | None = None,
    assigned_to_user_id: int | None = None,
) -> tuple[bool, str]:
    now = iso_utc()
    note = note.strip()
    with connect() as conn:
        task = row_to_dict(
            conn.execute(
                """
                SELECT
                    t.*,
                    l.first_name,
                    l.last_name,
                    l.lead_status,
                    l.contact_status,
                    l.sales_stage,
                    c.id AS conversation_id
                FROM tasks t
                JOIN leads l ON l.id = t.lead_id
                LEFT JOIN conversations c ON c.id = t.conversation_id
                WHERE t.id = ?
                """,
                (task_id,),
            ).fetchone()
        )
        if not task:
            return False, "Action introuvable."
        if task["type"] in {"setting_call", "closing_call"} and not note:
            return False, "Une mini note est obligatoire après un appel."
        if outcome == "template_missing":
            if not note:
                return False, "Explique quel modèle manque."
            cursor = conn.execute(
                """
                INSERT INTO template_requests (
                    lead_id, conversation_id, task_id, sequence_code, sequence_step_index,
                    course_id, requested_by_user_id, status, reason, context, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'to_create', ?, ?, ?, ?)
                """,
                (
                    task["lead_id"],
                    task.get("conversation_id"),
                    task_id,
                    task.get("sequence_code"),
                    task.get("sequence_step_index"),
                    user_id,
                    "Modèle manquant pour l'action",
                    note,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = 'blocked',
                    blocked_reason = 'template_missing',
                    updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
            insert_event(
                conn,
                task["lead_id"],
                "template_request_created",
                user_id=user_id,
                new={"template_request_id": int(cursor.lastrowid), "task_id": task_id},
            )
            _ensure_admin_action(
                conn,
                "template_request",
                f"Créer / lier modèle WhatsApp pour {lead_full_name(task)}",
                note,
                lead_id=task["lead_id"],
                conversation_id=task.get("conversation_id"),
                task_id=task_id,
                template_request_id=int(cursor.lastrowid),
                created_by_user_id=user_id,
                metadata={
                    "sequence_code": task.get("sequence_code"),
                    "sequence_step_index": task.get("sequence_step_index"),
                    "reason": "Modèle manquant pour l'action",
                },
            )
            return True, "Action bloquée en attente d'un nouveau modèle."

        conn.execute(
            """
            UPDATE tasks
            SET status = 'done',
                outcome = ?,
                completed_at = ?,
                updated_at = ?,
                metadata_json = ?
            WHERE id = ?
            """,
            (
                outcome,
                now,
                now,
                json.dumps({"completion_note": note}, ensure_ascii=False),
                task_id,
            ),
        )
        insert_event(
            conn,
            task["lead_id"],
            "action_completed_with_workflow",
            user_id=user_id,
            previous={"task_id": task_id, "type": task["type"]},
            new={"outcome": outcome, "note": note},
        )

        full_name = lead_full_name(task)
        conversation_id = task.get("conversation_id")
        if note and conversation_id:
            action_note_labels = {
                "reply": "Note de réponse",
                "follow_up": "Note de relance",
                "setting_call": "Note d'appel setting",
                "closing_call": "Note d'appel closing",
                "contact_review": "Note de revue contact",
                "other": "Note d'action",
            }
            action_note_label = action_note_labels.get(task["type"], "Note d'action")
            _insert_internal_note_message(
                conn,
                task["lead_id"],
                conversation_id,
                user_id,
                f"{action_note_label} : {note}",
                now,
            )

        def create_followup(
            sequence_code: str,
            due_at: str,
            step_index: int = 1,
            trigger_reason: str = "workflow_outcome",
            sequence_anchor_at: str | None = None,
            sequence_anchor_label: str | None = None,
        ) -> int | None:
            assignee_id = setter2_user_id(conn) or assigned_to_user_id or user_id
            if not conversation_id:
                return None
            metadata = (
                _sequence_anchor_metadata(sequence_anchor_at, sequence_anchor_label)
                if sequence_anchor_at
                else None
            )
            return _insert_next_action(
                conn,
                lead_id=task["lead_id"],
                conversation_id=conversation_id,
                action_type="follow_up",
                title=f"Relancer {full_name}",
                assigned_to_user_id=assignee_id,
                created_by_user_id=user_id,
                urgency="normal",
                due_at=due_at,
                description=note or None,
                trigger_reason=trigger_reason,
                sequence_code=sequence_code,
                sequence_step_index=step_index,
                previous_action_id=task_id,
                metadata=metadata,
            )

        def resolve(reason: str) -> None:
            if reason == "do_not_contact":
                conn.execute(
                    "UPDATE leads SET contact_status = 'do_not_contact', updated_at = ? WHERE id = ?",
                    (now, task["lead_id"]),
                )
            elif reason in {"not_relevant", "signed"}:
                conn.execute(
                    "UPDATE leads SET lead_status = ?, updated_at = ? WHERE id = ?",
                    (reason, now, task["lead_id"]),
                )
            _complete_open_actions_for_lead(
                conn,
                task["lead_id"],
                user_id,
                outcome=f"Statut terminal : {reason}",
            )
            conn.execute(
                """
                UPDATE conversations
                SET status = 'resolved',
                    resolution_reason = ?,
                    resolution_note = ?,
                    resolved_at = ?,
                    updated_at = ?
                WHERE lead_id = ?
                """,
                (reason, note or None, now, now, task["lead_id"]),
            )

        next_action_id = None
        if task["type"] == "reply":
            if outcome == "reply_no_appointment":
                active_call = _first_active_action_for_lead(
                    conn,
                    task["lead_id"],
                    action_types=("setting_call", "closing_call"),
                )
                if active_call:
                    insert_event(
                        conn,
                        task["lead_id"],
                        "reply_completed_planned_call_kept",
                        user_id=user_id,
                        previous={"reply_task_id": task_id},
                        new={
                            "kept_call_task_id": active_call["id"],
                            "kept_call_type": active_call["type"],
                        },
                        metadata={"conversation_id": conversation_id},
                    )
                    return True, "Action terminée. L'appel déjà planifié reste actif."
                first_step = _get_sequence_step(conn, "setter_no_next_step", 1)
                if not first_step:
                    return False, "Étape de relance introuvable."
                next_action_id = create_followup(
                    "setter_no_next_step",
                    _due_for_sequence_step(now, first_step),
                    trigger_reason="reply_sent_no_setting_booked",
                    sequence_anchor_at=now,
                    sequence_anchor_label="Réponse setter sans rendez-vous",
                )
            elif outcome == "setting_booked":
                if not conversation_id:
                    return False, "Conversation introuvable pour créer l'appel."
                assignee_id = (
                    assigned_to_user_id
                    if _is_setter1_user(conn, assigned_to_user_id)
                    else setter1_user_id(conn)
                ) or task.get("assigned_to_user_id") or user_id
                _complete_open_actions_for_lead(
                    conn,
                    task["lead_id"],
                    user_id,
                    outcome="Appel setting remplacé",
                    included_types=("setting_call",),
                )
                next_action_id = _insert_next_action(
                    conn,
                    lead_id=task["lead_id"],
                    conversation_id=conversation_id,
                    action_type="setting_call",
                    title=f"Documenter l'appel setting de {full_name}",
                    assigned_to_user_id=assignee_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note or None,
                    trigger_reason="setting_appointment_booked",
                    previous_action_id=task_id,
                    call_cycle_id=str(uuid4()),
                    call_attempt_index=1,
                )
            elif outcome == "closing_booked":
                closer_id = assigned_to_user_id or default_closer_user_id(conn)
                if not closer_id or not conversation_id:
                    return False, "Closer ou conversation introuvable."
                _complete_open_actions_for_lead(
                    conn,
                    task["lead_id"],
                    user_id,
                    outcome="Appel closing remplacé",
                    included_types=("closing_call",),
                )
                conn.execute(
                    """
                    UPDATE leads
                    SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'eligible', updated_at = ?
                    WHERE id = ?
                    """,
                    (closer_id, now, task["lead_id"]),
                )
                next_action_id = _insert_next_action(
                    conn,
                    lead_id=task["lead_id"],
                    conversation_id=conversation_id,
                    action_type="closing_call",
                    title=f"Documenter l'appel closing de {full_name}",
                    assigned_to_user_id=closer_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note or None,
                    trigger_reason="closing_appointment_booked_from_reply",
                    previous_action_id=task_id,
                    call_cycle_id=str(uuid4()),
                    call_attempt_index=1,
                )
            elif outcome in {"not_relevant", "do_not_contact"}:
                resolve(outcome)

        elif task["type"] == "setting_call":
            if outcome == "to_closing":
                closer_id = assigned_to_user_id or default_closer_user_id(conn)
                if not closer_id or not conversation_id:
                    return False, "Closer ou conversation introuvable."
                conn.execute(
                    """
                    UPDATE leads
                    SET closer_user_id = ?, sales_stage = 'closing', updated_at = ?
                    WHERE id = ?
                    """,
                    (closer_id, now, task["lead_id"]),
                )
                next_action_id = _insert_next_action(
                    conn,
                    lead_id=task["lead_id"],
                    conversation_id=conversation_id,
                    action_type="closing_call",
                    title=f"Documenter l'appel closing de {full_name}",
                    assigned_to_user_id=closer_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note,
                    trigger_reason="setting_call_to_closing",
                    previous_action_id=task_id,
                    call_cycle_id=str(uuid4()),
                    call_attempt_index=1,
                )
            elif outcome == "not_reached":
                anchor = _sequence_anchor_from_action(task, task.get("due_at") or now)
                cycle_id = task.get("call_cycle_id") or str(uuid4())
                attempt_index = int(task.get("call_attempt_index") or 1)
                conn.execute(
                    """
                    UPDATE tasks
                    SET call_cycle_id = coalesce(call_cycle_id, ?),
                        call_attempt_index = coalesce(call_attempt_index, ?)
                    WHERE id = ?
                    """,
                    (cycle_id, attempt_index, task_id),
                )
                count = _count_completed_call_outcomes(
                    conn, task["lead_id"], "setting_call", "not_reached", cycle_id
                )
                if count <= 1 and conversation_id:
                    step = _get_sequence_step(conn, "setting_call_not_reached", 1)
                    if not step:
                        return False, "Étape de rappel setting introuvable."
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="setting_call",
                        title=f"Documenter le rappel setting de {full_name}",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_for_call_retry_step(anchor, step, "setter1"),
                        description=note,
                        trigger_reason="setting_call_not_reached",
                        sequence_code="setting_call_not_reached",
                        sequence_step_index=1,
                        previous_action_id=task_id,
                        metadata=_sequence_anchor_metadata(anchor, "Appel setting non joint"),
                        call_cycle_id=cycle_id,
                        call_attempt_index=2,
                    )
                elif count <= 2 and conversation_id:
                    step = _get_sequence_step(conn, "setting_call_not_reached", 2)
                    if not step:
                        return False, "Étape de rappel setting introuvable."
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="setting_call",
                        title=f"Documenter le rappel setting de {full_name}",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_for_call_retry_step(anchor, step, "setter1"),
                        description=note,
                        trigger_reason="setting_call_not_reached",
                        sequence_code="setting_call_not_reached",
                        sequence_step_index=2,
                        previous_action_id=task_id,
                        metadata=_sequence_anchor_metadata(anchor, "Appel setting non joint"),
                        call_cycle_id=cycle_id,
                        call_attempt_index=3,
                    )
                else:
                    step = _get_sequence_step(conn, "setting_call_not_reached", 3)
                    if not step:
                        return False, "Étape de relance setting introuvable."
                    next_action_id = create_followup(
                        "setting_call_not_reached",
                        _due_for_sequence_step(anchor, step),
                        step_index=3,
                        trigger_reason="setting_call_not_reached_retries_exhausted",
                        sequence_anchor_at=anchor,
                        sequence_anchor_label="Appel setting non joint",
                    )
            elif outcome == "not_ready":
                first_step = _get_sequence_step(conn, "post_setting_undecided", 1)
                if not first_step:
                    return False, "Étape de relance post-setting introuvable."
                next_action_id = create_followup(
                    "post_setting_undecided",
                    _due_for_sequence_step(now, first_step),
                    trigger_reason="setting_call_undecided",
                    sequence_anchor_at=now,
                    sequence_anchor_label="Appel setting indécis",
                )
            elif outcome in {"not_relevant", "do_not_contact"}:
                resolve(outcome)

        elif task["type"] == "closing_call":
            if outcome == "signed":
                resolve("signed")
            elif outcome == "will_sign":
                conn.execute(
                    "UPDATE leads SET lead_status = 'will_sign', updated_at = ? WHERE id = ?",
                    (now, task["lead_id"]),
                )
                first_step = _get_sequence_step(conn, "closer_will_sign", 1)
                if not first_step:
                    return False, "Étape de relance Va signer introuvable."
                next_action_id = create_followup(
                    "closer_will_sign",
                    _due_for_sequence_step(now, first_step),
                    trigger_reason="closing_call_will_sign",
                    sequence_anchor_at=now,
                    sequence_anchor_label="Closing qualifié Va signer",
                )
            elif outcome == "not_reached":
                anchor = _sequence_anchor_from_action(task, task.get("due_at") or now)
                cycle_id = task.get("call_cycle_id") or str(uuid4())
                attempt_index = int(task.get("call_attempt_index") or 1)
                conn.execute(
                    """
                    UPDATE tasks
                    SET call_cycle_id = coalesce(call_cycle_id, ?),
                        call_attempt_index = coalesce(call_attempt_index, ?)
                    WHERE id = ?
                    """,
                    (cycle_id, attempt_index, task_id),
                )
                count = _count_completed_call_outcomes(
                    conn, task["lead_id"], "closing_call", "not_reached", cycle_id
                )
                if count <= 1 and conversation_id:
                    step = _get_sequence_step(conn, "closing_call_not_reached", 1)
                    if not step:
                        return False, "Étape de rappel closing introuvable."
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="closing_call",
                        title=f"Documenter le rappel closing de {full_name}",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_for_call_retry_step(anchor, step, "closer"),
                        description=note,
                        trigger_reason="closing_call_not_reached",
                        sequence_code="closing_call_not_reached",
                        sequence_step_index=1,
                        previous_action_id=task_id,
                        metadata=_sequence_anchor_metadata(anchor, "Appel closing non joint"),
                        call_cycle_id=cycle_id,
                        call_attempt_index=2,
                    )
                elif count <= 2 and conversation_id:
                    step = _get_sequence_step(conn, "closing_call_not_reached", 2)
                    if not step:
                        return False, "Étape de rappel closing introuvable."
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="closing_call",
                        title=f"Documenter le rappel closing de {full_name}",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_for_call_retry_step(anchor, step, "closer"),
                        description=note,
                        trigger_reason="closing_call_not_reached",
                        sequence_code="closing_call_not_reached",
                        sequence_step_index=2,
                        previous_action_id=task_id,
                        metadata=_sequence_anchor_metadata(anchor, "Appel closing non joint"),
                        call_cycle_id=cycle_id,
                        call_attempt_index=3,
                    )
                else:
                    step = _get_sequence_step(conn, "closing_call_not_reached", 3)
                    if not step:
                        return False, "Étape de relance closing introuvable."
                    next_action_id = create_followup(
                        "closing_call_not_reached",
                        _due_for_sequence_step(anchor, step),
                        step_index=3,
                        trigger_reason="closing_call_not_reached_retries_exhausted",
                        sequence_anchor_at=anchor,
                        sequence_anchor_label="Appel closing non joint",
                    )
            elif outcome == "undecided":
                first_step = _get_sequence_step(conn, "post_closing_undecided", 1)
                if not first_step:
                    return False, "Étape de relance post-appel introuvable."
                next_action_id = create_followup(
                    "post_closing_undecided",
                    _due_for_sequence_step(now, first_step),
                    trigger_reason="closing_call_undecided",
                    sequence_anchor_at=now,
                    sequence_anchor_label="Closing indécis",
                )
            elif outcome in {"not_relevant", "do_not_contact"}:
                resolve(outcome)

        elif task["type"] == "follow_up":
            if outcome == "sequence_completed_no_reply":
                resolve("sequence_completed_no_reply")
            elif outcome == "follow_up_sent":
                next_step = _next_sequence_step(
                    conn,
                    task.get("sequence_code"),
                    task.get("sequence_step_index"),
                )
                if next_step:
                    anchor = _sequence_anchor_from_action(task, now)
                    next_action_id = create_followup(
                        next_step["sequence_code"],
                        _due_for_sequence_step(anchor, next_step),
                        step_index=next_step["step_index"],
                        trigger_reason="follow_up_sequence_continues",
                        sequence_anchor_at=anchor,
                    )
                else:
                    resolve("sequence_completed_no_reply")

        elif task["type"] == "contact_review":
            if outcome == "maintain_do_not_contact":
                resolve("do_not_contact")
            elif outcome == "lift_do_not_contact":
                conn.execute(
                    """
                    UPDATE leads
                    SET contact_status = 'contact_allowed', updated_at = ?
                    WHERE id = ?
                    """,
                    (now, task["lead_id"]),
                )
                if conversation_id:
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="reply",
                        title=f"Répondre à {full_name}",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="urgent",
                        due_at=now,
                        description=note,
                        trigger_reason="do_not_contact_lifted_after_inbound",
                        previous_action_id=task_id,
                    )

        if next_action_id:
            conn.execute(
                "UPDATE tasks SET next_action_id = ? WHERE id = ?",
                (next_action_id, task_id),
            )
            insert_event(
                conn,
                task["lead_id"],
                "next_action_created_by_workflow",
                user_id=user_id,
                previous={"task_id": task_id, "outcome": outcome},
                new={"task_id": next_action_id},
            )
    return True, "Action terminée et suite créée selon la règle métier."


def _count_completed_outcomes(
    conn: Any,
    lead_id: int,
    action_type: str,
    outcome: str,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM tasks
        WHERE lead_id = ?
          AND type = ?
          AND outcome = ?
          AND status = 'done'
        """,
        (lead_id, action_type, outcome),
    ).fetchone()
    return int(row["count"] if row else 0)


def _count_completed_call_outcomes(
    conn: Any,
    lead_id: int,
    action_type: str,
    outcome: str,
    call_cycle_id: str,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM tasks
        WHERE lead_id = ?
          AND type = ?
          AND outcome = ?
          AND status = 'done'
          AND call_cycle_id = ?
        """,
        (lead_id, action_type, outcome, call_cycle_id),
    ).fetchone()
    return int(row["count"] if row else 0)
