from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, insert_event, row_to_dict, rows_to_dicts
from sales_cockpit.services.front_client import FrontApiError, FrontClient
from sales_cockpit.services.message_text import front_message_body_text
from sales_cockpit.services.whatsapp_rules import iso_utc


PHONE_PATTERN = re.compile(r"(?:whatsapp:)?(\+?\d[\d\s().-]{6,}\d)", re.IGNORECASE)
GENERIC_FRONT_FIRST_NAMES = {
    "",
    "contact",
    "contact front",
    "inconnu(e)",
    "inconnu",
    "inconnue",
    "non renseigné",
    "non renseigne",
    "n/a",
    "na",
    "demo",
}
FRONT_ANONYMIZED_FIRST_WORDS = {
    "amber",
    "azure",
    "black",
    "blue",
    "brown",
    "coral",
    "crimson",
    "cyan",
    "gray",
    "green",
    "grey",
    "indigo",
    "lavender",
    "lime",
    "magenta",
    "maroon",
    "navy",
    "olive",
    "orange",
    "pink",
    "purple",
    "red",
    "salmon",
    "silver",
    "tan",
    "tangerine",
    "teal",
    "taupe",
    "turquoise",
    "vermilion",
    "violet",
    "white",
    "yellow",
    "fuchsia",
}
FRONT_ANONYMIZED_SECOND_WORDS = {
    "alligator",
    "antelope",
    "armadillo",
    "axolotl",
    "badger",
    "beaver",
    "bison",
    "cheetah",
    "coyote",
    "dolphin",
    "eagle",
    "egret",
    "falcon",
    "gazelle",
    "gecko",
    "hedgehog",
    "iguana",
    "kangaroo",
    "koala",
    "lemur",
    "lynx",
    "meerkat",
    "ocelot",
    "octopus",
    "panda",
    "platypus",
    "porcupine",
    "rhinoceros",
    "seahorse",
    "sloth",
    "stork",
    "walrus",
}
FRONT_NON_PERSON_NAMES = {
    "facebook",
    "google",
    "info",
    "instagram",
    "meta",
    "none",
    "whatsapp",
}
FRONT_NON_PERSON_NAME_TOKENS = {
    "academy",
    "association",
    "cabinet",
    "clinic",
    "compta",
    "company",
    "ecole",
    "ecoles",
    "formation",
    "formations",
    "gmbh",
    "group",
    "groupe",
    "institute",
    "nutrition",
    "office",
    "sarl",
    "school",
    "suisse",
}
FRONT_ACTIVE_STATUSES = {"assigned", "unassigned", "open", "waiting", "pending"}
FRONT_RESOLVED_STATUSES = {"archived", "resolved", "closed", "deleted", "spam"}
FRONT_TRANSITION_SOURCE = "front_transition"
FRONT_TRANSITION_LEAD_TYPE = "front_transition"
FRONT_TRANSITION_REVIEW_ACTION = "front_transition_review"
FRONT_TRANSITION_FOLLOW_UP_ACTION = "front_transition_follow_up"
FRONT_TRANSITION_ACTION_TYPES = {
    FRONT_TRANSITION_REVIEW_ACTION,
    FRONT_TRANSITION_FOLLOW_UP_ACTION,
}


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
            reason = (
                "Conversation Front active avec dernier message client entrant : reprise transition Front "
                "hors flux V1."
            )
        elif latest_direction == "outbound":
            reason = (
                "Conversation Front active avec dernier message équipe sortant : reprise transition Front "
                "hors flux V1."
            )
        else:
            reason = "Conversation Front active : reprise transition Front hors flux V1."
        return {
            "migration_status": "active",
            "migration_action_type": FRONT_TRANSITION_REVIEW_ACTION,
            "migration_reason": reason,
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


def import_front_transition_records(
    records: list[dict[str, Any]],
    import_run_id: str,
) -> dict[str, Any]:
    """Import Front records as manual transition threads, never as V1 workflow items."""
    import_run_id = str(import_run_id or "").strip()
    if not import_run_id:
        raise ValueError("import_run_id is required.")
    grouped: dict[str, dict[str, Any]] = {}
    skipped = 0
    for record in records:
        conversation = record.get("conversation") if isinstance(record, dict) else None
        if not isinstance(conversation, dict):
            conversation = record if isinstance(record, dict) else {}
        messages = record.get("messages") if isinstance(record, dict) else []
        messages = messages if isinstance(messages, list) else []
        front_conversation_id = _front_id(conversation)
        if not front_conversation_id:
            skipped += 1
            continue
        phone = extract_front_phone(conversation, messages)
        group_key = _front_transition_group_key(phone, front_conversation_id)
        group = grouped.setdefault(
            group_key,
            {
                "front_group_key": group_key,
                "phone_e164": phone,
                "records": [],
                "is_open": False,
                "has_latest_inbound": False,
            },
        )
        if phone and not group.get("phone_e164"):
            group["phone_e164"] = phone
        migration = classify_front_migration(conversation, messages)
        status = str(conversation.get("status") or "").strip().lower()
        is_open = status in FRONT_ACTIVE_STATUSES or migration.get("migration_status") in {
            "active",
            "manual_review",
        }
        group["is_open"] = bool(group["is_open"] or is_open)
        latest = _latest_front_message(messages)
        group["has_latest_inbound"] = bool(
            group["has_latest_inbound"] or (latest and latest.get("is_inbound"))
        )
        group["records"].append(
            {
                "conversation": conversation,
                "messages": messages,
                "migration": migration,
                "is_open": is_open,
            }
        )

    started_at = iso_utc()
    processed_conversations = 0
    created_leads = 0
    created_conversations = 0
    created_actions = 0
    created_front_messages = 0
    attached_messages = 0
    with connect() as conn:
        for group in grouped.values():
            lead_id, conversation_id, lead_created, conversation_created = _ensure_front_transition_thread(
                conn,
                group,
                import_run_id,
                started_at,
            )
            created_leads += 1 if lead_created else 0
            created_conversations += 1 if conversation_created else 0
            group_message_times: list[tuple[str, str]] = []
            for record in group["records"]:
                front_row_id = _upsert_front_transition_conversation(
                    conn,
                    record["conversation"],
                    record["migration"],
                    import_run_id=import_run_id,
                    front_group_key=group["front_group_key"],
                    phone_e164=group.get("phone_e164"),
                    lead_id=lead_id,
                    conversation_id=conversation_id,
                    now=started_at,
                )
                processed_conversations += 1
                for message in record["messages"]:
                    result = _upsert_front_message(
                        conn,
                        front_conversation_id=_front_id(record["conversation"]),
                        front_conversation_row_id=front_row_id,
                        lead_id=lead_id,
                        conversation_id=conversation_id,
                        message=message,
                        attach_history=True,
                        now=started_at,
                        import_run_id=import_run_id,
                        front_group_key=group["front_group_key"],
                    )
                    created_front_messages += 1 if result["created"] else 0
                    attached_messages += 1 if result["attached"] else 0
                    created_at = _front_timestamp_to_iso(message.get("created_at"))
                    if created_at:
                        direction = "inbound" if message.get("is_inbound") else "outbound"
                        group_message_times.append((direction, created_at))

            _sync_front_transition_conversation_state(
                conn,
                lead_id=lead_id,
                conversation_id=conversation_id,
                import_run_id=import_run_id,
                front_group_key=group["front_group_key"],
                is_open=bool(group["is_open"]),
                message_times=group_message_times,
                now=started_at,
            )
            if group["is_open"]:
                created_actions += _ensure_front_transition_review_action(
                    conn,
                    lead_id=lead_id,
                    conversation_id=conversation_id,
                    import_run_id=import_run_id,
                    front_group_key=group["front_group_key"],
                    has_latest_inbound=bool(group["has_latest_inbound"]),
                    now=started_at,
                )
            insert_event(
                conn,
                lead_id,
                "front_transition_imported",
                new={
                    "import_run_id": import_run_id,
                    "front_group_key": group["front_group_key"],
                    "conversation_count": len(group["records"]),
                    "status": "open" if group["is_open"] else "resolved",
                },
                metadata={
                    "conversation_id": conversation_id,
                    "import_run_id": import_run_id,
                    "front_group_key": group["front_group_key"],
                },
            )
        conn.execute(
            """
            INSERT INTO integration_sync_runs (
                integration, status, started_at, finished_at, records_processed, metadata_json
            ) VALUES ('front_transition_import', 'completed', ?, ?, ?, ?)
            """,
            (
                started_at,
                iso_utc(),
                processed_conversations,
                json.dumps(
                    {
                        "import_run_id": import_run_id,
                        "group_count": len(grouped),
                        "skipped": skipped,
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    return {
        "import_run_id": import_run_id,
        "group_count": len(grouped),
        "conversation_count": processed_conversations,
        "skipped": skipped,
        "created_leads": created_leads,
        "created_conversations": created_conversations,
        "created_actions": created_actions,
        "created_front_messages": created_front_messages,
        "attached_messages": attached_messages,
    }


def purge_front_transition_import(import_run_id: str) -> dict[str, Any]:
    import_run_id = str(import_run_id or "").strip()
    if not import_run_id:
        raise ValueError("import_run_id is required.")
    with connect() as conn:
        lead_ids = [
            int(row["id"])
            for row in conn.execute(
                """
                SELECT id
                FROM leads
                WHERE source = ? AND front_import_run_id = ?
                """,
                (FRONT_TRANSITION_SOURCE, import_run_id),
            ).fetchall()
        ]
        front_conversation_count = conn.execute(
            "SELECT COUNT(*) AS total FROM front_conversations WHERE import_run_id = ?",
            (import_run_id,),
        ).fetchone()["total"]
        front_message_count = conn.execute(
            "SELECT COUNT(*) AS total FROM front_messages WHERE import_run_id = ?",
            (import_run_id,),
        ).fetchone()["total"]
        if lead_ids:
            placeholders = ", ".join("?" for _ in lead_ids)
            action_count = conn.execute(
                f"SELECT COUNT(*) AS total FROM tasks WHERE lead_id IN ({placeholders})",
                lead_ids,
            ).fetchone()["total"]
            message_count = conn.execute(
                f"SELECT COUNT(*) AS total FROM messages WHERE lead_id IN ({placeholders})",
                lead_ids,
            ).fetchone()["total"]
            conn.execute(
                f"DELETE FROM user_activity_log WHERE lead_id IN ({placeholders})",
                lead_ids,
            )
        else:
            action_count = 0
            message_count = 0
        conn.execute("DELETE FROM front_conversations WHERE import_run_id = ?", (import_run_id,))
        if lead_ids:
            placeholders = ", ".join("?" for _ in lead_ids)
            conn.execute(f"DELETE FROM leads WHERE id IN ({placeholders})", lead_ids)
        conn.execute(
            """
            DELETE FROM user_activity_log
            WHERE metadata_json LIKE ?
            """,
            (f"%{import_run_id}%",),
        )
        conn.execute(
            """
            DELETE FROM integration_sync_runs
            WHERE integration = 'front_transition_import'
              AND metadata_json LIKE ?
            """,
            (f"%{import_run_id}%",),
        )
    return {
        "import_run_id": import_run_id,
        "deleted_leads": len(lead_ids),
        "deleted_front_conversations": int(front_conversation_count),
        "deleted_front_messages": int(front_message_count),
        "deleted_messages": int(message_count),
        "deleted_actions": int(action_count),
    }


def repair_front_imported_message_bodies(
    import_run_id: str | None = None,
    *,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    filters = ["fm.imported_message_id IS NOT NULL"]
    params: list[Any] = []
    if import_run_id:
        filters.append("fm.import_run_id = ?")
        params.append(import_run_id)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(1, int(limit)))
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT fm.id, fm.imported_message_id, fm.payload_json,
                       fm.body AS front_body, m.body AS message_body
                FROM front_messages fm
                JOIN messages m ON m.id = fm.imported_message_id
                WHERE {' AND '.join(filters)}
                ORDER BY fm.id
                {limit_clause}
                """,
                params,
            ).fetchall()
        )
        updates: list[tuple[str, int, int]] = []
        for row in rows:
            body = _message_body(_json_payload(row.get("payload_json")))
            if body and (body != row.get("front_body") or body != row.get("message_body")):
                updates.append((body, int(row["id"]), int(row["imported_message_id"])))
        if not dry_run:
            now = iso_utc()
            for body, front_message_id, message_id in updates:
                conn.execute(
                    "UPDATE front_messages SET body = ?, updated_at = ? WHERE id = ?",
                    (body, now, front_message_id),
                )
                conn.execute("UPDATE messages SET body = ? WHERE id = ?", (body, message_id))
    return {
        "dry_run": dry_run,
        "scanned": len(rows),
        "would_update": len(updates),
        "updated": 0 if dry_run else len(updates),
    }


def import_front_message_attachments(
    import_run_id: str | None = None,
    *,
    dry_run: bool = True,
    limit: int | None = None,
    client: FrontClient | None = None,
) -> dict[str, Any]:
    filters = ["fm.imported_message_id IS NOT NULL", "fm.payload_json LIKE '%\"attachments\"%'"]
    params: list[Any] = []
    if import_run_id:
        filters.append("fm.import_run_id = ?")
        params.append(import_run_id)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(1, int(limit)))
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT fm.id, fm.front_message_id, fm.imported_message_id, fm.payload_json
                FROM front_messages fm
                WHERE {' AND '.join(filters)}
                ORDER BY fm.id
                {limit_clause}
                """,
                params,
            ).fetchall()
        )

    candidates: list[dict[str, Any]] = []
    for row in rows:
        payload = _json_payload(row.get("payload_json"))
        for attachment in _front_attachment_payloads(payload):
            source = f"front:{row['front_message_id']}:{attachment['front_attachment_id']}"
            candidates.append(
                {
                    **attachment,
                    "source": source,
                    "message_id": int(row["imported_message_id"]),
                    "front_message_row_id": int(row["id"]),
                    "front_message_id": row["front_message_id"],
                }
            )

    with connect() as conn:
        existing_sources = {
            row["source"]
            for row in conn.execute(
                "SELECT source FROM attachments WHERE source LIKE 'front:%'"
            ).fetchall()
        }
    pending = [item for item in candidates if item["source"] not in existing_sources]
    result: dict[str, Any] = {
        "dry_run": dry_run,
        "front_messages_scanned": len(rows),
        "candidate_attachments": len(candidates),
        "already_imported": len(candidates) - len(pending),
        "would_import": len(pending),
        "imported": 0,
        "failed": 0,
        "errors": [],
    }
    if dry_run or not pending:
        return result

    front_client = client or FrontClient.from_settings()
    settings = get_settings()
    now = iso_utc()
    with connect() as conn:
        for item in pending:
            try:
                downloaded = front_client.download_attachment(item["url"])
                content = downloaded.get("content") or b""
                if not isinstance(content, bytes) or not content:
                    raise FrontApiError("Pièce jointe Front vide.")
                file_name = _safe_attachment_filename(
                    str(downloaded.get("file_name") or item.get("file_name") or "piece_jointe_front")
                )
                mime_type = str(downloaded.get("mime_type") or item.get("mime_type") or "application/octet-stream")
                attachment_dir = settings.resolved_storage_path / "attachments" / str(item["message_id"])
                attachment_dir.mkdir(parents=True, exist_ok=True)
                storage_path = attachment_dir / f"{uuid4().hex}_{file_name}"
                storage_path.write_bytes(content)
                conn.execute(
                    """
                    INSERT INTO attachments (
                        message_id, source, file_name, mime_type, size_bytes,
                        storage_url_or_path, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["message_id"],
                        item["source"],
                        file_name,
                        mime_type,
                        len(content),
                        str(storage_path),
                        now,
                    ),
                )
                result["imported"] += 1
            except Exception as exc:  # noqa: BLE001 - continue batch and report bad files.
                result["failed"] += 1
                if len(result["errors"]) < 20:
                    result["errors"].append(
                        {
                            "front_message_id": item["front_message_id"],
                            "front_attachment_id": item["front_attachment_id"],
                            "error": str(exc),
                        }
                    )
    return result


def reconcile_front_transition_names(
    import_run_id: str | None = None,
    *,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    filters = ["l.source = ?"]
    params: list[Any] = [FRONT_TRANSITION_SOURCE]
    if import_run_id:
        filters.append("l.front_import_run_id = ?")
        params.append(import_run_id)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(max(1, int(limit)))
    with connect() as conn:
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT l.id, l.first_name, l.last_name, l.phone_e164,
                       l.front_import_run_id, l.front_transition_key
                FROM leads l
                WHERE {' AND '.join(filters)}
                ORDER BY l.id
                {limit_clause}
                """,
                params,
            ).fetchall()
        )
        decisions: list[dict[str, Any]] = []
        for lead in rows:
            if not _front_name_is_generic(lead.get("first_name"), lead.get("last_name")):
                decisions.append({"lead_id": lead["id"], "decision": "skipped_named"})
                continue
            candidates = _front_name_candidates(conn, lead)
            unique = _unique_name_candidates(candidates)
            if len(unique) == 1:
                first_name, last_name = _split_person_name(unique[0]["name"])
                decisions.append(
                    {
                        "lead_id": lead["id"],
                        "decision": "update",
                        "first_name": first_name,
                        "last_name": last_name,
                        "candidates": candidates,
                    }
                )
            elif len(unique) > 1:
                decisions.append(
                    {
                        "lead_id": lead["id"],
                        "decision": "ambiguous",
                        "candidates": candidates,
                    }
                )
            else:
                decisions.append({"lead_id": lead["id"], "decision": "unchanged"})

        if not dry_run:
            now = iso_utc()
            for decision in decisions:
                if decision["decision"] == "update":
                    conn.execute(
                        """
                        UPDATE leads
                        SET first_name = ?, last_name = ?, identity_status = 'verified',
                            identity_candidates_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            decision["first_name"],
                            decision["last_name"],
                            json.dumps(decision["candidates"], ensure_ascii=False),
                            now,
                            decision["lead_id"],
                        ),
                    )
                elif decision["decision"] == "ambiguous":
                    conn.execute(
                        """
                        UPDATE leads
                        SET identity_status = 'ambiguous_identity',
                            identity_candidates_json = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            json.dumps(decision["candidates"], ensure_ascii=False),
                            now,
                            decision["lead_id"],
                        ),
                    )

    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision["decision"]] = counts.get(decision["decision"], 0) + 1
    return {
        "dry_run": dry_run,
        "scanned": len(rows),
        "counts": counts,
        "samples": [item for item in decisions if item["decision"] in {"update", "ambiguous"}][:20],
    }


