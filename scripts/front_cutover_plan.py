from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import init_db
from sales_cockpit.services.front_import import build_front_cutover_plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a read-only Front cutover plan.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum buffered Front conversations.")
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    init_db()
    plan = build_front_cutover_plan(limit=args.limit)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    print("Front cutover plan")
    print(f"Buffered conversations: {plan['record_count']}")
    for decision, count in sorted(plan["counts"].items()):
        print(f"- {decision}: {count}")
    print()
    for row in plan["rows"][:20]:
        action = row.get("recommended_action") or "none"
        owner = row.get("recommended_owner") or "none"
        print(
            f"{row['decision']} | {row.get('front_conversation_id')} | "
            f"{row.get('match_status')} | {row.get('migration_status')} | "
            f"{action} -> {owner} | {row.get('phone_e164') or 'no phone'}"
        )


if __name__ == "__main__":
    main()
