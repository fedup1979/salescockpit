from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

from sales_cockpit.config import get_settings
from sales_cockpit.security import hash_password
from sales_cockpit.services.whatsapp_rules import iso_utc, utc_now


SCHEMA = """
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
    source TEXT NOT NULL DEFAULT 'mock',
    lead_status TEXT NOT NULL DEFAULT 'new',
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
    type TEXT NOT NULL DEFAULT 'call',
    title TEXT NOT NULL,
    description TEXT,
    assigned_to_user_id INTEGER REFERENCES users(id),
    created_by_user_id INTEGER REFERENCES users(id),
    due_at TEXT,
    urgency TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
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
    conn.execute(
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
        ("yasmine@essr.ch", "Yasmine", "closer"),
    ]

    with connect() as conn:
        for email, full_name, role in users:
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
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

        demo_leads = [
            {
                "schooldrive_lead_id": "SD-DEMO-1001",
                "first_name": "Camille",
                "last_name": "Roux",
                "email": "camille.roux@example.com",
                "phone_e164": "+41790000001",
                "phone_raw": "079 000 00 01",
                "course_id": "APP",
                "course_title": "Anatomie, Physiologie, Pathologie",
                "lead_status": "lead",
                "sales_stage": "setting",
                "temperature": "hot",
                "setter_user_id": mihary_id,
                "closer_user_id": yasmine_id,
                "last_inbound_at": iso_utc(now - timedelta(hours=2)),
                "messages": [
                    ("inbound", "Bonjour, je souhaite recevoir des informations sur la formation APP.", None, now - timedelta(hours=2)),
                    ("outbound", "Bonjour Camille, merci pour votre demande. Je regarde cela avec vous.", mihary_id, now - timedelta(hours=1, minutes=45)),
                ],
                "task": ("Appeler Camille pour proposer un rendez-vous", "urgent"),
            },
            {
                "schooldrive_lead_id": "SD-DEMO-1002",
                "first_name": "Nicolas",
                "last_name": "Meyer",
                "email": "nicolas.meyer@example.com",
                "phone_e164": "+41790000002",
                "phone_raw": "079 000 00 02",
                "course_id": "FSM",
                "course_title": "Formation en santé naturelle",
                "lead_status": "prospect",
                "sales_stage": "closing",
                "temperature": "warm",
                "setter_user_id": mihary_id,
                "closer_user_id": yasmine_id,
                "last_inbound_at": iso_utc(now - timedelta(hours=31)),
                "messages": [
                    ("inbound", "Je dois encore réfléchir au financement.", None, now - timedelta(hours=31)),
                    ("outbound", "Bien reçu, je reste à disposition.", yasmine_id, now - timedelta(hours=30, minutes=20)),
                ],
                "task": ("Relancer Nicolas avec le bon modèle WhatsApp", "high"),
            },
            {
                "schooldrive_lead_id": "SD-DEMO-1003",
                "first_name": "Sarah",
                "last_name": "Perrin",
                "email": "sarah.perrin@example.com",
                "phone_e164": "+41790000003",
                "phone_raw": "079 000 00 03",
                "course_id": "AS",
                "course_title": "Assistant médical",
                "lead_status": "new",
                "sales_stage": "new",
                "temperature": "cold",
                "setter_user_id": mihary_id,
                "closer_user_id": None,
                "last_inbound_at": None,
                "messages": [
                    ("manual_note", "Conversation informelle à reporter si le prospect répond sur le canal privé.", mihary_id, now - timedelta(days=1)),
                ],
                "task": ("Premier appel de qualification", "normal"),
            },
        ]

        extra_open = [
            ("SD-DEMO-2001", "Léa", "Martin", "APP", "Anatomie, Physiologie, Pathologie", "Je suis disponible cet après-midi pour un appel.", 1, "hot", "setting", "urgent"),
            ("SD-DEMO-2002", "Marc", "Dubois", "FSM", "Formation en santé naturelle", "Merci, je veux bien les prochaines dates de rentrée.", 3, "warm", "setting", "high"),
            ("SD-DEMO-2003", "Aline", "Favre", "AS", "Assistant médical", "Est-ce que la formation est compatible avec un emploi à 80 % ?", 5, "warm", "setting", "normal"),
            ("SD-DEMO-2004", "Julien", "Mercier", "NUTRI", "Nutrition", "Je compare encore deux écoles, pouvez-vous m'expliquer la différence ?", 7, "hot", "closing", "high"),
            ("SD-DEMO-2005", "Sofia", "Bernard", "APP", "Anatomie, Physiologie, Pathologie", "J'ai rempli le formulaire et j'aimerais parler à quelqu'un.", 9, "hot", "setting", "urgent"),
            ("SD-DEMO-2006", "Thomas", "Girard", "FSM", "Formation en santé naturelle", "La reconnaissance ASCA est-elle incluse dans ce parcours ?", 11, "warm", "setting", "normal"),
            ("SD-DEMO-2007", "Nadia", "Keller", "AS", "Assistant médical", "Je peux être rappelée demain matin si possible.", 13, "warm", "appointment_booked", "normal"),
            ("SD-DEMO-2008", "Romain", "Blanc", "APP", "Anatomie, Physiologie, Pathologie", "Je suis intéressé, mais j'ai une question sur les horaires.", 15, "hot", "setting", "high"),
            ("SD-DEMO-2009", "Émilie", "Morel", "FSM", "Formation en santé naturelle", "J'ai vu l'offre de lancement, est-elle encore valable ?", 18, "hot", "closing", "urgent"),
            ("SD-DEMO-2010", "Karim", "Berset", "NUTRI", "Nutrition", "Pouvez-vous m'envoyer le programme détaillé ?", 22, "warm", "setting", "normal"),
        ]
        extra_closed = [
            ("SD-DEMO-3001", "Manon", "Richard", "APP", "Anatomie, Physiologie, Pathologie", "Je dois vérifier mon budget avant de confirmer.", 26, "warm", "closing", "high"),
            ("SD-DEMO-3002", "Hugo", "Muller", "FSM", "Formation en santé naturelle", "Je reviens vers vous après discussion avec mon employeur.", 30, "warm", "closing", "normal"),
            ("SD-DEMO-3003", "Chloé", "Schmid", "AS", "Assistant médical", "Merci, je vais réfléchir encore un peu.", 34, "cold", "setting", "normal"),
            ("SD-DEMO-3004", "Bastien", "Robert", "NUTRI", "Nutrition", "Je ne suis pas certain de pouvoir commencer cette année.", 38, "warm", "closing", "high"),
            ("SD-DEMO-3005", "Irina", "Lopes", "APP", "Anatomie, Physiologie, Pathologie", "J'attends votre retour sur les modalités de paiement.", 43, "hot", "closing", "urgent"),
            ("SD-DEMO-3006", "David", "Nguyen", "FSM", "Formation en santé naturelle", "Je n'ai pas encore lu tous les documents.", 49, "cold", "setting", "normal"),
            ("SD-DEMO-3007", "Océane", "Petit", "AS", "Assistant médical", "Je préfère être rappelée la semaine prochaine.", 54, "warm", "appointment_booked", "high"),
            ("SD-DEMO-3008", "Mathieu", "Garnier", "APP", "Anatomie, Physiologie, Pathologie", "Je suis presque décidé, il me manque le planning exact.", 61, "hot", "closing", "urgent"),
            ("SD-DEMO-3009", "Elena", "Rossi", "FSM", "Formation en santé naturelle", "J'aimerais savoir s'il reste des places.", 72, "warm", "setting", "high"),
            ("SD-DEMO-3010", "Philippe", "Aubert", "NUTRI", "Nutrition", "Je dois reporter mon projet de formation.", 96, "cold", "lost", "normal"),
        ]

        for index, (sd_id, first_name, last_name, course_id, course_title, inbound_body, hours_ago, temperature, stage, urgency) in enumerate(extra_open + extra_closed, start=1):
            setter_id = mihary_id
            closer_id = yasmine_id if stage in {"closing", "appointment_booked", "won", "lost"} else None
            inbound_at = now - timedelta(hours=hours_ago)
            outbound_at = inbound_at + timedelta(minutes=18)
            demo_leads.append(
                {
                    "schooldrive_lead_id": sd_id,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
                    "phone_e164": f"+4179000{index + 10:04d}",
                    "phone_raw": f"079 000 {index + 10:02d} {index + 10:02d}",
                    "course_id": course_id,
                    "course_title": course_title,
                    "lead_status": "prospect" if stage == "closing" else "lead",
                    "sales_stage": stage,
                    "temperature": temperature,
                    "setter_user_id": setter_id,
                    "closer_user_id": closer_id,
                    "last_inbound_at": iso_utc(inbound_at),
                    "messages": [
                        ("inbound", inbound_body, None, inbound_at),
                        (
                            "outbound",
                            f"Bonjour {first_name}, merci pour votre message. Je regarde cela et je reviens vers vous.",
                            setter_id if closer_id is None else closer_id,
                            outbound_at,
                        ),
                    ],
                    "task": (f"Relancer {first_name} {last_name}", urgency),
                }
            )

        for lead in demo_leads:
            existing = conn.execute(
                "SELECT id FROM leads WHERE schooldrive_lead_id = ?",
                (lead["schooldrive_lead_id"],),
            ).fetchone()
            if existing:
                continue

            cursor = conn.execute(
                """
                INSERT INTO leads (
                    schooldrive_lead_id, first_name, last_name, email, phone_e164, phone_raw,
                    course_id, course_title, lead_status, sales_stage, temperature,
                    setter_user_id, closer_user_id, last_schooldrive_sync_at, last_notion_sync_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead["schooldrive_lead_id"],
                    lead["first_name"],
                    lead["last_name"],
                    lead["email"],
                    lead["phone_e164"],
                    lead["phone_raw"],
                    lead["course_id"],
                    lead["course_title"],
                    lead["lead_status"],
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
                    lead_id, recipient_phone_e164, whatsapp_sender, last_inbound_at, last_outbound_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    lead["phone_e164"],
                    "whatsapp:+14155238886",
                    lead["last_inbound_at"],
                    None,
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
            conn.execute(
                """
                INSERT INTO tasks (
                    lead_id, conversation_id, type, title, assigned_to_user_id, created_by_user_id,
                    due_at, urgency, status
                ) VALUES (?, ?, 'call', ?, ?, ?, ?, ?, 'open')
                """,
                (
                    lead_id,
                    conversation_id,
                    lead["task"][0],
                    lead["setter_user_id"] or yasmine_id,
                    lead["setter_user_id"] or yasmine_id,
                    iso_utc(now + timedelta(hours=3)),
                    lead["task"][1],
                ),
            )
            insert_event(conn, lead_id, "lead_seeded", metadata={"source": "mock"})

        resolved_count = conn.execute(
            "SELECT COUNT(*) AS count FROM conversations WHERE status = 'resolved'"
        ).fetchone()["count"]
        if resolved_count == 0:
            for schooldrive_id in ["SD-DEMO-3003", "SD-DEMO-3006", "SD-DEMO-3010"]:
                conn.execute(
                    """
                    UPDATE conversations
                    SET status = 'resolved', updated_at = ?
                    WHERE lead_id = (
                        SELECT id FROM leads WHERE schooldrive_lead_id = ?
                    )
                    """,
                    (iso_utc(now), schooldrive_id),
                )

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
