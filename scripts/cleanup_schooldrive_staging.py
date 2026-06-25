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
from sales_cockpit.db import connect


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
        help="Deprecated safety valve. Production cleanup is refused by this staging script.",
    )
    parser.add_argument(
        "--target-environment",
        choices=["staging"],
        help="Required with --execute. Confirms the intended cleanup target.",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help="Required with --execute: CLEAN_STAGING_SCHOOLDRIVE.",
    )
    args = parser.parse_args()

    settings = get_settings()
    environment = (settings.environment or "").strip().lower()
    if environment in {"prod", "production"}:
        raise SystemExit("Refusing to clean prod/production with cleanup_schooldrive_staging.py.")
    if args.execute:
        if args.target_environment != "staging":
            raise SystemExit("--execute requires --target-environment staging.")
        if args.confirm != "CLEAN_STAGING_SCHOOLDRIVE":
            raise SystemExit("--execute requires --confirm CLEAN_STAGING_SCHOOLDRIVE.")
        if environment != "staging":
            raise SystemExit("Refusing cleanup unless SALES_COCKPIT_ENVIRONMENT=staging.")

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
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS sd_cleanup_ids(id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM sd_cleanup_ids")
        conn.execute(
            "INSERT INTO sd_cleanup_ids SELECT id FROM leads WHERE source = 'schooldrive_webhook'"
        )
        conn.execute("DELETE FROM tasks WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)")
        conn.execute("DELETE FROM messages WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)")
        conn.execute(
            """
            DELETE FROM schooldrive_whatsapp_autoresponders
            WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)
            """
        )
        conn.execute(
            "DELETE FROM conversations WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)"
        )
        conn.execute("DELETE FROM lead_events WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)")
        conn.execute(
            """
            DELETE FROM user_activity_log
            WHERE lead_id IN (SELECT id FROM sd_cleanup_ids)
               OR conversation_id NOT IN (SELECT id FROM conversations)
               OR action_id NOT IN (SELECT id FROM tasks)
            """
        )
        conn.execute("DELETE FROM schooldrive_webhook_events")
        conn.execute("DELETE FROM leads WHERE source = 'schooldrive_webhook'")
        conn.execute("DELETE FROM messages WHERE channel = 'schooldrive_autoresponder'")
        conn.execute("DELETE FROM schooldrive_whatsapp_autoresponders")
        conn.execute("PRAGMA foreign_keys = ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Foreign key violations after cleanup: {len(violations)}")


def _vacuum(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("VACUUM")


def _count(conn: Any, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


if __name__ == "__main__":
    main()
