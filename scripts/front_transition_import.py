from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import init_db
from sales_cockpit.services.front_client import FrontApiError, FrontClient
from sales_cockpit.services.front_import import (
    FRONT_ACTIVE_STATUSES,
    classify_front_migration,
    extract_front_phone,
    import_front_transition_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Front WhatsApp conversations as manual transition threads, outside V1 flows."
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Front search query. Defaults to SALES_COCKPIT_FRONT_IMPORT_QUERY, then recent conversations.",
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum Front conversations to fetch.")
    parser.add_argument("--messages-limit", type=int, default=500, help="Maximum messages per conversation.")
    parser.add_argument(
        "--import-run-id",
        default="",
        help="Stable id for this batch. Required for repeatable purge/re-import; generated if omitted.",
    )
    parser.add_argument("--write", action="store_true", help="Write to Sales Cockpit. Default is dry-run.")
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help="Allow --limit above 50. Use for controlled staged batches only.",
    )
    parser.add_argument("--max-retries", type=int, default=2, help="Maximum Front 429 retries.")
    parser.add_argument(
        "--max-retry-delay",
        type=float,
        default=15.0,
        help="Maximum seconds to wait for one Front retry.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be at least 1.")
    if args.limit > 50 and not args.allow_large:
        raise SystemExit("Refusing to fetch more than 50 conversations without --allow-large.")
    if args.messages_limit < 1:
        raise SystemExit("--messages-limit must be at least 1.")

    settings = get_settings()
    if not settings.front_api_token:
        raise FrontApiError("Configure SALES_COCKPIT_FRONT_API_TOKEN.")

    client = FrontClient(
        api_token=settings.front_api_token,
        max_retries=args.max_retries,
        max_retry_delay_seconds=args.max_retry_delay,
    )
    query = (args.query if args.query is not None else settings.front_import_query) or ""
    conversations = (
        client.search_conversations(query, limit=args.limit)
        if query.strip()
        else client.list_conversations(limit=args.limit)
    )
    records = [
        {
            "conversation": conversation,
            "messages": client.list_conversation_messages(
                _front_id(conversation),
                limit=args.messages_limit,
            ),
        }
        for conversation in conversations
        if _front_id(conversation)
    ]
    import_run_id = args.import_run_id.strip() or _default_import_run_id()
    preview = _preview_records(records, import_run_id)
    output: dict[str, Any] = {
        "dry_run": not args.write,
        "import_run_id": import_run_id,
        "query": query,
        "conversation_count": len(records),
        **preview,
    }
    if args.write:
        init_db()
        output["write_result"] = import_front_transition_records(records, import_run_id)

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    print("Front transition import")
    print(f"Dry run: {output['dry_run']}")
    print(f"Import run id: {import_run_id}")
    print(f"Conversations fetched: {len(records)}")
    print(f"Groups: {preview['group_count']}")
    print(f"Open groups: {preview['open_group_count']}")
    print(f"Resolved groups: {preview['resolved_group_count']}")
    print(f"Messages fetched: {preview['message_count']}")
    if args.write:
        print(f"Write result: {json.dumps(output['write_result'], ensure_ascii=False)}")
    print()
    for row in preview["groups"][:30]:
        print(
            f"{row['status']} | {row['front_group_key']} | "
            f"{row['conversation_count']} conv | {row['message_count']} msg | "
            f"{row.get('phone_e164') or 'no phone'}"
        )


def _preview_records(records: list[dict[str, Any]], import_run_id: str) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    message_count = 0
    for record in records:
        conversation = record.get("conversation") or {}
        messages = record.get("messages") or []
        message_count += len(messages)
        phone = extract_front_phone(conversation, messages)
        front_conversation_id = _front_id(conversation)
        group_key = f"phone:{phone}" if phone else f"front:{front_conversation_id}"
        migration = classify_front_migration(conversation, messages)
        status = str(conversation.get("status") or "").strip().lower()
        is_open = status in FRONT_ACTIVE_STATUSES or migration.get("migration_status") in {
            "active",
            "manual_review",
        }
        group = groups.setdefault(
            group_key,
            {
                "front_group_key": group_key,
                "phone_e164": phone,
                "conversation_ids": [],
                "conversation_count": 0,
                "message_count": 0,
                "is_open": False,
            },
        )
        group["conversation_ids"].append(front_conversation_id)
        group["conversation_count"] += 1
        group["message_count"] += len(messages)
        group["is_open"] = bool(group["is_open"] or is_open)
        if phone and not group.get("phone_e164"):
            group["phone_e164"] = phone

    rows = sorted(
        (
            {
                **group,
                "status": "open" if group["is_open"] else "resolved",
                "import_run_id": import_run_id,
            }
            for group in groups.values()
        ),
        key=lambda row: (row["status"] != "open", row["front_group_key"]),
    )
    return {
        "group_count": len(rows),
        "open_group_count": sum(1 for row in rows if row["status"] == "open"),
        "resolved_group_count": sum(1 for row in rows if row["status"] == "resolved"),
        "message_count": message_count,
        "groups": rows,
    }


def _front_id(payload: dict[str, Any]) -> str:
    return str(payload.get("id") or payload.get("uid") or "").strip()


def _default_import_run_id() -> str:
    return "front-transition-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


if __name__ == "__main__":
    try:
        main()
    except FrontApiError as exc:
        raise SystemExit(f"Front transition import failed: {exc}") from exc
