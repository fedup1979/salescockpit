from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from sales_cockpit.business_rules import DEMO_TEMPLATE_CATALOG, SEQUENCE_STEPS, SEQUENCES
from sales_cockpit.config import get_settings
from sales_cockpit.security import hash_password
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now


DEMO_SEED_VERSION = "2026-06-18-action-scenarios-v1"


SCHEMA = """
CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'setter', 'closer')),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schooldrive_lead_id TEXT UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone_e164 TEXT,
    phone_raw TEXT,
    course_id TEXT,
    course_title TEXT,
    course_category_short_title TEXT,
    lead_type TEXT NOT NULL DEFAULT 'lead',
    source TEXT NOT NULL DEFAULT 'mock',
    acquisition_type TEXT NOT NULL DEFAULT 'unknown',
    lead_status TEXT NOT NULL DEFAULT 'new',
    contact_status TEXT NOT NULL DEFAULT 'contact_allowed',
    sales_stage TEXT NOT NULL DEFAULT 'new',
    temperature TEXT NOT NULL DEFAULT 'warm',
    owner_user_id INTEGER REFERENCES users(id),
    setter_user_id INTEGER REFERENCES users(id),
    closer_user_id INTEGER REFERENCES users(id),
    last_schooldrive_sync_at TEXT,
    last_notion_sync_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel TEXT NOT NULL DEFAULT 'whatsapp_twilio',
    twilio_conversation_id TEXT,
    whatsapp_sender TEXT,
    recipient_phone_e164 TEXT,
    last_inbound_at TEXT,
    last_outbound_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    resolution_reason TEXT,
    resolution_note TEXT,
    resolved_at TEXT,
    reopened_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound', 'manual_note')),
    channel TEXT NOT NULL DEFAULT 'whatsapp_twilio',
    body TEXT NOT NULL,
    sender_user_id INTEGER REFERENCES users(id),
    twilio_message_sid TEXT,
    twilio_status TEXT,
    twilio_error_code TEXT,
    twilio_error_message TEXT,
    template_id INTEGER REFERENCES whatsapp_templates(id),
    template_variables_json TEXT,
    whatsapp_window_state_at_send TEXT,
    sent_at TEXT,
    received_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    file_name TEXT NOT NULL,
    mime_type TEXT,
    size_bytes INTEGER,
    storage_url_or_path TEXT,
    twilio_media_sid TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS whatsapp_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    twilio_content_sid TEXT,
    name TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fr',
    category TEXT NOT NULL DEFAULT 'utility',
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    rejection_reason TEXT,
    created_by_user_id INTEGER REFERENCES users(id),
    submitted_at TEXT,
    approved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS template_placeholders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL REFERENCES whatsapp_templates(id) ON DELETE CASCADE,
    placeholder_key TEXT NOT NULL,
    source_field TEXT,
    example_value TEXT,
    required INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    type TEXT NOT NULL DEFAULT 'setting_call',
    title TEXT NOT NULL,
    description TEXT,
    assigned_to_user_id INTEGER REFERENCES users(id),
    created_by_user_id INTEGER REFERENCES users(id),
    due_at TEXT,
    urgency TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,
    trigger_reason TEXT,
    sequence_code TEXT,
    sequence_step_index INTEGER,
    expected_proof_type TEXT,
    proof_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    proof_event_id INTEGER REFERENCES lead_events(id) ON DELETE SET NULL,
    previous_action_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    next_action_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    cancelled_reason TEXT,
    blocked_reason TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    timeline TEXT NOT NULL,
    trigger TEXT NOT NULL,
    owner TEXT NOT NULL,
    stop_when TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sequence_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id INTEGER NOT NULL REFERENCES sequences(id) ON DELETE CASCADE,
    sequence_code TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    delay TEXT NOT NULL,
    template_name TEXT,
    meaning TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sequence_code, step_index)
);

CREATE TABLE IF NOT EXISTS template_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    sequence_code TEXT,
    sequence_step_index INTEGER,
    course_id TEXT,
    requested_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    template_id INTEGER REFERENCES whatsapp_templates(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'to_create',
    reason TEXT NOT NULL,
    context TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    event_type TEXT NOT NULL,
    previous_value_json TEXT,
    new_value_json TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id INTEGER,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    action_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bug_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    page TEXT,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    action_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    expected_behavior TEXT,
    actual_behavior TEXT,
    severity TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES lead_events(id) ON DELETE CASCADE,
    label_type TEXT NOT NULL,
    label_value TEXT NOT NULL,
    created_by_user_id INTEGER REFERENCES users(id),
    include_in_training INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS external_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    system TEXT NOT NULL,
    external_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT,
    confidence REAL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS integration_sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    integration TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    records_processed INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    metadata_json TEXT
);
"""


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    settings = get_settings()
    ensure_parent(settings.resolved_db_path)
    settings.resolved_storage_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.resolved_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        ensure_schema_columns(conn)


