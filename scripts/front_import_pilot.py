from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import init_db
from sales_cockpit.services.front_client import FrontApiError, FrontClient
from sales_cockpit.services.front_import import preview_front_conversation, upsert_front_history


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Front history import pilot.")
    parser.add_argument("--query", default="", help="Optional Front search query.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum conversations to inspect.")
    parser.add_argument(
        "--include-messages",
        action="store_true",
        help="Fetch message samples for each conversation.",
    )
    parser.add_argument(
        "--messages-limit",
        type=int,
        default=5,
        help="Maximum messages per conversation when --include-messages is set.",
    )
    parser.add_argument("--write", action="store_true", help="Store the pilot result in front_* tables.")
    parser.add_argument(
        "--attach-history",
        action="store_true",
        help="With --write, also attach matched Front messages to the Sales Cockpit thread as front_history.",
    )
    parser.add_argument("--max-retries", type=int, default=0, help="Maximum Front 429 retries.")
    parser.add_argument(
        "--max-retry-delay",
        type=float,
        default=5.0,
        help="Maximum seconds to wait for one Front retry.",
    )
    parser.add_argument(
        "--allow-large",
        action="store_true",
        help="Allow --limit above 10. Keep disabled unless doing a controlled batch.",
    )
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be at least 1.")
    if args.limit > 10 and not args.allow_large:
        raise SystemExit("Refusing to read more than 10 conversations without --allow-large.")
    if args.attach_history and not args.write:
        raise SystemExit("--attach-history requires --write.")

    settings = get_settings()
    if not settings.front_api_token:
        raise FrontApiError("Configure SALES_COCKPIT_FRONT_API_TOKEN.")
    init_db()
    client = FrontClient(
        api_token=settings.front_api_token,
        max_retries=args.max_retries,
        max_retry_delay_seconds=args.max_retry_delay,
    )
    conversations = (
        client.search_conversations(args.query, limit=args.limit)
        if args.query.strip()
        else client.list_conversations(limit=args.limit)
    )

    output: dict[str, Any] = {
        "dry_run": not args.write,
        "writes": 0,
        "attach_history": bool(args.attach_history),
        "conversation_count": len(conversations),
        "conversations": [],
    }
    for conversation in conversations:
        conversation_id = str(conversation.get("id") or conversation.get("uid") or "").strip()
        messages = []
        if args.include_messages and conversation_id:
            messages = client.list_conversation_messages(conversation_id, limit=args.messages_limit)
        if args.write:
            result = upsert_front_history(
                conversation,
                messages=messages,
                attach_history=args.attach_history,
            )
            output["writes"] += 1 + result["messages_created"] + result["messages_attached"]
        else:
            result = preview_front_conversation(conversation, messages=messages)
        output["conversations"].append(result)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except FrontApiError as exc:
        raise SystemExit(f"Front pilot failed: {exc}") from exc
