from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import init_db
from sales_cockpit.store import list_templates


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit local WhatsApp template readiness.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--require-approved-real",
        action="store_true",
        help="Fail if no real Twilio approved template is available.",
    )
    args = parser.parse_args()

    init_db()
    templates = list_templates()
    rows = [_template_row(template) for template in templates]
    real_rows = [row for row in rows if row["source"] == "twilio"]
    demo_rows = [row for row in rows if row["source"] == "demo"]
    approved_real = [row for row in real_rows if row["status"] == "approved"]
    result = {
        "ok": bool(approved_real) or not args.require_approved_real,
        "template_count": len(rows),
        "twilio_real_count": len(real_rows),
        "demo_count": len(demo_rows),
        "approved_real_count": len(approved_real),
        "status_counts": dict(Counter(row["status"] for row in real_rows)),
        "content_type_counts": dict(Counter(row["content_type"] for row in real_rows)),
        "real_templates": real_rows,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Twilio template audit")
        print(f"Total templates: {result['template_count']}")
        print(f"Real Twilio templates: {result['twilio_real_count']}")
        print(f"Demo/local templates: {result['demo_count']}")
        print(f"Approved real templates: {result['approved_real_count']}")
        print(f"Statuses: {result['status_counts']}")
        print(f"Content types: {result['content_type_counts']}")
        for row in real_rows:
            print(
                f"- {row['name']} | {row['content_sid']} | "
                f"{row['status']} | {row['language']} | {row['content_type']}"
            )
    if not result["ok"]:
        raise SystemExit(1)


def _template_row(template: dict) -> dict:
    sid = str(template.get("twilio_content_sid") or "")
    source = "twilio" if sid.startswith("HX") and not sid.startswith("HX_MOCK_") else "demo"
    return {
        "source": source,
        "name": template.get("name") or "",
        "content_sid": sid,
        "status": template.get("status") or "unknown",
        "language": template.get("language") or "",
        "category": template.get("category") or "",
        "content_type": template.get("twilio_content_type") or "unknown",
        "last_twilio_sync_at": template.get("last_twilio_sync_at"),
    }


if __name__ == "__main__":
    main()