def ensure_schema_columns(conn: sqlite3.Connection) -> None:
    add_missing_columns(
        conn,
        "leads",
        [
            ("course_category_short_title", "TEXT"),
            ("lead_type", "TEXT NOT NULL DEFAULT 'lead'"),
            ("acquisition_type", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("contact_status", "TEXT NOT NULL DEFAULT 'contact_allowed'"),
        ],
    )
    add_missing_columns(
        conn,
        "conversations",
        [
            ("resolution_reason", "TEXT"),
            ("resolution_note", "TEXT"),
            ("resolved_at", "TEXT"),
            ("reopened_at", "TEXT"),
        ],
    )
    add_missing_columns(
        conn,
        "tasks",
        [
            ("trigger_reason", "TEXT"),
            ("sequence_code", "TEXT"),
            ("sequence_step_index", "INTEGER"),
            ("expected_proof_type", "TEXT"),
            ("proof_message_id", "INTEGER"),
            ("proof_event_id", "INTEGER"),
            ("previous_action_id", "INTEGER"),
            ("next_action_id", "INTEGER"),
            ("cancelled_reason", "TEXT"),
            ("blocked_reason", "TEXT"),
            ("metadata_json", "TEXT"),
        ],
    )

    conn.execute(
        """
        UPDATE leads
        SET lead_type = 'lead'
        WHERE lead_type IS NULL OR trim(lead_type) = ''
        """
    )
    conn.execute(
        """
        UPDATE leads
        SET course_category_short_title = course_id
        WHERE (course_category_short_title IS NULL OR trim(course_category_short_title) = '')
          AND course_id IS NOT NULL
        """
    )
    conn.execute(
        """
        UPDATE leads
        SET contact_status = 'do_not_contact',
            lead_status = 'neutral'
        WHERE lead_status = 'do_not_contact'
        """
    )
    conn.execute(
        """
        UPDATE leads
        SET contact_status = 'contact_allowed'
        WHERE contact_status IS NULL OR trim(contact_status) = ''
        """
    )
    conn.execute(
        """
        UPDATE leads
        SET acquisition_type = CASE
            WHEN acquisition_type IS NOT NULL AND trim(acquisition_type) != '' THEN acquisition_type
            WHEN lead_type = 'presubscription' THEN 'organic'
            WHEN lead_type = 'lead' THEN 'paid_ads'
            ELSE 'unknown'
        END
        """
    )
    conn.execute(
        """
        UPDATE leads
        SET lead_status = 'neutral'
        WHERE lead_status IS NULL
           OR trim(lead_status) = ''
           OR lead_status IN ('new', 'lead', 'prospect')
        """
    )
    conn.execute(
        """
        UPDATE tasks
        SET type = 'setting_call'
        WHERE type = 'call'
        """
    )


def add_missing_columns(
    conn: sqlite3.Connection,
    table_name: str,
    migrations: list[tuple[str, str]],
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, definition in migrations:
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


def insert_event(
    conn: sqlite3.Connection,
    lead_id: int,
    event_type: str,
    user_id: int | None = None,
    previous: dict | None = None,
    new: dict | None = None,
    metadata: dict | None = None,
) -> None:
    cursor = conn.execute(
        """
        INSERT INTO lead_events (
            lead_id, user_id, event_type, previous_value_json, new_value_json, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            lead_id,
            user_id,
            event_type,
            json.dumps(previous or {}, ensure_ascii=False),
            json.dumps(new or {}, ensure_ascii=False),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    metadata_payload = metadata or {}
    conn.execute(
        """
        INSERT INTO user_activity_log (
            user_id, event_type, entity_type, entity_id, lead_id,
            conversation_id, action_id, metadata_json
        ) VALUES (?, ?, 'lead_event', ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            event_type,
            cursor.lastrowid,
            lead_id,
            metadata_payload.get("conversation_id"),
            metadata_payload.get("task_id") or metadata_payload.get("action_id"),
            json.dumps(
                {
                    "previous": previous or {},
                    "new": new or {},
                    "metadata": metadata_payload,
                },
                ensure_ascii=False,
            ),
        ),
    )


def _normalize_seeded_demo_actions(
    conn: sqlite3.Connection,
    now,
    setter_id: int,
    closer_id: int,
) -> None:
    rows = conn.execute(
        """
        SELECT
            t.id AS task_id,
            t.type AS task_type,
            t.title,
            t.status AS task_status,
            t.outcome,
            l.first_name,
            l.last_name,
            l.sales_stage,
            l.temperature,
            l.schooldrive_lead_id,
            c.id AS conversation_id,
            c.status AS conversation_status
        FROM tasks t
        JOIN leads l ON l.id = t.lead_id
        LEFT JOIN conversations c ON c.id = t.conversation_id
        WHERE l.schooldrive_lead_id LIKE 'SD-DEMO-%'
          AND t.status IN ('open', 'in_progress')
        """
    ).fetchall()

    for row in rows:
        if row["conversation_status"] == "resolved":
            conn.execute(
                """
                UPDATE tasks
                SET status = 'done', outcome = 'Conversation résolue',
                    completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (iso_utc(now), iso_utc(now), row["task_id"]),
            )
            continue

        title = str(row["title"] or "")
        is_original_seed = (
            row["task_type"] == "call"
            and row["outcome"] is None
            and (
                title.startswith("Relancer ")
                or title.startswith("Appeler ")
                or title.startswith("Premier appel")
                or "rendez-vous" in title
                or "modèle WhatsApp" in title
            )
        )
        if not is_original_seed:
            continue

        full_name = f"{row['first_name']} {row['last_name']}"
        task_id = int(row["task_id"])
        if row["sales_stage"] in {"closing", "appointment_booked"}:
            action_type = "closing_call"
            action_title = f"Contacter {full_name} pour closing"
            assignee_id = closer_id
            due_at = now - timedelta(minutes=15 + task_id)
            urgency = "high" if row["temperature"] != "hot" else "urgent"
        elif task_id % 5 == 0:
            action_type = "follow_up"
            action_title = f"Relancer {full_name}"
            assignee_id = setter_id
            due_at = now + timedelta(days=1, hours=1)
            urgency = "normal"
        elif task_id % 4 == 0:
            action_type = "follow_up"
            action_title = f"Relancer {full_name}"
            assignee_id = closer_id if row["sales_stage"] == "closing" else setter_id
            due_at = now - timedelta(hours=2)
            urgency = "high"
        elif row["sales_stage"] == "new":
            action_type = "setting_call"
            action_title = f"Appeler {full_name} pour qualification"
            assignee_id = setter_id
            due_at = now
            urgency = "normal"
        else:
            action_type = "reply"
            action_title = f"Répondre à {full_name}"
            assignee_id = setter_id
            due_at = now - timedelta(minutes=task_id)
            urgency = "urgent" if row["temperature"] == "hot" else "high"

        conn.execute(
            """
            UPDATE tasks
            SET type = ?, title = ?, assigned_to_user_id = ?, due_at = ?,
                urgency = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                action_type,
                action_title,
                assignee_id,
                iso_utc(due_at),
                urgency,
                iso_utc(now),
                row["task_id"],
            ),
        )


def _ensure_demo_task_for_each_user(conn: sqlite3.Connection, now) -> None:
    users = conn.execute(
        """
        SELECT id, full_name
        FROM users
        WHERE active = 1
        ORDER BY id
        """
    ).fetchall()
    targets = conn.execute(
        """
        SELECT
            l.id AS lead_id,
            l.first_name,
            l.last_name,
            c.id AS conversation_id
        FROM leads l
        JOIN conversations c ON c.lead_id = l.id
        WHERE l.schooldrive_lead_id LIKE 'SD-DEMO-%'
          AND c.status != 'resolved'
        ORDER BY l.schooldrive_lead_id
        """
    ).fetchall()
    if not targets:
        return

    for index, user in enumerate(users):
        existing_task = conn.execute(
            """
            SELECT id
            FROM tasks
            WHERE assigned_to_user_id = ?
              AND status IN ('open', 'in_progress')
            LIMIT 1
            """,
            (user["id"],),
        ).fetchone()
        if existing_task:
            continue

        target = targets[index % len(targets)]
        prospect_name = f"{target['first_name']} {target['last_name']}"
        conn.execute(
            """
            INSERT INTO tasks (
                lead_id, conversation_id, type, title, description,
                assigned_to_user_id, created_by_user_id, due_at, urgency, status
            ) VALUES (?, ?, 'setting_call', ?, ?, ?, ?, ?, 'normal', 'open')
            """,
            (
                target["lead_id"],
                target["conversation_id"],
                f"Vérifier la file de {user['full_name']}",
                f"Tâche de démonstration liée à {prospect_name}.",
                user["id"],
                user["id"],
                iso_utc(now + timedelta(minutes=20 + index * 10)),
            ),
        )


def _seed_business_rule_tables(conn: sqlite3.Connection, now) -> None:
    current_time = iso_utc(now)
    for sequence in SEQUENCES:
        conn.execute(
            """
            INSERT INTO sequences (
                code, label, timeline, trigger, owner, stop_when, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(code) DO UPDATE SET
                label = excluded.label,
                timeline = excluded.timeline,
                trigger = excluded.trigger,
                owner = excluded.owner,
                stop_when = excluded.stop_when,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (
                sequence["code"],
                sequence["label"],
                sequence["timeline"],
                sequence["trigger"],
                sequence["owner"],
                sequence["stop_when"],
                current_time,
            ),
        )

    sequence_ids = {
        row["code"]: row["id"]
        for row in conn.execute("SELECT id, code FROM sequences").fetchall()
    }
    for step in SEQUENCE_STEPS:
        sequence_id = sequence_ids.get(step["sequence_code"])
        if not sequence_id:
            continue
        conn.execute(
            """
            INSERT INTO sequence_steps (
                sequence_id, sequence_code, step_index, delay, template_name,
                meaning, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(sequence_code, step_index) DO UPDATE SET
                sequence_id = excluded.sequence_id,
                delay = excluded.delay,
                template_name = excluded.template_name,
                meaning = excluded.meaning,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (
                sequence_id,
                step["sequence_code"],
                step["step_index"],
                step["delay"],
                step.get("template_name") or None,
                step["meaning"],
                current_time,
            ),
        )


def _normalize_lead_business_fields(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE leads
        SET contact_status = CASE
                WHEN lead_status = 'do_not_contact' THEN 'do_not_contact'
                WHEN contact_status IS NULL OR trim(contact_status) = '' THEN 'contact_allowed'
                ELSE contact_status
            END,
            lead_status = CASE
                WHEN lead_status IN ('new', 'lead', 'prospect', 'do_not_contact')
                    OR lead_status IS NULL
                    OR trim(lead_status) = ''
                THEN 'neutral'
                ELSE lead_status
            END,
            acquisition_type = CASE
                WHEN acquisition_type IS NOT NULL
                     AND trim(acquisition_type) != ''
                     AND acquisition_type != 'unknown'
                THEN acquisition_type
                WHEN lead_type = 'presubscription' THEN 'organic'
                WHEN lead_type = 'lead' THEN 'paid_ads'
                ELSE 'unknown'
            END
        """
    )


def _reset_demo_dataset_if_needed(conn: sqlite3.Connection, now) -> None:
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE key = 'demo_seed_version'"
    ).fetchone()
    if row and row["value"] == DEMO_SEED_VERSION:
        return

    conn.execute("DELETE FROM leads WHERE schooldrive_lead_id LIKE 'SD-DEMO-%'")
    conn.execute(
        """
        INSERT INTO app_metadata (key, value, updated_at)
        VALUES ('demo_seed_version', ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (DEMO_SEED_VERSION, iso_utc(now)),
    )


def reset_demo_data() -> None:
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM leads WHERE schooldrive_lead_id LIKE 'SD-DEMO-%'")
        conn.execute("DELETE FROM app_metadata WHERE key = 'demo_seed_version'")
    seed_initial_data()


def _build_demo_scenarios(
    now,
    mihary_id: int,
    setter2_id: int,
    yasmine_id: int,
    laura_id: int,
    francois_id: int,
    tiago_id: int,
) -> list[dict[str, Any]]:
    def message(direction: str, body: str, sender_user_id: int | None, delta: timedelta):
        return (direction, body, sender_user_id, now + delta)

    def task(
        action_type: str,
        title: str,
        assignee_id: int,
        due_delta: timedelta | None,
        urgency: str = "normal",
        status: str = "open",
        description: str | None = None,
        trigger_reason: str | None = None,
        sequence_code: str | None = None,
        sequence_step_index: int | None = None,
        outcome: str | None = None,
        completed_delta: timedelta | None = None,
        blocked_reason: str | None = None,
        template_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": action_type,
            "title": title,
            "assigned_to_user_id": assignee_id,
            "created_by_user_id": assignee_id,
            "due_at": iso_utc(now + due_delta) if due_delta is not None else None,
            "urgency": urgency,
            "status": status,
            "description": description,
            "trigger_reason": trigger_reason,
            "sequence_code": sequence_code,
            "sequence_step_index": sequence_step_index,
            "outcome": outcome,
            "completed_at": iso_utc(now + completed_delta) if completed_delta is not None else None,
            "blocked_reason": blocked_reason,
            "template_request": template_request,
        }

    def lead(
        schooldrive_id: str,
        first_name: str,
        last_name: str,
        phone_suffix: str,
        course_id: str,
        course_title: str,
        lead_type: str,
        lead_status: str,
        contact_status: str,
        sales_stage: str,
        setter_user_id: int | None,
        closer_user_id: int | None,
        messages: list[tuple],
        tasks: list[dict[str, Any]] | None = None,
        conversation_status: str = "open",
        resolution_reason: str | None = None,
        resolution_note: str | None = None,
        resolved_delta: timedelta | None = None,
    ) -> dict[str, Any]:
        inbound_times = [item[3] for item in messages if item[0] == "inbound"]
        category = course_id.split()[0]
        return {
            "schooldrive_lead_id": schooldrive_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": f"{schooldrive_id.lower()}@example.com",
            "phone_e164": f"+4179000{phone_suffix}",
            "phone_raw": f"079 000 {phone_suffix[:2]} {phone_suffix[2:]}",
            "course_id": course_id,
            "course_category_short_title": category,
            "course_title": course_title,
            "lead_type": lead_type,
            "lead_status": lead_status,
            "contact_status": contact_status,
            "sales_stage": sales_stage,
            "temperature": "warm",
            "setter_user_id": setter_user_id,
            "closer_user_id": closer_user_id,
            "last_inbound_at": iso_utc(max(inbound_times)) if inbound_times else None,
            "conversation_status": conversation_status,
            "resolution_reason": resolution_reason,
            "resolution_note": resolution_note,
            "resolved_at": iso_utc(now + resolved_delta) if resolved_delta is not None else None,
            "messages": messages,
            "tasks": tasks or [],
        }

    return [
        lead(
            "SD-DEMO-4001",
            "Léa",
            "Martin",
            "4001",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("outbound", "Bonjour Léa, merci pour votre demande APP. Yasmine", yasmine_id, -timedelta(days=1)),
                message("inbound", "Bonjour, je suis disponible maintenant pour échanger.", None, -timedelta(minutes=5)),
            ],
            [
                task(
                    "reply",
                    "Répondre à Léa Martin",
                    mihary_id,
                    -timedelta(minutes=5),
                    "urgent",
                    description="Le prospect attend une réponse maintenant.",
                    trigger_reason="prospect_replied",
                )
            ],
        ),
        lead(
            "SD-DEMO-4002",
            "Marc",
            "Dubois",
            "4002",
            "FSM",
            "Formation en santé naturelle",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Merci, je veux bien les prochaines dates de rentrée.", None, -timedelta(hours=13)),
                message("outbound", "Bonjour Marc, je vous envoie les informations utiles. Yasmine", mihary_id, -timedelta(hours=12)),
            ],
            [
                task(
                    "reply",
                    "Répondre à Marc Dubois",
                    mihary_id,
                    -timedelta(hours=12),
                    "high",
                    "done",
                    outcome="reply_no_appointment",
                    completed_delta=-timedelta(hours=12),
                ),
                task(
                    "follow_up",
                    "Relancer Marc Dubois",
                    setter2_id,
                    timedelta(hours=60),
                    "normal",
                    description="Relance après échange setter sans RDV.",
                    trigger_reason="reply_sent_no_setting_booked",
                    sequence_code="setter_no_next_step",
                    sequence_step_index=1,
                ),
            ],
        ),
        lead(
            "SD-DEMO-4003",
            "Sarah",
            "Perrin",
            "4003",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "new",
            mihary_id,
            None,
            [
                message("outbound", "Bonjour Sarah, merci pour votre demande APP. Yasmine", yasmine_id, -timedelta(hours=73)),
            ],
            [
                task(
                    "follow_up",
                    "Relancer Sarah Perrin",
                    setter2_id,
                    -timedelta(minutes=10),
                    "high",
                    description="Aucune réponse au premier WhatsApp automatique après 72h.",
                    trigger_reason="initial_message_no_reply_after_72h",
                    sequence_code="lead_no_reply",
                    sequence_step_index=1,
                )
            ],
        ),
        lead(
            "SD-DEMO-4004",
            "Aline",
            "Favre",
            "4004",
            "AS",
            "AS GE E26 PM",
            "presubscription",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Je dois réfléchir à mon budget.", None, -timedelta(hours=76)),
                message("outbound", "Bien reçu, je reste disponible si besoin. Yasmine", mihary_id, -timedelta(hours=75)),
            ],
            [
                task(
                    "follow_up",
                    "Relancer Aline Favre",
                    setter2_id,
                    -timedelta(minutes=30),
                    "normal",
                    description="Fenêtre WhatsApp fermée, template obligatoire.",
                    trigger_reason="follow_up_due",
                    sequence_code="setter_no_next_step",
                    sequence_step_index=2,
                )
            ],
        ),
        lead(
            "SD-DEMO-4005",
            "Thomas",
            "Girard",
            "4005",
            "FSM",
            "Formation en santé naturelle",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Je cherche une solution très spécifique pour un financement employeur.", None, -timedelta(days=4)),
                message("outbound", "Je regarde quelle réponse est la plus adaptée. Yasmine", mihary_id, -timedelta(days=4, minutes=-20)),
            ],
            [
                task(
                    "follow_up",
                    "Relancer Thomas Girard",
                    setter2_id,
                    -timedelta(hours=1),
                    "high",
                    "blocked",
                    description="Aucun template adapté au financement employeur.",
                    trigger_reason="follow_up_due_template_missing",
                    sequence_code="setter_no_next_step",
                    sequence_step_index=3,
                    blocked_reason="template_missing",
                    template_request={
                        "status": "to_create",
                        "reason": "Créer un template financement employeur",
                        "context": "Le prospect demande si l'employeur peut prendre en charge la formation.",
                    },
                )
            ],
        ),
        lead(
            "SD-DEMO-4006",
            "Nadia",
            "Keller",
            "4006",
            "AS",
            "AS GE E26 PM",
            "presubscription",
            "eligible",
            "contact_allowed",
            "appointment_booked",
            mihary_id,
            None,
            [
                message("inbound", "Oui, demain matin me convient pour un appel.", None, -timedelta(hours=4)),
                message("outbound", "Parfait, mon collègue vous appelle demain matin. Yasmine", mihary_id, -timedelta(hours=3, minutes=50)),
            ],
            [
                task(
                    "setting_call",
                    "Appeler Nadia Keller pour setting",
                    mihary_id,
                    timedelta(minutes=20),
                    "high",
                    description="RDV setting confirmé, mini note obligatoire après l'appel.",
                    trigger_reason="setting_appointment_booked",
                )
            ],
        ),
        lead(
            "SD-DEMO-4007",
            "Romain",
            "Blanc",
            "4007",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Vous pouvez m'appeler aujourd'hui.", None, -timedelta(hours=3)),
                message("outbound", "Très bien, mon collègue vous appelle aujourd'hui. Yasmine", mihary_id, -timedelta(hours=2, minutes=50)),
            ],
            [
                task(
                    "setting_call",
                    "Appeler Romain Blanc pour setting",
                    mihary_id,
                    -timedelta(hours=2),
                    "high",
                    "done",
                    outcome="not_reached",
                    completed_delta=-timedelta(hours=2),
                ),
                task(
                    "setting_call",
                    "Rappeler Romain Blanc pour setting",
                    mihary_id,
                    timedelta(hours=2),
                    "high",
                    description="Premier rappel après appel setting non joint.",
                    trigger_reason="setting_call_not_reached",
                    sequence_code="setting_call_not_reached",
                    sequence_step_index=1,
                ),
            ],
        ),
        lead(
            "SD-DEMO-4008",
            "Nicolas",
            "Meyer",
            "4008",
            "FSM",
            "FSM GE P26",
            "presubscription",
            "neutral",
            "contact_allowed",
            "closing",
            mihary_id,
            yasmine_id,
            [
                message("inbound", "Je suis prêt à discuter de l'inscription.", None, -timedelta(hours=20)),
                message("outbound", "Parfait, je vous appelle pour finaliser. Yasmine", yasmine_id, -timedelta(hours=19)),
            ],
            [
                task(
                    "closing_call",
                    "Contacter Nicolas Meyer pour closing",
                    yasmine_id,
                    -timedelta(minutes=15),
                    "urgent",
                    description="Appel closing à réaliser, mini note obligatoire.",
                    trigger_reason="setting_call_to_closing",
                )
            ],
        ),
        lead(
            "SD-DEMO-4009",
            "Émilie",
            "Morel",
            "4009",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "closing",
            mihary_id,
            yasmine_id,
            [
                message("inbound", "Je préfère qu'on fasse le point au téléphone.", None, -timedelta(days=2)),
                message("outbound", "Je vous appelle comme convenu. Yasmine", yasmine_id, -timedelta(days=2, minutes=-10)),
            ],
            [
                task(
                    "closing_call",
                    "Contacter Émilie Morel pour closing",
                    yasmine_id,
                    -timedelta(hours=24),
                    "high",
                    "done",
                    outcome="not_reached",
                    completed_delta=-timedelta(hours=24),
                ),
                task(
                    "closing_call",
                    "Rappeler Émilie Morel pour closing",
                    yasmine_id,
                    timedelta(hours=24),
                    "high",
                    description="Deuxième rappel après closing non joint.",
                    trigger_reason="closing_call_not_reached",
                    sequence_code="closing_call_not_reached",
                    sequence_step_index=2,
                ),
            ],
        ),
        lead(
            "SD-DEMO-4010",
            "Mathieu",
            "Garnier",
            "4010",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "will_sign",
            "contact_allowed",
            "closing",
            mihary_id,
            yasmine_id,
            [
                message("inbound", "Je pense signer, il me manque seulement le dernier lien.", None, -timedelta(days=3)),
                message("outbound", "Je vous aide à finaliser. Yasmine", yasmine_id, -timedelta(days=3, minutes=-30)),
            ],
            [
                task(
                    "closing_call",
                    "Contacter Mathieu Garnier pour closing",
                    yasmine_id,
                    -timedelta(days=3),
                    "high",
                    "done",
                    outcome="will_sign",
                    completed_delta=-timedelta(days=3),
                ),
                task(
                    "follow_up",
                    "Relancer Mathieu Garnier",
                    setter2_id,
                    -timedelta(minutes=20),
                    "high",
                    description="Relance post-closing Va signer.",
                    trigger_reason="closing_call_will_sign",
                    sequence_code="closer_will_sign",
                    sequence_step_index=1,
                ),
            ],
        ),
        lead(
            "SD-DEMO-4011",
            "Océane",
            "Petit",
            "4011",
            "APP",
            "APP GE P26",
            "presubscription",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Je ne suis pas encore inscrite mais la rentrée approche.", None, -timedelta(days=5)),
                message("outbound", "Je vous garde informée des prochaines possibilités. Yasmine", mihary_id, -timedelta(days=5, minutes=-20)),
            ],
            [
                task(
                    "follow_up",
                    "Relancer Océane Petit avant début de cours",
                    setter2_id,
                    -timedelta(minutes=25),
                    "urgent",
                    description="Relance liée au début de cours, prioritaire sur les relances liées au lead.",
                    trigger_reason="course_start_approaching",
                    sequence_code="course_start",
                    sequence_step_index=3,
                )
            ],
        ),
        lead(
            "SD-DEMO-4012",
            "Hugo",
            "Muller",
            "4012",
            "FSM",
            "Formation en santé naturelle",
            "lead",
            "neutral",
            "do_not_contact",
            "setting",
            mihary_id,
            None,
            [
                message("inbound", "Ne me contactez plus.", None, -timedelta(days=8)),
                message("outbound", "Bien reçu, nous ne vous recontacterons plus. Yasmine", mihary_id, -timedelta(days=8, minutes=-5)),
                message("inbound", "Finalement j'ai une question sur les dates.", None, -timedelta(minutes=20)),
            ],
            [
                task(
                    "contact_review",
                    "Revoir le statut de contact de Hugo Muller",
                    mihary_id,
                    -timedelta(minutes=20),
                    "urgent",
                    description="Le prospect était Ne plus contacter mais vient de réécrire.",
                    trigger_reason="do_not_contact_prospect_replied",
                )
            ],
        ),
        lead(
            "SD-DEMO-4013",
            "Irina",
            "Lopes",
            "4013",
            "AS",
            "AS GE E26 PM",
            "presubscription",
            "signed",
            "contact_allowed",
            "won",
            mihary_id,
            yasmine_id,
            [
                message("inbound", "C'est bon, je viens de signer.", None, -timedelta(days=1)),
                message("outbound", "Merci Irina, votre inscription est confirmée. Yasmine", yasmine_id, -timedelta(days=1, minutes=-10)),
            ],
            [
                task(
                    "closing_call",
                    "Contacter Irina Lopes pour closing",
                    yasmine_id,
                    -timedelta(days=1),
                    "high",
                    "done",
                    outcome="signed",
                    completed_delta=-timedelta(days=1),
                )
            ],
            "resolved",
            "signed",
            "Vente gagnée.",
            -timedelta(days=1, minutes=-20),
        ),
        lead(
            "SD-DEMO-4014",
            "Chloé",
            "Schmid",
            "4014",
            "FSM",
            "Formation en santé naturelle",
            "lead",
            "neutral",
            "contact_allowed",
            "lost",
            mihary_id,
            None,
            [
                message("outbound", "Bonjour Chloé, je clôture votre demande pour le moment. Yasmine", yasmine_id, -timedelta(days=30)),
            ],
            [],
            "resolved",
            "sequence_completed_no_reply",
            "Dernière relance envoyée sans réponse.",
            -timedelta(days=30),
        ),
        lead(
            "SD-DEMO-4015",
            "Philippe",
            "Aubert",
            "4015",
            "NUTRI",
            "Nutrition",
            "lead",
            "not_relevant",
            "contact_allowed",
            "lost",
            mihary_id,
            None,
            [
                message("inbound", "Je ne parle pas français et je vis hors zone compatible.", None, -timedelta(days=2)),
                message("manual_note", "Qualification : non pertinent, pas de suite commerciale.", mihary_id, -timedelta(days=2, minutes=-15)),
            ],
            [],
            "resolved",
            "not_relevant",
            "Prospect non pertinent.",
            -timedelta(days=2),
        ),
        lead(
            "SD-DEMO-4016",
            "",
            "",
            "4016",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "new",
            mihary_id,
            None,
            [
                message("inbound", "Bonjour, pouvez-vous m'envoyer les informations ?", None, -timedelta(minutes=3)),
            ],
            [
                task(
                    "reply",
                    "Répondre à Inconnu(e)",
                    mihary_id,
                    -timedelta(minutes=3),
                    "urgent",
                    description="Prospect sans nom identifié, téléphone uniquement.",
                    trigger_reason="prospect_replied",
                )
            ],
        ),
        lead(
            "SD-DEMO-4017",
            "Laura",
            "Admin Démo",
            "4017",
            "FSM",
            "Formation en santé naturelle",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("manual_note", "Démo admin : valider un modèle de message avant publication.", laura_id, -timedelta(hours=2)),
            ],
            [
                task(
                    "other",
                    "Valider le wording du modèle financement",
                    laura_id,
                    timedelta(hours=1),
                    "normal",
                    description="Tâche admin de démonstration pour vérifier la file personnelle de Laura.",
                    trigger_reason="demo_admin_task",
                )
            ],
        ),
        lead(
            "SD-DEMO-4018",
            "François",
            "Admin Démo",
            "4018",
            "APP",
            "Anatomie, Physiologie, Pathologie",
            "lead",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("manual_note", "Démo admin : relire la logique de transitions.", francois_id, -timedelta(hours=1)),
            ],
            [
                task(
                    "other",
                    "Relire la logique de transitions",
                    francois_id,
                    -timedelta(minutes=5),
                    "normal",
                    description="Tâche admin de démonstration pour vérifier la file personnelle de François.",
                    trigger_reason="demo_admin_task",
                )
            ],
        ),
        lead(
            "SD-DEMO-4019",
            "Tiago",
            "Admin Démo",
            "4019",
            "AS",
            "AS GE E26 PM",
            "presubscription",
            "neutral",
            "contact_allowed",
            "setting",
            mihary_id,
            None,
            [
                message("manual_note", "Démo admin : vérifier le mapping SchoolDrive.", tiago_id, -timedelta(hours=1)),
            ],
            [
                task(
                    "other",
                    "Vérifier le mapping SchoolDrive",
                    tiago_id,
                    timedelta(hours=2),
                    "normal",
                    description="Tâche admin de démonstration pour vérifier la file personnelle de Tiago.",
                    trigger_reason="demo_admin_task",
                )
            ],
        ),
    ]