def rematch_front_buffer(limit: int = 500, attach_history: bool = False) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, payload_json
            FROM front_conversations
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        message_rows = conn.execute(
            """
            SELECT front_conversation_row_id, payload_json
            FROM front_messages
            WHERE front_conversation_row_id IN (
                SELECT id
                FROM front_conversations
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT ?
            )
            ORDER BY datetime(front_created_at) ASC, id ASC
            """,
            (limit,),
        ).fetchall()

    messages_by_front_row: dict[int, list[dict[str, Any]]] = {}
    for row in message_rows:
        message = _json_payload(row["payload_json"])
        if message:
            messages_by_front_row.setdefault(int(row["front_conversation_row_id"]), []).append(message)

    results: list[dict[str, Any]] = []
    for row in rows:
        conversation = _json_payload(row["payload_json"])
        if not conversation:
            continue
        results.append(
            upsert_front_history(
                conversation,
                messages=messages_by_front_row.get(int(row["id"]), []),
                attach_history=attach_history,
            )
        )

    match_counts: dict[str, int] = {}
    migration_counts: dict[str, int] = {}
    attached = 0
    for result in results:
        match_status = str(result.get("match_status") or "unknown")
        migration_status = str(result.get("migration_status") or "unknown")
        match_counts[match_status] = match_counts.get(match_status, 0) + 1
        migration_counts[migration_status] = migration_counts.get(migration_status, 0) + 1
        attached += int(result.get("messages_attached") or 0)

    return {
        "records_seen": len(rows),
        "records_processed": len(results),
        "match_counts": match_counts,
        "migration_counts": migration_counts,
        "messages_attached": attached,
        "results": results,
    }


