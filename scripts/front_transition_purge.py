from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import connect, init_db
from sales_cockpit.services.front_import import FRONT_TRANSITION_SOURCE, purge_front_transition_import


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge one Front transition import run.")
    parser.add_argument("--import-run-id", required=True, help="Import run id to purge.")
    parser.add_argument("--yes", action="store_true", help="Actually delete the run. Default is dry-run.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    import_run_id = args.import_run_id.strip()
    if not import_run_id:
        raise SystemExit("--import-run-id is required.")

    init_db()
    preview = _preview_purge(import_run_id)
    output: dict[str, Any] = {
        "dry_run": not args.yes,
        "import_run_id": import_run_id,
        "preview": preview,
    }
    if args.yes:
        output["purge_result"] = purge_front_transition_import(import_run_id)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("Front transition purge")
    print(f"Dry run: {output['dry_run']}")
    print(f"Import run id: {import_run_id}")
    print(f"Preview: {json.dumps(preview, ensure_ascii=False)}")
    if args.yes:
        print(f"Purge result: {json.dumps(output['purge_result'], ensure_ascii=False)}")
    else:
        print("No deletion performed. Re-run with --yes to purge this run.")


def _preview_purge(import_run_id: str) -> dict[str, int]:
    with connect() as conn:
        lead_rows = conn.execute(
            """
            SELECT id
            FROM leads
            WHERE source = ? AND front_import_run_id = ?
            """,
            (FRONT_TRANSITION_SOURCE, import_run_id),
        ).fetchall()
        lead_ids = [int(row["id"]) for row in lead_rows]
        front_conversations = conn.execute(
            "SELECT COUNT(*) AS total FROM front_conversations WHERE import_run_id = ?",
            (import_run_id,),
        ).fetchone()["total"]
        front_messages = conn.execute(
            "SELECT COUNT(*) AS total FROM front_messages WHERE import_run_id = ?",
            (import_run_id,),
        ).fetchone()["total"]
        if not lead_ids:
            return {
                "leads": 0,
                "conversations": 0,
                "messages": 0,
                "tasks": 0,
                "front_conversations": int(front_conversations),
                "front_messages": int(front_messages),
            }
        placeholders = ", ".join("?" for _ in lead_ids)
        conversations = conn.execute(
            f"SELECT COUNT(*) AS total FROM conversations WHERE lead_id IN ({placeholders})",
            lead_ids,
        ).fetchone()["total"]
        messages = conn.execute(
            f"SELECT COUNT(*) AS total FROM messages WHERE lead_id IN ({placeholders})",
            lead_ids,
        ).fetchone()["total"]
        tasks = conn.execute(
            f"SELECT COUNT(*) AS total FROM tasks WHERE lead_id IN ({placeholders})",
            lead_ids,
        ).fetchone()["total"]
    return {
        "leads": len(lead_ids),
        "conversations": int(conversations),
        "messages": int(messages),
        "tasks": int(tasks),
        "front_conversations": int(front_conversations),
        "front_messages": int(front_messages),
    }


if __name__ == "__main__":
    main()