def seed_initial_data() -> None:
    init_db()
    settings = get_settings()
    now = utc_now()
    password = settings.seed_password

    users = [
        ("laura.escariz@essr.ch", "Laura Escariz", "admin"),
        ("francois.dupuis@essr.ch", "François Dupuis", "admin"),
        ("tiago.jacobs@gmail.com", "Tiago Jacobs", "admin"),
        ("service.etudiants@essr.ch", "Mihary", "setter"),
        ("setter2@essr.ch", "Tanjona", "setter"),
        ("yasmine@essr.ch", "Yasmine", "closer"),
    ]

    with connect() as conn:
        _seed_business_rule_tables(conn, now)
        for email, full_name, role in users:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET full_name = ?, role = ?, active = 1
                    WHERE email = ?
                    """,
                    (full_name, role, email),
                )
                continue
            conn.execute(
                """
                INSERT INTO users (email, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
                """,
                (email, hash_password(password), full_name, role),
            )

        mihary_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("service.etudiants@essr.ch",)
        ).fetchone()["id"]
        yasmine_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("yasmine@essr.ch",)
        ).fetchone()["id"]
        setter2_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("setter2@essr.ch",)
        ).fetchone()["id"]
        laura_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("laura.escariz@essr.ch",)
        ).fetchone()["id"]
        francois_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("francois.dupuis@essr.ch",)
        ).fetchone()["id"]
        tiago_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("tiago.jacobs@gmail.com",)
        ).fetchone()["id"]

        _reset_demo_dataset_if_needed(conn, now)

        demo_leads = _build_demo_scenarios(
            now,
            mihary_id,
            setter2_id,
            yasmine_id,
            laura_id,
            francois_id,
            tiago_id,
        )

        for lead in demo_leads:
            existing = conn.execute(
                "SELECT id FROM leads WHERE schooldrive_lead_id = ?",
                (lead["schooldrive_lead_id"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE leads
                    SET course_category_short_title = ?, course_title = ?, lead_type = ?,
                        acquisition_type = ?, contact_status = coalesce(contact_status, 'contact_allowed'),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        lead["course_category_short_title"],
                        lead["course_title"],
                        lead["lead_type"],
                        "organic" if lead["lead_type"] == "presubscription" else "paid_ads",
                        iso_utc(now),
                        existing["id"],
                    ),
                )
                continue

            cursor = conn.execute(
                """
                INSERT INTO leads (
                    schooldrive_lead_id, first_name, last_name, email, phone_e164, phone_raw,
                    course_id, course_category_short_title, course_title, lead_type, acquisition_type,
                    lead_status, contact_status, sales_stage, temperature,
                    setter_user_id, closer_user_id, last_schooldrive_sync_at, last_notion_sync_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead["schooldrive_lead_id"],
                    lead["first_name"],
                    lead["last_name"],
                    lead["email"],
                    lead["phone_e164"],
                    lead["phone_raw"],
                    lead["course_id"],
                    lead["course_category_short_title"],
                    lead["course_title"],
                    lead["lead_type"],
                    "organic" if lead["lead_type"] == "presubscription" else "paid_ads",
                    lead["lead_status"],
                    lead["contact_status"],
                    lead["sales_stage"],
                    lead["temperature"],
                    lead["setter_user_id"],
                    lead["closer_user_id"],
                    iso_utc(now),
                    iso_utc(now),
                ),
            )
            lead_id = cursor.lastrowid
            conv_cursor = conn.execute(
                """
                INSERT INTO conversations (
                    lead_id, recipient_phone_e164, whatsapp_sender, last_inbound_at, last_outbound_at,
                    status, resolution_reason, resolution_note, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    lead["phone_e164"],
                    "whatsapp:+14155238886",
                    lead["last_inbound_at"],
                    None,
                    lead.get("conversation_status", "open"),
                    lead.get("resolution_reason"),
                    lead.get("resolution_note"),
                    lead.get("resolved_at"),
                ),
            )
            conversation_id = conv_cursor.lastrowid
            last_outbound = None
            for direction, body, sender_user_id, message_time in lead["messages"]:
                timestamp = iso_utc(message_time)
                conn.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, lead_id, direction, channel, body, sender_user_id,
                        twilio_status, sent_at, received_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        lead_id,
                        direction,
                        "whatsapp_twilio" if direction != "manual_note" else "private_whatsapp_manual",
                        body,
                        sender_user_id,
                        "delivered" if direction == "outbound" else None,
                        timestamp if direction == "outbound" else None,
                        timestamp if direction == "inbound" else None,
                        timestamp,
                    ),
                )
                if direction == "outbound":
                    last_outbound = timestamp
            conn.execute(
                "UPDATE conversations SET last_outbound_at = ? WHERE id = ?",
                (last_outbound, conversation_id),
            )
            for lead_task in lead.get("tasks", []):
                metadata = lead_task.get("metadata")
                task_cursor = conn.execute(
                    """
                    INSERT INTO tasks (
                        lead_id, conversation_id, type, title, description,
                        assigned_to_user_id, created_by_user_id, due_at, urgency, status,
                        outcome, trigger_reason, sequence_code, sequence_step_index,
                        blocked_reason, metadata_json, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lead_id,
                        conversation_id,
                        lead_task["type"],
                        lead_task["title"],
                        lead_task.get("description"),
                        lead_task.get("assigned_to_user_id"),
                        lead_task.get("created_by_user_id"),
                        lead_task.get("due_at"),
                        lead_task.get("urgency", "normal"),
                        lead_task.get("status", "open"),
                        lead_task.get("outcome"),
                        lead_task.get("trigger_reason"),
                        lead_task.get("sequence_code"),
                        lead_task.get("sequence_step_index"),
                        lead_task.get("blocked_reason"),
                        json.dumps(metadata, ensure_ascii=False) if metadata else None,
                        lead_task.get("completed_at"),
                    ),
                )
                template_request = lead_task.get("template_request")
                if template_request:
                    conn.execute(
                        """
                        INSERT INTO template_requests (
                            lead_id, conversation_id, task_id, sequence_code, sequence_step_index,
                            course_id, requested_by_user_id, status, reason, context, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lead_id,
                            conversation_id,
                            task_cursor.lastrowid,
                            lead_task.get("sequence_code"),
                            lead_task.get("sequence_step_index"),
                            lead["course_id"],
                            lead_task.get("assigned_to_user_id"),
                            template_request.get("status", "to_create"),
                            template_request["reason"],
                            template_request.get("context"),
                            iso_utc(now),
                            iso_utc(now),
                        ),
                    )
            insert_event(conn, lead_id, "lead_seeded", metadata={"source": "mock"})

        _normalize_lead_business_fields(conn)
        _normalize_seeded_demo_actions(conn, now, mihary_id, yasmine_id)
        _ensure_demo_task_for_each_user(conn, now)

        templates = [
            (
                "app_followup_rdv",
                "HX_MOCK_APP_RDV",
                "fr",
                "utility",
                "Bonjour {{first_name}}, souhaitez-vous fixer un rendez-vous pour parler de la formation {{course_title}} ?",
                "approved",
                {"first_name": "Camille", "course_title": "APP"},
            ),
            (
                "fsm_financement",
                "HX_MOCK_FSM_FINANCEMENT",
                "fr",
                "utility",
                "Bonjour {{first_name}}, je reviens vers vous au sujet des possibilités de financement pour {{course_title}}.",
                "approved",
                {"first_name": "Nicolas", "course_title": "FSM"},
            ),
            (
                "relance_attente_validation",
                None,
                "fr",
                "utility",
                "Bonjour {{first_name}}, je prépare une réponse adaptée à votre situation et je reviens vers vous rapidement.",
                "pending",
                {"first_name": "Sarah"},
            ),
        ]
        for template in DEMO_TEMPLATE_CATALOG:
            placeholders = {
                "first_name": "Camille",
                "course_title": "Anatomie, Physiologie, Pathologie",
            }
            templates.append(
                (
                    template["name"],
                    f"HX_MOCK_{template['name'].upper()}",
                    "fr",
                    template["category"],
                    template["body"],
                    "approved",
                    placeholders,
                )
            )
        for name, sid, lang, category, body, status, placeholders in templates:
            existing_template = conn.execute(
                "SELECT id FROM whatsapp_templates WHERE name = ?",
                (name,),
            ).fetchone()
            if existing_template:
                continue

            cursor = conn.execute(
                """
                INSERT INTO whatsapp_templates (
                    name, twilio_content_sid, language, category, body, status, created_by_user_id,
                    approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    sid,
                    lang,
                    category,
                    body,
                    status,
                    yasmine_id,
                    iso_utc(now) if status == "approved" else None,
                ),
            )
            template_id = cursor.lastrowid
            for key, example in placeholders.items():
                conn.execute(
                    """
                    INSERT INTO template_placeholders (
                        template_id, placeholder_key, source_field, example_value, required
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (template_id, key, key, example),
                )
        _normalize_lead_business_fields(conn)