def list_front_import_records(
    limit: int = 100,
    match_status: str = "all",
    migration_status: str = "all",
    migration_action_type: str = "all",
) -> list[dict[str, Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if match_status != "all":
        filters.append("fc.match_status = ?")
        params.append(match_status)
    if migration_status != "all":
        filters.append("fc.migration_status = ?")
        params.append(migration_status)
    if migration_action_type != "all":
        if migration_action_type == "none":
            filters.append("fc.migration_action_type IS NULL")
        else:
            filters.append("fc.migration_action_type = ?")
            params.append(migration_action_type)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
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
            {where}
            GROUP BY fc.id
            ORDER BY datetime(fc.updated_at) DESC, fc.id DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return rows_to_dicts(rows)


def build_front_cutover_plan(limit: int = 500) -> dict[str, Any]:
    records = list_front_import_records(limit=limit)
    rows = [_front_cutover_plan_row(record) for record in records]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    return {
        "record_count": len(records),
        "counts": counts,
        "rows": rows,
    }


def _front_cutover_plan_row(record: dict[str, Any]) -> dict[str, Any]:
    match_status = record.get("match_status")
    migration_status = record.get("migration_status")
    action_type = record.get("migration_action_type")
    if match_status != "matched":
        decision = "manual_review"
        reason = "La conversation Front n'est pas rattachée à un lead SchoolDrive/Sales Cockpit."
    elif migration_status == "resolved":
        decision = "history_only"
        reason = "Front indique une conversation terminée : importer comme historique, sans action."
    elif migration_status == "active" and action_type == FRONT_TRANSITION_REVIEW_ACTION:
        decision = "ready_to_convert"
        reason = (
            "Conversation active et rattachée : créer une reprise transition Front hors flux V1."
        )
    else:
        decision = "manual_review"
        reason = record.get("migration_reason") or "Cas non couvert par les règles automatiques."

    return {
        "decision": decision,
        "recommended_action": action_type,
        "recommended_owner": _front_recommended_owner(action_type),
        "reason": reason,
        "front_conversation_id": record.get("front_conversation_id"),
        "front_status": record.get("front_status"),
        "subject": record.get("subject"),
        "phone_e164": record.get("phone_e164"),
        "match_status": match_status,
        "migration_status": migration_status,
        "lead_id": record.get("lead_id"),
        "conversation_id": record.get("conversation_id"),
        "schooldrive_lead_id": record.get("schooldrive_lead_id"),
        "first_name": record.get("first_name"),
        "last_name": record.get("last_name"),
        "front_message_count": record.get("front_message_count") or 0,
        "attached_message_count": record.get("attached_message_count") or 0,
    }


def _front_recommended_owner(action_type: str | None) -> str | None:
    if action_type in {FRONT_TRANSITION_REVIEW_ACTION, FRONT_TRANSITION_FOLLOW_UP_ACTION}:
        return "Mihary"
    return None


def _front_transition_group_key(phone: str | None, front_conversation_id: str) -> str:
    if phone:
        return f"phone:{phone}"
    return f"front:{front_conversation_id}"


def _ensure_front_transition_thread(
    conn: Any,
    group: dict[str, Any],
    import_run_id: str,
    now: str,
) -> tuple[int, int, bool, bool]:
    group_key = group["front_group_key"]
    phone = group.get("phone_e164")
    existing = row_to_dict(
        conn.execute(
            """
            SELECT l.id AS lead_id, c.id AS conversation_id
            FROM leads l
            LEFT JOIN conversations c ON c.lead_id = l.id
            WHERE l.source = ?
              AND l.front_import_run_id = ?
              AND l.front_transition_key = ?
            ORDER BY c.id DESC
            LIMIT 1
            """,
            (FRONT_TRANSITION_SOURCE, import_run_id, group_key),
        ).fetchone()
    )
    if existing:
        lead_id = int(existing["lead_id"])
        conversation_id = existing.get("conversation_id")
        if conversation_id:
            return lead_id, int(conversation_id), False, False
        cursor = conn.execute(
            """
            INSERT INTO conversations (
                lead_id, channel, recipient_phone_e164, front_import_run_id,
                front_transition_key, created_at, updated_at
            ) VALUES (?, 'whatsapp_front_transition', ?, ?, ?, ?, ?)
            """,
            (lead_id, phone, import_run_id, group_key, now, now),
        )
        return lead_id, int(cursor.lastrowid), False, True

    label = phone or group_key.replace("front:", "Front ")
    cursor = conn.execute(
        """
        INSERT INTO leads (
            first_name, last_name, phone_e164, phone_raw, course_title,
            lead_type, source, acquisition_type, lead_status, contact_status,
            sales_stage, temperature, setter_user_id, identity_status,
            front_import_run_id, front_transition_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'Transition Front', ?, ?, 'front_transition',
            'eligible', 'contact_allowed', 'new', 'warm', ?, ?, ?, ?, ?, ?)
        """,
        (
            "Contact Front",
            label,
            phone,
            phone,
            FRONT_TRANSITION_LEAD_TYPE,
            FRONT_TRANSITION_SOURCE,
            _default_setter1_id(conn),
            "verified" if phone else "needs_identification",
            import_run_id,
            group_key,
            now,
            now,
        ),
    )
    lead_id = int(cursor.lastrowid)
    conversation_cursor = conn.execute(
        """
        INSERT INTO conversations (
            lead_id, channel, recipient_phone_e164, front_import_run_id,
            front_transition_key, created_at, updated_at
        ) VALUES (?, 'whatsapp_front_transition', ?, ?, ?, ?, ?)
        """,
        (lead_id, phone, import_run_id, group_key, now, now),
    )
    return lead_id, int(conversation_cursor.lastrowid), True, True


def _default_setter1_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE role = 'setter'
          AND active = 1
          AND lower(email) != 'setter2@essr.ch'
        ORDER BY id
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])
    row = conn.execute(
        "SELECT id FROM users WHERE role = 'setter' AND active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _default_setter2_id(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM users
        WHERE active = 1 AND lower(email) = 'setter2@essr.ch'
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])
    row = conn.execute(
        "SELECT id FROM users WHERE role = 'setter' AND active = 1 ORDER BY id LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _upsert_front_transition_conversation(
    conn: Any,
    conversation: dict[str, Any],
    migration: dict[str, Any],
    *,
    import_run_id: str,
    front_group_key: str,
    phone_e164: str | None,
    lead_id: int,
    conversation_id: int,
    now: str,
) -> int:
    front_conversation_id = _front_id(conversation)
    payload_json = json.dumps(conversation, ensure_ascii=False, sort_keys=True)
    links = conversation.get("_links") if isinstance(conversation.get("_links"), dict) else {}
    status = str(conversation.get("status") or "").strip().lower()
    is_open = status in FRONT_ACTIVE_STATUSES
    values = (
        lead_id,
        conversation_id,
        "front_transition",
        1.0 if phone_e164 else 0.5,
        "Transition Front groupée par numéro." if phone_e164 else "Transition Front sans numéro exploitable.",
        phone_e164,
        front_group_key,
        import_run_id,
        conversation.get("subject") or "",
        conversation.get("status") or "",
        _name_or_id(conversation.get("assignee")),
        "active" if is_open else migration.get("migration_status", "resolved"),
        FRONT_TRANSITION_REVIEW_ACTION if is_open else None,
        (
            "Conversation Front ouverte : reprise manuelle hors flux V1."
            if is_open
            else "Conversation Front terminée : historique seulement."
        ),
        links.get("self") if isinstance(links, dict) else None,
        payload_json,
        now,
        now,
    )
    existing = row_to_dict(
        conn.execute(
            "SELECT id FROM front_conversations WHERE front_conversation_id = ?",
            (front_conversation_id,),
        ).fetchone()
    )
    if existing:
        conn.execute(
            """
            UPDATE front_conversations
            SET lead_id = ?, conversation_id = ?, match_status = ?,
                match_confidence = ?, match_reason = ?, phone_e164 = ?,
                front_group_key = ?, import_run_id = ?, subject = ?,
                front_status = ?, assignee_name = ?, migration_status = ?,
                migration_action_type = ?, migration_reason = ?, api_link = ?,
                payload_json = ?, last_seen_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (*values, existing["id"]),
        )
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO front_conversations (
            front_conversation_id, lead_id, conversation_id, match_status,
            match_confidence, match_reason, phone_e164, front_group_key,
            import_run_id, subject, front_status, assignee_name, migration_status,
            migration_action_type, migration_reason, api_link, payload_json,
            last_seen_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (front_conversation_id, *values),
    )
    return int(cursor.lastrowid)


def _sync_front_transition_conversation_state(
    conn: Any,
    *,
    lead_id: int,
    conversation_id: int,
    import_run_id: str,
    front_group_key: str,
    is_open: bool,
    message_times: list[tuple[str, str]],
    now: str,
) -> None:
    last_inbound = max((value for direction, value in message_times if direction == "inbound"), default=None)
    last_outbound = max((value for direction, value in message_times if direction == "outbound"), default=None)
    conn.execute(
        """
        UPDATE conversations
        SET status = ?,
            resolution_reason = ?,
            resolution_note = ?,
            resolved_at = ?,
            last_inbound_at = coalesce(?, last_inbound_at),
            last_outbound_at = coalesce(?, last_outbound_at),
            front_import_run_id = ?,
            front_transition_key = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            "open" if is_open else "resolved",
            None if is_open else "front_import_archived",
            None if is_open else "Conversation Front importée comme historique terminé.",
            None if is_open else now,
            last_inbound,
            last_outbound,
            import_run_id,
            front_group_key,
            now,
            conversation_id,
        ),
    )
    conn.execute(
        """
        UPDATE leads
        SET front_import_run_id = ?, front_transition_key = ?, updated_at = ?
        WHERE id = ?
        """,
        (import_run_id, front_group_key, now, lead_id),
    )
    if not is_open:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'cancelled',
                outcome = 'Conversation Front terminée avant reprise',
                completed_at = ?,
                updated_at = ?
            WHERE lead_id = ?
              AND conversation_id = ?
              AND type IN (?, ?)
              AND status IN ('open', 'in_progress', 'planned', 'blocked')
            """,
            (
                now,
                now,
                lead_id,
                conversation_id,
                FRONT_TRANSITION_REVIEW_ACTION,
                FRONT_TRANSITION_FOLLOW_UP_ACTION,
            ),
        )


def _ensure_front_transition_review_action(
    conn: Any,
    *,
    lead_id: int,
    conversation_id: int,
    import_run_id: str,
    front_group_key: str,
    has_latest_inbound: bool,
    now: str,
) -> int:
    assignee_id = _default_setter1_id(conn)
    if not assignee_id:
        return 0
    existing = conn.execute(
        """
        SELECT id
        FROM tasks
        WHERE lead_id = ?
          AND conversation_id = ?
          AND type = ?
          AND status IN ('open', 'in_progress', 'planned', 'blocked')
        ORDER BY id DESC
        LIMIT 1
        """,
        (lead_id, conversation_id, FRONT_TRANSITION_REVIEW_ACTION),
    ).fetchone()
    title = "Reprise transition Front"
    description = (
        "Historique Front importé. Relire, répondre ou programmer une reprise manuelle hors flux V1."
    )
    urgency = "urgent" if has_latest_inbound else "normal"
    if existing:
        conn.execute(
            """
            UPDATE tasks
            SET assigned_to_user_id = ?, due_at = ?, urgency = ?,
                description = ?, front_import_run_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (assignee_id, now, urgency, description, import_run_id, now, existing["id"]),
        )
        return 0
    conn.execute(
        """
        INSERT INTO tasks (
            lead_id, conversation_id, type, title, description, assigned_to_user_id,
            created_by_user_id, due_at, urgency, status, trigger_reason,
            front_import_run_id, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, 'open',
            'front_transition_import_open_conversation', ?, ?, ?, ?)
        """,
        (
            lead_id,
            conversation_id,
            FRONT_TRANSITION_REVIEW_ACTION,
            title,
            description,
            assignee_id,
            now,
            urgency,
            import_run_id,
            json.dumps(
                {
                    "import_run_id": import_run_id,
                    "front_group_key": front_group_key,
                    "has_latest_inbound": has_latest_inbound,
                },
                ensure_ascii=False,
            ),
            now,
            now,
        ),
    )
    return 1


