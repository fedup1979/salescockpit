from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.services.front_client import FrontApiError, FrontClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Front import dry-run.")
    parser.add_argument("--query", default="", help="Optional Front search query.")
    parser.add_argument("--limit", type=int, default=1, help="Maximum conversations to inspect.")
    parser.add_argument(
        "--include-messages",
        action="store_true",
        help="Fetch a small message sample for each conversation.",
    )
    parser.add_argument(
        "--messages-limit",
        type=int,
        default=5,
        help="Maximum messages per conversation when --include-messages is set.",
    )
    args = parser.parse_args()

    client = FrontClient.from_settings()
    if args.query.strip():
        conversations = client.search_conversations(args.query, limit=args.limit)
    else:
        conversations = client.list_conversations(limit=args.limit)
    conversations = conversations[: args.limit]

    output: dict[str, Any] = {
        "dry_run": True,
        "writes": 0,
        "conversation_count": len(conversations),
        "conversations": [],
    }
    for conversation in conversations:
        summary = summarize_conversation(conversation)
        if args.include_messages:
            conversation_id = summary["id"]
            messages = client.list_conversation_messages(
                conversation_id,
                limit=args.messages_limit,
            )
            summary["messages"] = [summarize_message(message) for message in messages[: args.messages_limit]]
        output["conversations"].append(summary)

    print(json.dumps(output, ensure_ascii=False, indent=2))


def summarize_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    recipients = conversation.get("recipients") or []
    links = conversation.get("_links") or {}
    return {
        "id": conversation.get("id") or conversation.get("uid") or "",
        "subject": conversation.get("subject") or "",
        "status": conversation.get("status") or "",
        "created_at": conversation.get("created_at"),
        "waiting_since": conversation.get("waiting_since"),
        "assignee": _name_or_id(conversation.get("assignee")),
        "inboxes": [_name_or_id(inbox) for inbox in conversation.get("inboxes") or []],
        "recipients": [
            recipient.get("handle") or recipient.get("name") or ""
            for recipient in recipients
            if isinstance(recipient, dict)
        ],
        "api_link": links.get("self") if isinstance(links, dict) else None,
    }


def summarize_message(message: dict[str, Any]) -> dict[str, Any]:
    body = message.get("text") or message.get("body") or ""
    return {
        "id": message.get("id") or message.get("uid") or "",
        "type": message.get("type") or "",
        "is_inbound": message.get("is_inbound"),
        "created_at": message.get("created_at"),
        "author": _name_or_id(message.get("author")),
        "body_preview": " ".join(str(body).split())[:240],
    }


def _name_or_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return value.get("name") or value.get("email") or value.get("id") or value.get("uid")


if __name__ == "__main__":
    try:
        main()
    except FrontApiError as exc:
        raise SystemExit(f"Front dry-run failed: {exc}") from exc
