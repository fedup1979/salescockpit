from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sales_cockpit.db import connect, insert_event, row_to_dict, rows_to_dicts
from sales_cockpit.services.whatsapp_rules import iso_utc


PHONE_PATTERN = re.compile(r"(?:whatsapp:)?(\+?\d[\d\s().-]{6,}\d)", re.IGNORECASE)
FRONT_ACTIVE_STATUSES = {"assigned", "unassigned", "open", "waiting", "pending"}
FRONT_RESOLVED_STATUSES = {"archived", "resolved", "closed", "deleted", "spam"}


def normalize_phone_e164(raw_phone: Any, default_country: str = "CH") -> str | None:
    raw = str(raw_phone or "").strip()
    if not raw:
        return None
    raw = raw.replace("whatsapp:", "").replace("WhatsApp:", "")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    keep_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if keep_plus:
        return f"+{digits}"
    if default_country.upper() == "CH" and digits.startswith("0") and len(digits) == 10:
        return f"+41{digits[1:]}"
    if digits.startswith("41") and len(digits) == 11:
        return f"+{digits}"
    if 8 <= len(digits) <= 15:
        return f"+{digits}"
    return None


def extract_front_phone(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> str | None:
    candidates: list[str] = []
    for key in ("subject", "to", "from"):
        value = conversation.get(key)
        if value:
            candidates.append(str(value))
    for recipient in conversation.get("recipients") or []:
        if isinstance(recipient, dict):
            candidates.extend(
                str(value)
                for value in (
                    recipient.get("handle"),
                    recipient.get("name"),
                    recipient.get("phone"),
                )
                if value
            )
    for message in messages or []:
        for key in ("recipient", "sender", "to", "from"):
            value = message.get(key)
            if isinstance(value, dict):
                candidates.extend(str(item) for item in value.values() if item)
            elif value:
                candidates.append(str(value))

    for candidate in candidates:
        for match in PHONE_PATTERN.finditer(candidate):
            normalized = normalize_phone_e164(match.group(1))
            if normalized:
                return normalized
    return None


def match_front_conversation(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    phone = extract_front_phone(conversation, messages)
    if not phone:
        return {
            "match_status": "unmatched",
            "match_confidence": 0.0,
            "match_reason": "Aucun téléphone exploitable trouvé dans Front.",
            "phone_e164": None,
            "lead_id": None,
            "conversation_id": None,
        }
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                l.id AS lead_id,
                c.id AS conversation_id,
                l.schooldrive_lead_id,
                l.first_name,
                l.last_name,
                l.phone_e164,
                c.recipient_phone_e164
            FROM leads l
            LEFT JOIN conversations c ON c.lead_id = l.id
            WHERE l.phone_e164 = ?
               OR l.phone_raw = ?
               OR c.recipient_phone_e164 = ?
            ORDER BY l.id, c.id DESC
            """,
            (phone, phone, phone),
        ).fetchall()
    matches = rows_to_dicts(rows)
    unique_lead_ids = sorted({item["lead_id"] for item in matches if item.get("lead_id")})
    if not matches:
        return {
            "match_status": "unmatched",
            "match_confidence": 0.0,
            "match_reason": f"Aucun lead Sales Cockpit avec le téléphone {phone}.",
            "phone_e164": phone,
            "lead_id": None,
            "conversation_id": None,
        }
    if len(unique_lead_ids) > 1:
        return {
            "match_status": "ambiguous",
            "match_confidence": 0.4,
            "match_reason": f"Plusieurs leads correspondent au téléphone {phone}.",
            "phone_e164": phone,
            "lead_id": None,
            "conversation_id": None,
            "matches": matches,
        }
    match = matches[0]
    return {
        "match_status": "matched",
        "match_confidence": 1.0,
        "match_reason": f"Correspondance exacte par téléphone {phone}.",
        "phone_e164": phone,
        "lead_id": match["lead_id"],
        "conversation_id": match["conversation_id"],
        "matches": matches,
    }


def classify_front_migration(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = str(conversation.get("status") or "").strip().lower()
    latest_message = _latest_front_message(messages or [])
    latest_direction = None
    if latest_message:
        latest_direction = "inbound" if latest_message.get("is_inbound") else "outbound"

    if status in FRONT_RESOLVED_STATUSES:
        return {
            "migration_status": "resolved",
            "migration_action_type": None,
            "migration_reason": f"Front indique '{status}'. Importer comme historique fermé, sans prochaine action.",
        }
    if status in FRONT_ACTIVE_STATUSES:
        if latest_direction == "inbound":
            return {
                "migration_status": "active",
                "migration_action_type": "reply",
                "migration_reason": "Conversation Front active avec dernier message client entrant : répondre dans Sales Cockpit.",
            }
        if latest_direction == "outbound":
            return {
                "migration_status": "active",
                "migration_action_type": "follow_up",
                "migration_reason": "Conversation Front active avec dernier message équipe sortant : prévoir une relance ou revue.",
            }
        return {
            "migration_status": "manual_review",
            "migration_action_type": None,
            "migration_reason": "Conversation Front active mais aucun message exploitable : revue manuelle nécessaire.",
        }
    return {
        "migration_status": "manual_review",
        "migration_action_type": None,
        "migration_reason": f"Statut Front inconnu ou non mappé : '{status or 'vide'}'. Revue manuelle nécessaire.",
    }


def preview_front_conversation(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    match = match_front_conversation(conversation, messages)
    migration = classify_front_migration(conversation, messages)
    return {
        "front_conversation_id": _front_id(conversation),
        "subject": conversation.get("subject") or "",
        "front_status": conversation.get("status") or "",
        "assignee": _name_or_id(conversation.get("assignee")),
        "phone_e164": match.get("phone_e164"),
        "match_status": match["match_status"],
        "match_confidence": match["match_confidence"],
        "match_reason": match["match_reason"],
        "lead_id": match.get("lead_id"),
        "conversation_id": match.get("conversation_id"),
        "message_count": len(messages or []),
        **migration,
    }


def upsert_front_history(
    conversation: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
    attach_history: bool = False,
) -> dict[str, Any]:
    front_conversation_id = _front_id(conversation)
    if not front_conversation_id:
        raise ValueError("Front conversation id is required.")
    messages = messages or []
    match = match_front_conversation(conversation, messages)
    migration = classify_front_migration(conversation, messages)
    now = iso_utc()
    payload_json = json.dumps(conversation, ensure_ascii=False, sort_keys=True)
    links = conversation.get("_links") if isinstance(conversation.get("_links"), dict) else {}
    with connect() as conn:
        existing = row_to_dict(
            conn.execute(
                "SELECT id FROM front_conversations WHERE front_conversation_id = ?",
                (front_conversation_id,),
            ).fetchone()
        )
        values = (
            match.get("lead_id"),
            match.get("conversation_id"),
            match["match_status"],
            match["match_confidence"],
            match["match_reason"],
            match.get("phone_e164"),
            conversation.get("subject") or "",
            conversation.get("status") or "",
            _name_or_id(conversation.get("assignee")),
            migration["migration_status"],
            migration["migration_action_type"],
            migration["migration_reason"],
            links.get("self") if isinstance(links, dict) else None,
            payload_json,
            now,
            now,
        )
        if existing:
            front_conversation_row_id = int(existing["id"])
            conn.execute(
                """
                UPDATE front_conversations
                SET lead_id = ?, conversation_id = ?, match_status = ?,
                    match_confidence = ?, match_reason = ?, phone_e164 = ?,
                    subject = ?, front_status = ?, assignee_name = ?,
                    migration_status = ?, migration_action_type = ?, migration_reason = ?,
                    api_link = ?, payload_json = ?, last_seen_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (*values, front_conversation_row_id),
            )
            conversation_created = False
        else:
            cursor = conn.execute(
                """
                INSERT INTO front_conversations (
                    front_conversation_id, lead_id, conversation_id, match_status,
                    match_confidence, match_reason, phone_e164, subject, front_status,
                    assignee_name, migration_status, migration_action_type, migration_reason,
                    api_link, payload_json, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (front_conversation_id, *values),
            )
            front_conversation_row_id = int(cursor.lastrowid)
            conversation_created = True

        inserted_messages = 0
        attached_messages = 0
        for message in messages:
            message_result = _upsert_front_message(
                conn,
                front_conversation_id=front_conversation_id,
                front_conversation_row_id=front_conversation_row_id,
                lead_id=match.get("lead_id"),
                conversation_id=match.get("conversation_id"),
                message=message,
                attach_history=attach_history and match["match_status"] == "matched",
                now=now,
            )
            inserted_messages += 1 if message_result["created"] else 0
            attached_messages += 1 if message_result["attached"] else 0

        if match.get("lead_id"):
            insert_event(
                conn,
                int(match["lead_id"]),
                "front_history_seen",
                new={
                    "front_conversation_id": front_conversation_id,
                    "message_count": len(messages),
                    "attach_history": attach_history,
                    "attached_messages": attached_messages,
                },
                metadata={"conversation_id": match.get("conversation_id")},
            )
    return {
        "front_conversation_id": front_conversation_id,
        "created": conversation_created,
        "messages_seen": len(messages),
        "messages_created": inserted_messages,
        "messages_attached": attached_messages,
        **match,
        **migration,
    }


def list_front_import_records(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                fc.*,
                l.schooldrive_lead_id,
                l.first_name,
                l.last_name,
                COUNT(fm.id) AS front_message_count,
                SUM(CASE WHEN fm.imported_message_id IS NOT NULL THEN 1 ELSE 0 END) AS attached_message_count
            FROM front_conversations fc
            LEFT JOIN leads l ON l.id = fc.lead_id
            LEFT JOIN front_messages fm ON fm.front_conversation_row_id = fc.id
            GROUP BY fc.id
            ORDER BY datetime(fc.updated_at) DESC, fc.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return rows_to_dicts(rows)


def _upsert_front_message(
    conn: Any,
    front_conversation_id: str,
    front_conversation_row_id: int,
    lead_id: int | None,
    conversation_id: int | None,
    message: dict[str, Any],
    attach_history: bool,
    now: str,
) -> dict[str, bool]:
    front_message_id = _front_id(message)
    if not front_message_id:
        return {"created": False, "attached": False}
    body = _message_body(message)
    if not body:
        return {"created": False, "attached": False}
    direction = "inbound" if message.get("is_inbound") else "outbound"
    created_at = _front_timestamp_to_iso(message.get("created_at")) or now
    existing = row_to_dict(
        conn.execute(
            "SELECT id, imported_message_id FROM front_messages WHERE front_message_id = ?",
            (front_message_id,),
        ).fetchone()
    )
    imported_message_id = existing.get("imported_message_id") if existing else None
    attached = False
    if attach_history and lead_id and conversation_id and not imported_message_id:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, lead_id, direction, channel, body,
                sent_at, received_at, created_at
            ) VALUES (?, ?, ?, 'front_history', ?, ?, ?, ?)
            """,
            (
                conversation_id,
                lead_id,
                direction,
                body,
                created_at if direction == "outbound" else None,
                created_at if direction == "inbound" else None,
                created_at,
            ),
        )
        imported_message_id = int(cursor.lastrowid)
        attached = True

    payload_json = json.dumps(message, ensure_ascii=False, sort_keys=True)
    values = (
        front_conversation_id,
        front_conversation_row_id,
        lead_id,
        conversation_id,
        imported_message_id,
        direction,
        body,
        message.get("type") or "",
        created_at,
        _name_or_id(message.get("author")),
        payload_json,
        now,
    )
    if existing:
        conn.execute(
            """
            UPDATE front_messages
            SET front_conversation_id = ?, front_conversation_row_id = ?,
                lead_id = ?, conversation_id = ?, imported_message_id = ?,
                direction = ?, body = ?, front_type = ?, front_created_at = ?,
                author_name = ?, payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (*values, existing["id"]),
        )
        return {"created": False, "attached": attached}
    conn.execute(
        """
        INSERT INTO front_messages (
            front_message_id, front_conversation_id, front_conversation_row_id,
            lead_id, conversation_id, imported_message_id, direction, body,
            front_type, front_created_at, author_name, payload_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (front_message_id, *values),
    )
    return {"created": True, "attached": attached}


def _front_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("uid") or "").strip()


def _message_body(message: dict[str, Any]) -> str:
    return " ".join(str(message.get("text") or message.get("body") or "").split())


def _latest_front_message(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not messages:
        return None
    return max(messages, key=lambda message: float(message.get("created_at") or 0))


def _front_timestamp_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _name_or_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("name") or value.get("email") or value.get("id") or value.get("uid")
