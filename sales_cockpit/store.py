from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sales_cockpit.business_rules import (
    RESOLUTION_REASONS,
    STOP_CONTACT_STATUSES,
    STOP_QUALIFICATION_STATUSES,
)
from sales_cockpit.db import connect, init_db, insert_event, row_to_dict, rows_to_dicts
from sales_cockpit.security import verify_password
from sales_cockpit.services.mock_twilio import MockTwilioClient
from sales_cockpit.services.whatsapp_rules import calculate_window, iso_utc, parse_dt, utc_now


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


def followups_are_blocked(record: dict[str, Any]) -> bool:
    return (
        record.get("lead_status") in STOP_QUALIFICATION_STATUSES
        or record.get("contact_status") in STOP_CONTACT_STATUSES
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

    query = f"""
        SELECT
            c.id AS conversation_id,
            l.id AS lead_id,
            l.schooldrive_lead_id,
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
                CASE WHEN t.due_at IS NULL THEN 1 ELSE 0 END,
                datetime(t.due_at) ASC,
                CASE t.urgency WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END,
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
            "setting_call": f"Appeler {full_name} pour setting",
            "closing_call": f"Appeler {full_name} pour closing",
        }
        trigger_reasons = {
            "reply": "standard_reply_assigned",
            "follow_up": "standard_followup_scheduled",
            "setting_call": "standard_setting_call_scheduled",
            "closing_call": "standard_closing_call_scheduled",
        }

        _complete_open_actions_for_lead(
            conn,
            conv["lead_id"],
            user_id,
            outcome=f"Action remplacée par {action_type}",
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
                    lead_status = 'neutral',
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
            SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'neutral', updated_at = ?
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
            title=f"Contacter {full_name} pour closing",
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
                "lead_status": "neutral",
                "closer_user_id": closer_user_id,
                "task_id": action_id,
                "appointment_note": appointment_note,
                "notes": notes,
            },
        )
    return True, f"Passage au closer créé pour {closer['full_name']}."


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
                "setting_call": "Appeler",
                "closing_call": "Contacter pour closing",
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

    label = "rouverte" if status == "open" else "marquée comme résolue"
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
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO tasks (
            lead_id, conversation_id, type, title, description, assigned_to_user_id,
            created_by_user_id, due_at, urgency, status, trigger_reason, sequence_code,
            sequence_step_index, previous_action_id, blocked_reason, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid)


def _complete_open_actions_for_lead(
    conn: Any,
    lead_id: int,
    user_id: int | None,
    outcome: str,
    excluded_types: tuple[str, ...] = (),
) -> None:
    params: list[Any] = [lead_id]
    exclusion = ""
    if excluded_types:
        placeholders = ", ".join("?" for _ in excluded_types)
        exclusion = f" AND type NOT IN ({placeholders})"
        params.extend(excluded_types)

    rows = conn.execute(
        f"""
        SELECT id FROM tasks
        WHERE lead_id = ? AND status IN ('open', 'in_progress', 'planned', 'blocked'){exclusion}
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
) -> dict[str, Any] | None:
    statuses = "('open', 'in_progress', 'planned', 'blocked')" if include_blocked else "('open', 'in_progress', 'planned')"
    filters = ["lead_id = ?", f"status IN {statuses}"]
    params: list[Any] = [lead_id]
    if action_types:
        placeholders = ", ".join("?" for _ in action_types)
        filters.append(f"type IN ({placeholders})")
        params.extend(action_types)
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


