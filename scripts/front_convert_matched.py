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
from sales_cockpit.services.front_import import build_front_cutover_plan
from sales_cockpit.services.whatsapp_rules import iso_utc
from sales_cockpit.store import assign_standard_next_action, get_next_action_for_lead


OWNER_BY_ACTION = {
    "reply": "service.etudiants@essr.ch",
    "follow_up": "setter2@essr.ch",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deprecated. Front transition imports must stay outside V1 flows."
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--execute", action="store_true", help="Actually create/replace actions.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing open next action. Default is to skip those rows.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be at least 1.")
    raise SystemExit(
        "front_convert_matched.py est désactivé : les conversations Front importées restent "
        "hors flux V1. Utilise scripts/front_transition_import.py puis "
        "scripts/front_transition_maintenance.py."
    )

    init_db()
    admin_id = _first_admin_id()
    user_ids_by_email = _user_ids_by_email()
    plan = build_front_cutover_plan(limit=args.limit)
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row in plan["rows"]:
        result = _convert_row(
            row,
            admin_id=admin_id,
            user_ids_by_email=user_ids_by_email,
            execute=args.execute,
            replace_existing=args.replace_existing,
        )
        rows.append(result)
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1

    output = {
        "dry_run": not args.execute,
        "replace_existing": args.replace_existing,
        "source_record_count": plan["record_count"],
        "counts": counts,
        "rows": rows,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("Front matched conversion")
    print(f"Dry run: {output['dry_run']}")
    print(f"Source records: {output['source_record_count']}")
    print(f"Counts: {output['counts']}")
    for item in rows[:30]:
        print(
            f"{item['decision']} | {item.get('front_conversation_id')} | "
            f"{item.get('action_type') or 'none'} -> {item.get('owner_email') or 'none'} | "
            f"{item.get('reason')}"
        )


def _convert_row(
    row: dict[str, Any],
    *,
    admin_id: int,
    user_ids_by_email: dict[str, int],
    execute: bool,
    replace_existing: bool,
) -> dict[str, Any]:
    action_type = row.get("recommended_action")
    owner_email = OWNER_BY_ACTION.get(str(action_type or ""))
    output = {
        "front_conversation_id": row.get("front_conversation_id"),
        "lead_id": row.get("lead_id"),
        "conversation_id": row.get("conversation_id"),
        "action_type": action_type,
        "owner_email": owner_email,
    }
    if row.get("decision") != "ready_to_convert":
        return {**output, "decision": "skipped_not_ready", "reason": row.get("reason")}
    if not row.get("lead_id") or not row.get("conversation_id"):
        return {**output, "decision": "skipped_missing_target", "reason": "Missing lead or conversation id."}
    if action_type not in OWNER_BY_ACTION:
        return {**output, "decision": "skipped_unsupported_action", "reason": f"Unsupported action {action_type}."}
    owner_id = user_ids_by_email.get(owner_email or "")
    if not owner_id:
        return {**output, "decision": "skipped_missing_owner", "reason": f"Missing owner {owner_email}."}

    existing = get_next_action_for_lead(int(row["lead_id"]))
    if existing and not replace_existing:
        return {
            **output,
            "decision": "skipped_existing_action",
            "reason": f"Existing open action {existing['id']} ({existing['type']}).",
        }
    if not execute:
        return {
            **output,
            "decision": "would_convert",
            "reason": "Dry-run only. Re-run with --execute to create the action.",
        }

    note = (
        "Conversion Front: "
        f"{row.get('migration_status')} / {row.get('recommended_action')} "
        f"depuis {row.get('front_conversation_id')}."
    )
    ok, message = assign_standard_next_action(
        int(row["conversation_id"]),
        admin_id,
        str(action_type),
        owner_id,
        iso_utc(),
        note,
    )
    return {
        **output,
        "decision": "converted" if ok else "failed",
        "reason": message,
    }


def _first_admin_id() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' AND active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("No active admin user found.")
    return int(row["id"])


def _user_ids_by_email() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute("SELECT id, email FROM users WHERE active = 1").fetchall()
    return {str(row["email"]).lower(): int(row["id"]) for row in rows}


if __name__ == "__main__":
    main()
