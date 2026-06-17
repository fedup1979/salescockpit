from __future__ import annotations

import json
from typing import Any

from sales_cockpit.db import connect, init_db, insert_event, row_to_dict, rows_to_dicts
from sales_cockpit.security import verify_password
from sales_cockpit.services.mock_twilio import MockTwilioClient
from sales_cockpit.services.whatsapp_rules import calculate_window, iso_utc, utc_now


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
    user.pop("password_hash", None)
    return user


def list_users(active_only: bool = True) -> list[dict[str, Any]]:
    query = "SELECT id, email, full_name, role, active FROM users"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY role, full_name"
    with connect() as conn:
        rows = conn.execute(query).fetchall()
    return rows_to_dicts(rows)


def list_conversations(search: str = "", stage: str = "all") -> list[dict[str, Any]]:
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
                OR lower(coalesce(l.course_title, '')) LIKE ?
                OR lower(coalesce(last_msg.body, '')) LIKE ?
            )
            """
        )
        params.extend([like, like, like, like, like])
    if stage != "all":
        filters.append("l.sales_stage = ?")
        params.append(stage)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    query = f"""
        SELECT
            c.id AS conversation_id,
            l.id AS lead_id,
            l.first_name,
            l.last_name,
            l.email,
            l.phone_e164,
            l.course_title,
            l.lead_status,
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
            (
                SELECT COUNT(*) FROM tasks t
                WHERE t.lead_id = l.id AND t.status IN ('open', 'in_progress')
            ) AS open_tasks
        FROM conversations c
        JOIN leads l ON l.id = c.lead_id
        LEFT JOIN users setter ON setter.id = l.setter_user_id
        LEFT JOIN users closer ON closer.id = l.closer_user_id
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
        conv["window_closes_at"] = iso_utc(state.closes_at) if state.closes_at else None
    return conversations


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
                l.course_title,
                l.lead_status,
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


def set_conversation_status(
    conversation_id: int, user_id: int, status: str
) -> tuple[bool, str]:
    if status not in {"open", "resolved"}:
        return False, "Statut de conversation invalide."
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    previous_status = conv["status"]
    if previous_status == status:
        return True, "La conversation a déjà ce statut."

    now = iso_utc()
    with connect() as conn:
        conn.execute(
            "UPDATE conversations SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, conversation_id),
        )
        insert_event(
            conn,
            conv["lead_id"],
            "conversation_status_changed",
            user_id=user_id,
            previous={"status": previous_status},
            new={"status": status},
            metadata={"conversation_id": conversation_id},
        )

    label = "rouverte" if status == "open" else "marquée comme résolue"
    return True, f"Conversation {label}."


def list_messages(conversation_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.*, u.full_name AS sender_name, wt.name AS template_name
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
    return int(template_id)


def update_lead_qualification(
    lead_id: int,
    user_id: int,
    sales_stage: str,
    temperature: str,
    lead_status: str,
) -> None:
    with connect() as conn:
        previous = row_to_dict(
            conn.execute(
                "SELECT sales_stage, temperature, lead_status FROM leads WHERE id = ?",
                (lead_id,),
            ).fetchone()
        )
        conn.execute(
            """
            UPDATE leads
            SET sales_stage = ?, temperature = ?, lead_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (sales_stage, temperature, lead_status, iso_utc(), lead_id),
        )
        insert_event(
            conn,
            lead_id,
            "lead_qualification_updated",
            user_id=user_id,
            previous=previous,
            new={
                "sales_stage": sales_stage,
                "temperature": temperature,
                "lead_status": lead_status,
            },
        )


def send_freeform_message(conversation_id: int, user_id: int, body: str) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    if not conv:
        return False, "Conversation introuvable."
    state = calculate_window(conv["last_inbound_at"])
    if not state.is_open:
        return False, "Fenêtre WhatsApp fermée. Utilise un modèle approuvé."

    result = MockTwilioClient().send_freeform(conv["recipient_phone_e164"], body)
    now = iso_utc()
    with connect() as conn:
        conn.execute(
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
        conn.execute(
            "UPDATE conversations SET last_outbound_at = ?, updated_at = ? WHERE id = ?",
            (now, now, conversation_id),
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
    conversation_id: int, user_id: int, template_id: int, variables: dict[str, str]
) -> tuple[bool, str]:
    conv = get_conversation(conversation_id)
    template = get_template(template_id)
    if not conv:
        return False, "Conversation introuvable."
    if not template:
        return False, "Modèle introuvable."
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
        conn.execute(
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
        conn.execute(
            "UPDATE conversations SET last_outbound_at = ?, updated_at = ? WHERE id = ?",
            (now, now, conversation_id),
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
                SELECT l.id AS lead_id, c.id AS conversation_id
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
                SELECT l.id AS lead_id, c.id AS conversation_id
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
        else:
            cursor = conn.execute(
                """
                INSERT INTO leads (
                    first_name, last_name, phone_e164, phone_raw, source,
                    lead_status, sales_stage, temperature
                ) VALUES ('WhatsApp', 'Unknown', ?, ?, 'twilio_webhook_mock', 'new', 'new', 'warm')
                """,
                (from_phone, from_phone),
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
                l.first_name,
                l.last_name,
                l.course_title,
                u.full_name AS assigned_to_name
            FROM tasks t
            JOIN leads l ON l.id = t.lead_id
            LEFT JOIN users u ON u.id = t.assigned_to_user_id
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
            ) VALUES (?, ?, 'call', ?, ?, ?, ?, ?, 'open')
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