def _next_sequence_step(
    conn: Any,
    sequence_code: str | None,
    current_step_index: int | None,
) -> dict[str, Any] | None:
    if not sequence_code:
        return None
    next_index = (current_step_index or 0) + 1
    return row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM sequence_steps
            WHERE sequence_code = ? AND step_index = ? AND active = 1
            """,
            (sequence_code, next_index),
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
        include_blocked=False,
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
            next_action_id = _insert_next_action(
                conn,
                lead_id=conv["lead_id"],
                conversation_id=conv["id"],
                action_type="setting_call",
                title=f"Appeler {full_name} pour setting",
                assigned_to_user_id=assignee_id,
                created_by_user_id=user_id,
                urgency="high",
                due_at=next_due_at or sent_at,
                description=note or None,
                trigger_reason="setting_appointment_booked",
                previous_action_id=action["id"],
            )
            conn.execute("UPDATE tasks SET next_action_id = ? WHERE id = ?", (next_action_id, action["id"]))
            return

        if action_outcome == "closing_booked":
            closer_id = assigned_to_user_id or default_closer_user_id(conn)
            if not closer_id:
                return
            conn.execute(
                """
                UPDATE leads
                SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'neutral', updated_at = ?
                WHERE id = ?
                """,
                (closer_id, sent_at, conv["lead_id"]),
            )
            next_action_id = _insert_next_action(
                conn,
                lead_id=conv["lead_id"],
                conversation_id=conv["id"],
                action_type="closing_call",
                title=f"Contacter {full_name} pour closing",
                assigned_to_user_id=closer_id,
                created_by_user_id=user_id,
                urgency="high",
                due_at=next_due_at or sent_at,
                description=note or None,
                trigger_reason="closing_appointment_booked_from_reply",
                previous_action_id=action["id"],
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
            due_at=_due_after(sent_at, "+72h"),
            trigger_reason="reply_sent_no_setting_booked",
            sequence_code="setter_no_next_step",
            sequence_step_index=1,
            previous_action_id=action["id"],
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
            due_at=_due_after(sent_at, next_step["delay"]),
            trigger_reason="follow_up_sequence_continues",
            sequence_code=next_step["sequence_code"],
            sequence_step_index=next_step["step_index"],
            previous_action_id=action["id"],
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
        excluded_types=(
            ("contact_review",)
            if lead.get("contact_status") in STOP_CONTACT_STATUSES
            else ("reply",)
        ),
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
    return rows_to_dicts(rows)


def list_templates(search: str = "", approved_only: bool = False) -> list[dict[str, Any]]:
    filters = []
    params: list[Any] = []
    if approved_only:
        filters.append("status = 'approved'")
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


def create_template(
    user_id: int,
    name: str,
    body: str,
    status: str = "draft",
    language: str = "fr",
    category: str = "utility",
    placeholders: dict[str, str] | None = None,
) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO whatsapp_templates (name, language, category, body, status, created_by_user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, language, category, body, status, user_id),
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


def list_sequence_steps(sequence_code: str | None = None) -> list[dict[str, Any]]:
    filters = ["active = 1"]
    params: list[Any] = []
    if sequence_code:
        filters.append("sequence_code = ?")
        params.append(sequence_code)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM sequence_steps
            WHERE {' AND '.join(filters)}
            ORDER BY sequence_code, step_index
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


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
                    blocked_reason = NULL,
                    updated_at = ?
                WHERE id = ? AND status = 'blocked'
                """,
                (now, request["task_id"]),
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
        lead_status = "neutral"
    if lead_status == "do_not_contact":
        contact_status = "do_not_contact"
        lead_status = "neutral"
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
        title = f"Contacter {full_name} pour closing"
        urgency = "high"
    elif sales_stage == "appointment_booked":
        target_type = "setting_call"
        assignee_id = row.get("setter_user_id") or _default_active_user_id(conn, "setter")
        title = f"Appeler {full_name} pour setting"
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


