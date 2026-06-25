from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect, seed_initial_data
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
    parser.add_argument(
        "--strict-prod",
        action="store_true",
        help="Fail unless production is ready for the real WhatsApp cutover.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    settings = get_settings()
    if not args.strict_prod:
        seed_initial_data()
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
    if workflow.get("obsolete_sequence_reference_count"):
        readiness_failures.append(
            f"{workflow['obsolete_sequence_reference_count']} obsolete post_call_undecided reference(s)"
        )
    if workflow.get("active_followup_missing_step_count"):
        readiness_failures.append(
            f"{workflow['active_followup_missing_step_count']} active follow-up(s) with missing sequence step"
        )
    if not readiness["backup"].get("exists"):
        readiness_failures.append("No backup found")
    if args.strict_prod:
        readiness_failures.extend(
            _strict_prod_failures(
                settings=settings,
                readiness=readiness,
                api_base=args.api_base,
                ui_url=args.ui_url,
                allow_cold_prod=args.allow_cold_prod,
            )
        )

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


def _strict_prod_failures(
    settings: Any,
    readiness: dict[str, Any],
    api_base: str,
    ui_url: str,
    allow_cold_prod: bool = False,
) -> list[str]:
    failures: list[str] = []
    environment = (settings.environment or "").lower()
    if environment not in {"prod", "production"}:
        failures.append("--strict-prod must run against SALES_COCKPIT_ENVIRONMENT=prod/production")
    if settings.seed_demo_data:
        failures.append("Production strict check requires SALES_COCKPIT_SEED_DEMO_DATA=false")
    if _weak_seed_password(settings.seed_password):
        failures.append("SALES_COCKPIT_SEED_PASSWORD must not use the default or a weak value")

    if not api_base or not _is_https_url(api_base):
        failures.append("--api-base must be a public HTTPS URL in strict prod")
    if not ui_url or not _is_https_url(ui_url):
        failures.append("--ui-url must be a public HTTPS URL in strict prod")

    for name, value in {
        "SALES_COCKPIT_API_TOKEN": settings.api_token,
        "SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN": settings.schooldrive_webhook_token,
        "SALES_COCKPIT_TWILIO_ACCOUNT_SID": settings.twilio_account_sid,
        "SALES_COCKPIT_TWILIO_AUTH_TOKEN": settings.twilio_auth_token,
    }.items():
        if _bad_secret(value):
            failures.append(f"{name} is missing or looks like a placeholder")

    twilio = readiness["twilio"]
    if (settings.twilio_mode or "").lower() != "live":
        failures.append("Twilio mode must be live for strict prod")
    if not (settings.twilio_whatsapp_sender or settings.twilio_messaging_service_sid):
        failures.append("Twilio sender or messaging service SID is required")
    if not settings.twilio_validate_signature:
        failures.append("Twilio signature validation must be enabled")
    if not _is_https_url(twilio.get("webhook_url")):
        failures.append("Twilio inbound webhook URL must be HTTPS")
    if not _is_https_url(twilio.get("status_callback_url")):
        failures.append("Twilio status callback URL must be HTTPS")

    backup = readiness["backup"]
    if not backup.get("exists") or int(backup.get("size_bytes") or 0) <= 0:
        failures.append("A non-empty backup is required")
    elif _backup_age_hours(backup.get("updated_at") or "") > 24:
        failures.append("Latest backup is older than 24 hours")

    workflow = readiness["workflow"]
    if workflow.get("blocked_action_count"):
        failures.append(f"{workflow['blocked_action_count']} blocked action(s) remain")
    if workflow.get("pending_template_request_count"):
        failures.append(f"{workflow['pending_template_request_count']} pending template request(s) remain")
    old_pending_send_count = _old_pending_send_count()
    if old_pending_send_count:
        failures.append(f"{old_pending_send_count} old pending_send outbound message(s) remain")
    if not allow_cold_prod and not _schooldrive_ar_sent_validated():
        failures.append("SchoolDrive AR sent validation is missing")

    missing_mappings = _strict_missing_template_mapping_count()
    if missing_mappings:
        failures.append(f"{missing_mappings} active follow-up step/category combination(s) lack a real approved template mapping")

    return failures


def _bad_secret(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return not normalized or normalized in {"change_me", "changeme", "todo", "placeholder", "secret"}


def _weak_seed_password(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return (
        not normalized
        or normalized in {"changeme", "change_me", "changeme!2026", "password", "password123"}
        or len(normalized) < 14
    )


def _is_https_url(value: str | None) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _backup_age_hours(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600


def _strict_missing_template_mapping_count() -> int:
    with connect() as conn:
        row = conn.execute(
            """
            WITH required AS (
                SELECT
                    ss.sequence_code,
                    ss.step_index,
                    cc.course_category,
                    lt.lead_type
                FROM sequence_steps ss
                JOIN sequences s ON s.code = ss.sequence_code AND s.active = 1
                JOIN course_categories cc ON cc.active = 1
                CROSS JOIN (
                    SELECT 'lead' AS lead_type
                    UNION ALL
                    SELECT 'presubscription' AS lead_type
                ) lt
                WHERE ss.active = 1
                  AND ss.action_type = 'follow_up'
                  AND ss.requires_template = 1
            )
            SELECT COUNT(*) AS count
            FROM required r
            WHERE NOT EXISTS (
                SELECT 1
                FROM sequence_template_mappings stm
                JOIN whatsapp_templates wt ON wt.id = stm.template_id
                WHERE stm.active = 1
                  AND stm.sequence_code = r.sequence_code
                  AND stm.sequence_step_index = r.step_index
                  AND stm.lead_type IN ('all', r.lead_type)
                  AND stm.course_category IN ('all', r.course_category)
                  AND wt.status = 'approved'
                  AND wt.twilio_content_sid IS NOT NULL
                  AND wt.twilio_content_sid LIKE 'HX%'
                  AND wt.twilio_content_sid NOT LIKE 'HX_MOCK_%'
            )
            """
        ).fetchone()
    return int(row["count"] if row else 0)


def _old_pending_send_count() -> int:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM messages
            WHERE direction = 'outbound'
              AND channel = 'whatsapp_twilio'
              AND twilio_status = 'pending_send'
              AND datetime(created_at) < datetime('now', '-15 minutes')
            """
        ).fetchone()
    return int(row["count"] if row else 0)


def _schooldrive_ar_sent_validated() -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM schooldrive_whatsapp_autoresponders
            WHERE status = 'sent'
              AND sent_at IS NOT NULL
            """
        ).fetchone()
    return int(row["count"] if row else 0) > 0


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
        "security": readiness.get("security", {}),
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
