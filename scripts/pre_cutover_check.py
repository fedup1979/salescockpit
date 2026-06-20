from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import init_db
from sales_cockpit.store import get_integration_readiness


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sales Cockpit pre-cutover checks.")
    parser.add_argument("--api-base", default="", help="Optional API base URL, e.g. http://127.0.0.1:8602.")
    parser.add_argument("--ui-url", default="", help="Optional Streamlit URL to check.")
    parser.add_argument(
        "--allow-cold-prod",
        action="store_true",
        help="Do not fail only because SchoolDrive/Front are empty. Useful for cold prod preparation.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    readiness = get_integration_readiness()
    checks: list[dict[str, Any]] = []

    if args.api_base:
        checks.append(_check_api(args.api_base, args.timeout))
    if args.ui_url:
        checks.append(_check_ui(args.ui_url, args.timeout))

    readiness_failures = []
    for check in readiness["checks"]:
        state = check.get("state")
        name = check.get("name")
        if state == "danger":
            readiness_failures.append(f"{name}: {check.get('detail')}")
        if state == "warning" and not (
            args.allow_cold_prod and name in {"SchoolDrive", "Front"}
        ):
            readiness_failures.append(f"{name}: {check.get('detail')}")

    workflow = readiness["workflow"]
    if workflow["open_conversations_without_action"]:
        readiness_failures.append(
            f"{workflow['open_conversations_without_action']} active conversation(s) without next action"
        )
    if workflow.get("resolved_conversations_with_action_count"):
        readiness_failures.append(
            f"{workflow['resolved_conversations_with_action_count']} resolved conversation(s) with active action"
        )
    if workflow.get("conversations_with_multiple_main_actions"):
        readiness_failures.append(
            f"{workflow['conversations_with_multiple_main_actions']} conversation(s) with conflicting active actions"
        )
    if not readiness["backup"].get("exists"):
        readiness_failures.append("No backup found")

    checks.append(
        {
            "name": "readiness",
            "ok": not readiness_failures,
            "failures": readiness_failures,
            "readiness_checks": readiness["checks"],
            "workflow": workflow,
            "backup": readiness["backup"],
        }
    )

    result = {
        "environment": settings.environment,
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "summary": _summary(readiness),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_text_result(result)
    if not result["ok"]:
        raise SystemExit(1)


def _check_api(api_base: str, timeout: float) -> dict[str, Any]:
    url = api_base.rstrip("/") + "/health"
    try:
        response = requests.get(url, timeout=timeout)
        payload = response.json()
    except Exception as exc:
        return {"name": "api", "ok": False, "url": url, "error": str(exc)}
    return {
        "name": "api",
        "ok": response.status_code == 200 and payload.get("status") == "ok",
        "url": url,
        "status_code": response.status_code,
        "payload": payload,
    }


def _check_ui(ui_url: str, timeout: float) -> dict[str, Any]:
    try:
        response = requests.get(ui_url, timeout=timeout)
    except Exception as exc:
        return {"name": "ui", "ok": False, "url": ui_url, "error": str(exc)}
    return {
        "name": "ui",
        "ok": response.status_code == 200,
        "url": ui_url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
    }


def _summary(readiness: dict[str, Any]) -> dict[str, Any]:
    return {
        "readiness": [(item["name"], item["state"], item["detail"]) for item in readiness["checks"]],
        "schooldrive_events": readiness["schooldrive"]["status_counts"],
        "schooldrive_leads": readiness["schooldrive"]["lead_count"],
        "front_matches": readiness["front"]["match_counts"],
        "front_migration": readiness["front"]["migration_counts"],
        "front_messages": readiness["front"]["message_count"],
        "twilio_mode": readiness["twilio"]["mode"],
        "twilio_statuses": readiness["twilio"]["status_counts"],
        "workflow": readiness["workflow"],
    }


def _print_text_result(result: dict[str, Any]) -> None:
    status = "OK" if result["ok"] else "KO"
    print(f"Sales Cockpit pre-cutover check: {status}")
    print(f"Environment: {result['environment']}")
    for check in result["checks"]:
        marker = "OK" if check["ok"] else "KO"
        print(f"- {check['name']}: {marker}")
        for failure in check.get("failures") or []:
            print(f"  - {failure}")
        if check.get("error"):
            print(f"  - {check['error']}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
