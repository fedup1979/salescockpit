from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, init_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove SchoolDrive operational data from a non-production Sales Cockpit database."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply the cleanup. Without this flag, only prints counts.",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow cleanup when SALES_COCKPIT_ENVIRONMENT=production.",
    )
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    if settings.environment == "production" and not args.allow_production:
        raise SystemExit("Refusing to clean production without --allow-production.")

    before = _counts()
    result: dict[str, Any] = {
        "environment": settings.environment,
        "db_path": str(settings.resolved_db_path),
        "execute": args.execute,
        "before": before,
    }

    if args.execute:
        _cleanup()
        _vacuum(settings.resolved_db_path)
        result["after"] = _counts()
    else:
        result["after"] = before

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _counts() -> dict[str, int]:
    with connect() as conn:
        return {
            "schooldrive_leads": _count(
                conn,
                "SELECT COUNT(*) FROM leads WHERE source = 'schooldrive_webhook'",
            ),
            "schooldrive_conversations": _count(
                conn,
                """
                SELECT COUNT(*)
                FROM conversations c
                JOIN leads l ON l.id = c.lead_id
                WHERE l.source = 'schooldrive_webhook'
                """,
            ),
            "schooldrive_tasks": _count(
                conn,
                """
                SELECT COUNT(*)
                FROM tasks t
                JOIN leads l ON l.id = t.lead_id
                WHERE l.source = 'schooldrive_webhook'
                """,
            ),
            "schooldrive_messages": _count(
                conn,
                """
                SELECT COUNT(*)
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.source = 'schooldrive_webhook'
                """,
            ),
            "schooldrive_autoresponders": _count(
                conn,
                "SELECT COUNT(*) FROM schooldrive_whatsapp_autoresponders",
            ),
            "schooldrive_events": _count(
                conn,
                "SELECT COUNT(*) FROM schooldrive_webhook_events",
            ),
        }


def _cleanup() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM schooldrive_webhook_events")
        conn.execute("DELETE FROM leads WHERE source = 'schooldrive_webhook'")
        conn.execute("DELETE FROM messages WHERE channel = 'schooldrive_autoresponder'")
        conn.execute("DELETE FROM schooldrive_whatsapp_autoresponders")


def _vacuum(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("VACUUM")


def _count(conn: Any, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


if __name__ == "__main__":
    main()