def send_freeform_message(
    conversation_id: int,
    user_id: int,
    body: str,
    action_outcome: str | None = None,
    next_due_at: str | None = None,
    assigned_to_user_id: int | None = None,
    note: str = "",
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    if conv.get("contact_status") in STOP_CONTACT_STATUSES:
        return False, "Contact bloqué : le statut Ne plus contacter doit être levé avant tout envoi."
    if conv.get("status") == "resolved":
        return False, "Conversation terminée : réactivez-la avant tout envoi."
    with connect() as conn:
        if _has_blocked_followup(conn, conv["lead_id"]):
            return False, "Relance bloquée : le nouveau modèle doit être approuvé avant l'envoi."
    state = calculate_window(conv["last_inbound_at"])
    if not state.is_open:
        return False, "Fenêtre WhatsApp fermée. Utilisez un modèle approuvé."

    result = MockTwilioClient().send_freeform(conv["recipient_phone_e164"], body)
    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, sender_user_id,
                twilio_message_sid, twilio_status, whatsapp_window_state_at_send,
                sent_at, created_at
            ) VALUES (?, ?, 'outbound', 'whatsapp_twilio', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                conv["lead_id"],
                body,
                user_id,
                result.sid,
                result.status,
                state.state,
                now,
                now,
            ),
        )
        message_id = int(cursor.lastrowid)
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
            new={"body": body, "twilio_sid": result.sid},
        )
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
        if _has_blocked_followup(conn, conv["lead_id"]):
            return False, "Relance bloquée : le nouveau modèle doit être approuvé avant l'envoi."
    if template["status"] != "approved":
        return False, "Ce modèle n'est pas approuvé."

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

    result = MockTwilioClient().send_template(
        conv["recipient_phone_e164"], template["twilio_content_sid"] or "HX_MOCK", variables
    )
    now = iso_utc()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, sender_user_id,
                twilio_message_sid, twilio_status, template_id, template_variables_json,
                whatsapp_window_state_at_send, sent_at, created_at
            ) VALUES (?, ?, 'outbound', 'whatsapp_twilio', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                conv["lead_id"],
                body,
                user_id,
                result.sid,
                result.status,
                template_id,
                json.dumps(variables, ensure_ascii=False),
                state.state,
                now,
                now,
            ),
        )
        message_id = int(cursor.lastrowid)
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
    return True, "Modèle envoyé en mode mock."


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
) -> dict[str, Any]:
    now = iso_utc()
    with connect() as conn:
        if lead_id is None:
            row = conn.execute(
                """
                SELECT l.id AS lead_id, c.id AS conversation_id, l.setter_user_id
                FROM leads l
                JOIN conversations c ON c.lead_id = l.id
                WHERE l.phone_e164 = ? OR c.recipient_phone_e164 = ?
                ORDER BY c.id DESC
                LIMIT 1
                """,
                (from_phone, from_phone),
            ).fetchone()
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
            conversation_id = found["conversation_id"]
            setter_user_id = found.get("setter_user_id")
        else:
            setter_user_id = _default_active_user_id(conn, "setter")
            cursor = conn.execute(
                """
                INSERT INTO leads (
                    first_name, last_name, phone_e164, phone_raw, source,
                    acquisition_type, lead_status, contact_status, sales_stage,
                    temperature, setter_user_id
                ) VALUES ('Inconnu(e)', '', ?, ?, 'twilio_webhook_mock',
                    'unknown', 'neutral', 'contact_allowed', 'new', 'warm', ?)
                """,
                (from_phone, from_phone, setter_user_id),
            )
            lead_id = cursor.lastrowid
            conversation_id = conn.execute(
                """
                INSERT INTO conversations (lead_id, recipient_phone_e164, last_inbound_at)
                VALUES (?, ?, ?)
                """,
                (lead_id, from_phone, now),
            ).lastrowid

        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body, received_at, created_at
            ) VALUES (?, ?, 'inbound', 'whatsapp_twilio', ?, ?, ?)
            """,
            (conversation_id, lead_id, body, now, now),
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
            metadata={"source": "api"},
        )
        return {
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "message_id": cursor.lastrowid,
        }


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
        ) -> int | None:
            assignee_id = setter2_user_id(conn) or assigned_to_user_id or user_id
            if not conversation_id:
                return None
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
                next_action_id = create_followup(
                    "setter_no_next_step",
                    _due_after(now, "+72h"),
                    trigger_reason="reply_sent_no_setting_booked",
                )
            elif outcome == "setting_booked":
                if not conversation_id:
                    return False, "Conversation introuvable pour créer l'appel."
                assignee_id = (
                    assigned_to_user_id
                    if _is_setter1_user(conn, assigned_to_user_id)
                    else setter1_user_id(conn)
                ) or task.get("assigned_to_user_id") or user_id
                next_action_id = _insert_next_action(
                    conn,
                    lead_id=task["lead_id"],
                    conversation_id=conversation_id,
                    action_type="setting_call",
                    title=f"Appeler {full_name} pour setting",
                    assigned_to_user_id=assignee_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note or None,
                    trigger_reason="setting_appointment_booked",
                    previous_action_id=task_id,
                )
            elif outcome == "closing_booked":
                closer_id = assigned_to_user_id or default_closer_user_id(conn)
                if not closer_id or not conversation_id:
                    return False, "Closer ou conversation introuvable."
                conn.execute(
                    """
                    UPDATE leads
                    SET closer_user_id = ?, sales_stage = 'closing', lead_status = 'neutral', updated_at = ?
                    WHERE id = ?
                    """,
                    (closer_id, now, task["lead_id"]),
                )
                next_action_id = _insert_next_action(
                    conn,
                    lead_id=task["lead_id"],
                    conversation_id=conversation_id,
                    action_type="closing_call",
                    title=f"Contacter {full_name} pour closing",
                    assigned_to_user_id=closer_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note or None,
                    trigger_reason="closing_appointment_booked_from_reply",
                    previous_action_id=task_id,
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
                    title=f"Contacter {full_name} pour closing",
                    assigned_to_user_id=closer_id,
                    created_by_user_id=user_id,
                    urgency="high",
                    due_at=next_due_at or now,
                    description=note,
                    trigger_reason="setting_call_to_closing",
                    previous_action_id=task_id,
                )
            elif outcome == "not_reached":
                count = _count_completed_outcomes(conn, task["lead_id"], "setting_call", "not_reached")
                if count <= 1 and conversation_id:
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="setting_call",
                        title=f"Rappeler {full_name} pour setting",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_after(now, "+2h"),
                        description=note,
                        trigger_reason="setting_call_not_reached",
                        sequence_code="setting_call_not_reached",
                        sequence_step_index=1,
                        previous_action_id=task_id,
                    )
                elif count <= 2 and conversation_id:
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="setting_call",
                        title=f"Rappeler {full_name} pour setting",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_after(now, "+24h"),
                        description=note,
                        trigger_reason="setting_call_not_reached",
                        sequence_code="setting_call_not_reached",
                        sequence_step_index=2,
                        previous_action_id=task_id,
                    )
                else:
                    next_action_id = create_followup(
                        "setting_call_not_reached",
                        _due_after(now, "+72h"),
                        step_index=3,
                        trigger_reason="setting_call_not_reached_retries_exhausted",
                    )
            elif outcome == "not_ready":
                next_action_id = create_followup(
                    "setter_no_next_step",
                    _due_after(now, "+72h"),
                    trigger_reason="setting_call_no_next_step",
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
                next_action_id = create_followup(
                    "closer_will_sign",
                    _due_after(now, "+72h"),
                    trigger_reason="closing_call_will_sign",
                )
            elif outcome == "not_reached":
                count = _count_completed_outcomes(conn, task["lead_id"], "closing_call", "not_reached")
                if count <= 1 and conversation_id:
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="closing_call",
                        title=f"Rappeler {full_name} pour closing",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_after(now, "+2h"),
                        description=note,
                        trigger_reason="closing_call_not_reached",
                        sequence_code="closing_call_not_reached",
                        sequence_step_index=1,
                        previous_action_id=task_id,
                    )
                elif count <= 2 and conversation_id:
                    next_action_id = _insert_next_action(
                        conn,
                        lead_id=task["lead_id"],
                        conversation_id=conversation_id,
                        action_type="closing_call",
                        title=f"Rappeler {full_name} pour closing",
                        assigned_to_user_id=task["assigned_to_user_id"] or user_id,
                        created_by_user_id=user_id,
                        urgency="high",
                        due_at=_due_after(now, "+24h"),
                        description=note,
                        trigger_reason="closing_call_not_reached",
                        sequence_code="closing_call_not_reached",
                        sequence_step_index=2,
                        previous_action_id=task_id,
                    )
                else:
                    next_action_id = create_followup(
                        "closing_call_not_reached",
                        _due_after(now, "+72h"),
                        step_index=3,
                        trigger_reason="closing_call_not_reached_retries_exhausted",
                    )
            elif outcome == "undecided":
                next_action_id = create_followup(
                    "post_call_undecided",
                    _due_after(now, "+72h"),
                    trigger_reason="closing_call_undecided",
                )
            elif outcome == "not_relevant":
                resolve("not_relevant")

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
                    next_action_id = create_followup(
                        next_step["sequence_code"],
                        _due_after(now, next_step["delay"]),
                        step_index=next_step["step_index"],
                        trigger_reason="follow_up_sequence_continues",
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