def _upsert_front_message(
    conn: Any,
    front_conversation_id: str,
    front_conversation_row_id: int,
    lead_id: int | None,
    conversation_id: int | None,
    message: dict[str, Any],
    attach_history: bool,
    now: str,
    import_run_id: str | None = None,
    front_group_key: str | None = None,
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
        import_run_id,
        front_group_key,
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
                import_run_id = coalesce(?, import_run_id),
                front_group_key = coalesce(?, front_group_key),
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
            lead_id, conversation_id, imported_message_id, import_run_id,
            front_group_key, direction, body, front_type, front_created_at,
            author_name, payload_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (front_message_id, *values),
    )
    return {"created": True, "attached": attached}


def _front_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("uid") or "").strip()


def _front_attachment_payloads(message: dict[str, Any]) -> list[dict[str, Any]]:
    items = message.get("attachments") if isinstance(message, dict) else []
    if not isinstance(items, list):
        return []
    attachments: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        links = item.get("_links") if isinstance(item.get("_links"), dict) else {}
        url = str(
            item.get("url")
            or item.get("download_url")
            or links.get("download")
            or links.get("self")
            or ""
        ).strip()
        if not url:
            continue
        front_attachment_id = str(item.get("id") or item.get("uid") or index).strip()
        attachments.append(
            {
                "front_attachment_id": front_attachment_id,
                "url": url,
                "file_name": item.get("filename")
                or item.get("file_name")
                or item.get("name")
                or f"piece_jointe_front_{index + 1}",
                "mime_type": item.get("content_type") or item.get("mime_type") or item.get("content-type"),
                "size_bytes": item.get("size"),
                "is_inline": bool((item.get("metadata") or {}).get("is_inline")),
            }
        )
    return attachments


