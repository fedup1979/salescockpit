from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import init_db
from sales_cockpit.services.front_import import rematch_front_buffer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute Front buffer matches against current Sales Cockpit leads."
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--attach-history",
        action="store_true",
        help="Attach matched buffered messages to operational threads as front_history.",
    )
    parser.add_argument("--json", action="store_true", help="Print full rematch details.")
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be at least 1.")

    init_db()
    result = rematch_front_buffer(limit=args.limit, attach_history=args.attach_history)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print("Front buffer rematch")
    print(f"Records seen: {result['records_seen']}")
    print(f"Records processed: {result['records_processed']}")
    print(f"Match counts: {result['match_counts']}")
    print(f"Migration counts: {result['migration_counts']}")
    print(f"Messages attached: {result['messages_attached']}")


if __name__ == "__main__":
    main()
