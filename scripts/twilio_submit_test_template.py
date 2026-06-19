from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import connect, init_db
from sales_cockpit.store import (
    create_and_submit_twilio_template,
    list_templates,
    sync_twilio_templates,
)


DEFAULT_BODY = (
    "Bonjour {{1}}, merci pour votre demande. "
    "Nous avons bien recu votre message et revenons vers vous rapidement. ESSR"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create and submit one Twilio DEV WhatsApp template from the current env."
    )
    parser.add_argument("--name", default="sc_dev_accuse_reception_fr_001")
    parser.add_argument("--body", default=DEFAULT_BODY)
    parser.add_argument("--language", default="fr")
    parser.add_argument("--category", default="utility")
    parser.add_argument(
        "--placeholders-json",
        default='{"1": "Camille"}',
        help="Example placeholder values used by Twilio, as JSON.",
    )
    parser.add_argument(
        "--force-create",
        action="store_true",
        help="Create another Twilio content item even if a local template with this name exists.",
    )
    args = parser.parse_args()

    init_db()
    admin_id = _first_admin_user_id()
    sync_ok, sync_message = sync_twilio_templates(admin_id)
    print(json.dumps({"sync_ok": sync_ok, "sync_message": sync_message}, ensure_ascii=False))
    if not sync_ok:
        raise SystemExit(1)

    existing = list_templates(args.name)
    if existing and not args.force_create:
        print(json.dumps({"status": "exists", "templates": [_template_summary(t) for t in existing]}, ensure_ascii=False, indent=2))
        return

    try:
        placeholders = json.loads(args.placeholders_json)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid --placeholders-json: {exc}") from exc
    if not isinstance(placeholders, dict):
        raise SystemExit("--placeholders-json must decode to an object.")

    ok, message, template_id = create_and_submit_twilio_template(
        admin_id,
        name=args.name,
        body=args.body,
        language=args.language,
        category=args.category,
        placeholders={str(key): str(value) for key, value in placeholders.items()},
        submit_for_approval=True,
    )
    print(
        json.dumps(
            {"created_ok": ok, "message": message, "template_id": template_id},
            ensure_ascii=False,
            indent=2,
        )
    )
    if not ok:
        raise SystemExit(1)

    sync_twilio_templates(admin_id)
    print(
        json.dumps(
            {"status": "created", "templates": [_template_summary(t) for t in list_templates(args.name)]},
            ensure_ascii=False,
            indent=2,
        )
    )


def _first_admin_user_id() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1"
        ).fetchone()
    if not row:
        raise SystemExit("No admin user found.")
    return int(row["id"])


def _template_summary(template: dict) -> dict:
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "status": template.get("status"),
        "language": template.get("language"),
        "category": template.get("category"),
        "twilio_content_sid": template.get("twilio_content_sid"),
        "twilio_content_type": template.get("twilio_content_type"),
        "last_twilio_sync_at": template.get("last_twilio_sync_at"),
    }


if __name__ == "__main__":
    main()