def _safe_attachment_filename(value: str) -> str:
    name = Path(value).name.strip() or "piece_jointe_front"
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "piece_jointe_front"


def _json_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _message_body(message: dict[str, Any]) -> str:
    return front_message_body_text(message)


def _front_name_is_generic(first_name: Any, last_name: Any) -> bool:
    first = str(first_name or "").strip().lower()
    last = str(last_name or "").strip()
    return first in GENERIC_FRONT_FIRST_NAMES or first == "contact front" or last.startswith("Front ")


def _front_name_candidates(conn: Any, lead: dict[str, Any]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    phone = lead.get("phone_e164")
    if phone:
        for row in rows_to_dicts(
            conn.execute(
                """
                SELECT first_name, last_name, source
                FROM leads
                WHERE phone_e164 = ?
                  AND source != ?
                  AND id != ?
                ORDER BY id DESC
                """,
                (phone, FRONT_TRANSITION_SOURCE, lead["id"]),
            ).fetchall()
        ):
            name = _join_name(row.get("first_name"), row.get("last_name"))
            if _usable_front_person_name(name):
                candidates.append({"name": name, "source": f"lead:{row.get('source') or 'unknown'}"})

    front_rows = rows_to_dicts(
        conn.execute(
            """
            SELECT payload_json
            FROM front_conversations
            WHERE lead_id = ?
            """,
            (lead["id"],),
        ).fetchall()
    )
    message_rows = rows_to_dicts(
        conn.execute(
            """
            SELECT payload_json
            FROM front_messages
            WHERE lead_id = ?
            ORDER BY front_created_at DESC, id DESC
            LIMIT 50
            """,
            (lead["id"],),
        ).fetchall()
    )
    for row in front_rows:
        payload = _json_payload(row.get("payload_json"))
        for name in _conversation_name_candidates(payload):
            candidates.append({"name": name, "source": "front_conversation"})
    for row in message_rows:
        payload = _json_payload(row.get("payload_json"))
        for name in _message_name_candidates(payload, phone):
            candidates.append({"name": name, "source": "front_message"})
    return candidates


def _conversation_name_candidates(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    recipient = payload.get("recipient")
    if isinstance(recipient, dict):
        names.append(str(recipient.get("name") or ""))
    subject = str(payload.get("subject") or "")
    match = re.search(r"conversation with (.+)$", subject, re.IGNORECASE)
    if match:
        names.append(match.group(1))
    return [name for name in (_clean_candidate_name(item) for item in names) if _usable_front_person_name(name)]


def _message_name_candidates(payload: dict[str, Any], phone: str | None) -> list[str]:
    names: list[str] = []
    is_inbound = bool(payload.get("is_inbound"))
    prospect_role = "from" if is_inbound else "to"
    for recipient in payload.get("recipients") or []:
        if not isinstance(recipient, dict):
            continue
        role = str(recipient.get("role") or "").lower()
        handle = str(recipient.get("handle") or "")
        if role == prospect_role or (phone and normalize_phone_e164(handle) == phone):
            names.append(str(recipient.get("name") or ""))
    return [name for name in (_clean_candidate_name(item) for item in names) if _usable_front_person_name(name)]


def _clean_candidate_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    name = re.sub(r"^(?:WhatsApp|Facebook)\s+conversation\s+with\s+", "", name, flags=re.IGNORECASE)
    return name.strip(" .")


def _usable_front_person_name(value: str) -> bool:
    name = _clean_candidate_name(value)
    if len(name) < 2:
        return False
    lowered = name.lower()
    if lowered in FRONT_NON_PERSON_NAMES or lowered in GENERIC_FRONT_FIRST_NAMES:
        return False
    normalized_tokens = set(re.sub(r"[^a-z0-9]+", " ", lowered).split())
    if normalized_tokens & FRONT_NON_PERSON_NAME_TOKENS:
        return False
    if lowered.startswith("contact front") or lowered.startswith("contact "):
        return False
    if "essr" in lowered or "@" in lowered:
        return False
    if normalize_phone_e164(name):
        return False
    if _looks_like_front_anonymized_name(name):
        return False
    return True


def _looks_like_front_anonymized_name(value: str) -> bool:
    parts = re.sub(r"[^A-Za-z ]+", " ", value).lower().split()
    return (
        len(parts) == 2
        and parts[0] in FRONT_ANONYMIZED_FIRST_WORDS
        and parts[1] in FRONT_ANONYMIZED_SECOND_WORDS
    )


def _unique_name_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        name = _clean_candidate_name(candidate.get("name") or "")
        key = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
        if key and key not in unique:
            unique[key] = {"name": name, "source": candidate.get("source") or "unknown"}
    return list(unique.values())


def _split_person_name(value: str) -> tuple[str, str]:
    parts = _clean_candidate_name(value).split()
    if not parts:
        return "Contact Front", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _join_name(first_name: Any, last_name: Any) -> str:
    return " ".join(part for part in [str(first_name or "").strip(), str(last_name or "").strip()] if part)


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
