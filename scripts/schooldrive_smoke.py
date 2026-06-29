from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.config import get_settings
from sales_cockpit.db import connect


DEFAULT_LOCAL_URL = "http://127.0.0.1:8000/webhooks/schooldrive/lead-or-presubscription"


@dataclass(frozen=True)
class SmokeStep:
    name: str
    payload: dict[str, Any]
    expected_status: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a synthetic SchoolDrive webhook smoke test."
    )
    parser.add_argument("--url", default=DEFAULT_LOCAL_URL, help="Webhook URL to POST to.")
    parser.add_argument(
        "--token",
        default="",
        help="Bearer token. Defaults to SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN.",
    )
    parser.add_argument(
        "--environment",
        default="staging",
        help="Payload environment value, normally staging or production.",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="Optional stable run id. Defaults to a unique timestamp-based id.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payloads without POSTing.")
    parser.add_argument(
        "--db-check",
        action="store_true",
        help="Also verify local DB side effects. Use only when running beside the target app DB.",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    args = parser.parse_args()

    settings = get_settings()
    token = args.token.strip() or (settings.schooldrive_webhook_token or "").strip()
    if not token and not args.dry_run:
        raise SystemExit("Missing bearer token. Pass --token or set SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN.")

    now = datetime.now(UTC).replace(microsecond=0)
    run_id = args.run_id.strip() or now.strftime("smoke-%Y%m%dT%H%M%SZ")
    steps = build_smoke_steps(run_id=run_id, environment=args.environment, base_time=now)

    if args.dry_run:
        print(json.dumps([step.payload for step in steps], ensure_ascii=False, indent=2))
        return

    results = [_post_step(args.url, token, step, args.timeout) for step in steps]
    if args.db_check:
        results.append(_db_check(run_id))

    summary = {
        "run_id": run_id,
        "ok_count": sum(1 for result in results if result["ok"]),
        "error_count": sum(1 for result in results if not result["ok"]),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if any(not result["ok"] for result in results):
        raise SystemExit(1)


def build_smoke_steps(
    *,
    run_id: str,
    environment: str,
    base_time: datetime,
) -> list[SmokeStep]:
    initial_at = base_time - timedelta(hours=4)
    sent_at = base_time - timedelta(hours=3)
    later_at = base_time - timedelta(hours=2)

    lead_id = f"lead:{run_id}-lead"
    presub_sent_id = f"subscription:{run_id}-presub-sent"
    presub_queued_id = f"subscription:{run_id}-presub-queued"
    archive_id = f"subscription:{run_id}-archive"

    lead_initial = _payload(
        event_id=f"evt_{run_id}_01_initial",
        occurred_at=initial_at + timedelta(minutes=1),
        aggregated_updated_at=initial_at,
        environment=environment,
        schooldrive_id=lead_id,
        lead_type="lead",
        first_name="Smoke",
        last_name="Initial",
        phone="+41790009901",
        course_category="FSM",
        course_name=None,
        status="lead",
        autoresponders=[],
    )
    lead_sent = _payload(
        event_id=f"evt_{run_id}_02_sent",
        occurred_at=sent_at + timedelta(minutes=1),
        aggregated_updated_at=sent_at,
        environment=environment,
        schooldrive_id=lead_id,
        lead_type="lead",
        first_name="Smoke",
        last_name="Sent",
        phone="+41790009901",
        course_category="FSM",
        course_name=None,
        status="lead",
        autoresponders=[
            _autoresponder(
                message_id=f"armsg:{run_id}:lead-sent",
                short_name="MKT-FSM-LN-BT-01",
                status="sent",
                sent_at=sent_at,
                body="Bonjour Smoke, merci pour votre demande FSM.",
            )
        ],
    )
    stale_replay = _copy_with(
        lead_initial,
        event_id=f"evt_{run_id}_03_stale",
        occurred_at=(sent_at + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    )
    duplicate_sent = lead_sent

    presub_sent = _payload(
        event_id=f"evt_{run_id}_05_presub_sent",
        occurred_at=later_at + timedelta(minutes=1),
        aggregated_updated_at=later_at,
        environment=environment,
        schooldrive_id=presub_sent_id,
        lead_type="presubscription",
        first_name="Smoke",
        last_name="Presub",
        phone="+41790009902",
        course_category="APP",
        course_name="APP VISIO SMOKE",
        start_date=(base_time + timedelta(days=20)).date().isoformat(),
        status="pre_subscription",
        autoresponders=[
            _autoresponder(
                message_id=f"armsg:{run_id}:presub-sent",
                short_name="mkt_app_ln_subs_01",
                whatsapp_template_id="HX_SMOKE_SENT",
                variables={"prenom": "Smoke"},
                status="sent",
                sent_at=later_at,
                body="Bonjour Smoke, merci pour votre preinscription APP.",
            )
        ],
    )
    presub_queued = _payload(
        event_id=f"evt_{run_id}_06_presub_queued",
        occurred_at=base_time + timedelta(minutes=1),
        aggregated_updated_at=base_time,
        environment=environment,
        schooldrive_id=presub_queued_id,
        lead_type="presubscription",
        first_name="Smoke",
        last_name="Queued",
        phone="+41790009903",
        course_category="APP",
        course_name="APP VISIO SMOKE",
        start_date=(base_time + timedelta(days=20)).date().isoformat(),
        status="pre_subscription",
        autoresponders=[
            _autoresponder(
                message_id=f"armsg:{run_id}:presub-queued",
                short_name="mkt_app_ln_subs_01",
                whatsapp_template_id="HX_SMOKE_QUEUED",
                variables={"prenom": "Smoke"},
                status="queued",
                sent_at=None,
                body=None,
            )
        ],
    )
    archive_initial = _payload(
        event_id=f"evt_{run_id}_07_archive_initial",
        occurred_at=base_time + timedelta(minutes=2),
        aggregated_updated_at=base_time + timedelta(minutes=2),
        environment=environment,
        schooldrive_id=archive_id,
        lead_type="presubscription",
        first_name="Smoke",
        last_name="Archive",
        phone="+41790009904",
        course_category="APP",
        course_name="APP VD SMOKE",
        start_date=(base_time + timedelta(days=40)).date().isoformat(),
        status="pre_subscription",
        autoresponders=[
            _autoresponder(
                message_id=f"armsg:{run_id}:archive-sent",
                short_name="mkt_app_ln_subs_01",
                whatsapp_template_id="HX_SMOKE_ARCHIVE",
                variables={"prenom": "Smoke"},
                status="sent",
                sent_at=base_time + timedelta(minutes=2),
                body="Bonjour Smoke, merci pour votre preinscription archive.",
            )
        ],
    )
    archive_update = _copy_with(
        archive_initial,
        event_id=f"evt_{run_id}_08_archive_update",
        occurred_at=(base_time + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
        aggregated_updated_at=(base_time + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
        is_archived=True,
        archived_at=(base_time + timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
        archive_reason="Synthetic smoke archive",
    )

    return [
        SmokeStep("lead initial without WhatsApp", lead_initial, "ignored"),
        SmokeStep("lead updated with sent WhatsApp", lead_sent, "created"),
        SmokeStep("older lead replay ignored", stale_replay, "ignored"),
        SmokeStep("duplicate event ignored by event_id", duplicate_sent, "duplicate"),
        SmokeStep("presubscription with sent WhatsApp", presub_sent, "created"),
        SmokeStep("presubscription with queued WhatsApp", presub_queued, "created"),
        SmokeStep("archived presubscription initial", archive_initial, "created"),
        SmokeStep("archived presubscription update", archive_update, "updated"),
    ]


def _payload(
    *,
    event_id: str,
    occurred_at: datetime | str,
    aggregated_updated_at: datetime | str,
    environment: str,
    schooldrive_id: str,
    lead_type: str,
    first_name: str,
    last_name: str,
    phone: str,
    course_category: str,
    course_name: str | None,
    status: str,
    autoresponders: list[dict[str, Any]],
    start_date: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "2.1",
        "event_id": event_id,
        "occurred_at": _iso(occurred_at),
        "environment": environment,
        "data": {
            "schooldrive_id": schooldrive_id,
            "lead_type": lead_type,
            "url": _schooldrive_url(schooldrive_id),
            "aggregated_updated_at": _iso(aggregated_updated_at),
            "is_archived": False,
            "archived_at": None,
            "archive_reason": None,
            "signed": False,
            "signed_at": None,
            "person": {
                "title": "mrs",
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
            },
            "do_not_contact": {"blocked": False, "reasons": []},
            "course": {
                "id": _smoke_course_id(schooldrive_id, course_name),
                "category": {
                    "id": None,
                    "short_name": course_category,
                    "name": course_category,
                },
                "short_name": course_name,
                "name": course_name,
                "start_date": start_date,
                "seats_total": 100 if course_name else None,
                "seats_occupied": 10 if course_name else None,
                "seats_available": 90 if course_name else None,
                "is_full": False if course_name else None,
            },
            "status": status,
            "whatsapp_autoresponders": autoresponders,
            "related_subscriptions": [],
        },
    }


def _autoresponder(
    *,
    message_id: str,
    short_name: str,
    status: str,
    sent_at: datetime | None,
    body: str | None,
    whatsapp_template_id: str = "HX_SMOKE",
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "autoresponder_id": 9000,
        "short_name": short_name,
        "whatsapp_template_id": whatsapp_template_id,
        "whatsapp_template_variables_mapping": variables or {"1": "Smoke"},
        "whatsapp_send_body": body,
        "status": status,
        "sent_at": _iso(sent_at) if sent_at else None,
    }


def _copy_with(payload: dict[str, Any], **updates: Any) -> dict[str, Any]:
    copy = json.loads(json.dumps(payload))
    for key, value in updates.items():
        if key in {"event_id", "occurred_at", "environment", "schema_version"}:
            copy[key] = value
        else:
            copy["data"][key] = value
    return copy


def _post_step(url: str, token: str, step: SmokeStep, timeout: float) -> dict[str, Any]:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=step.payload,
        timeout=timeout,
    )
    try:
        response_body: Any = response.json()
    except ValueError:
        response_body = response.text[:500]
    actual_status = response_body.get("status") if isinstance(response_body, dict) else None
    return {
        "name": step.name,
        "event_id": step.payload["event_id"],
        "schooldrive_id": step.payload["data"]["schooldrive_id"],
        "http_status": response.status_code,
        "expected_status": step.expected_status,
        "actual_status": actual_status,
        "ok": 200 <= response.status_code < 300 and actual_status == step.expected_status,
        "response": response_body,
    }


def _db_check(run_id: str) -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                l.schooldrive_lead_id,
                l.schooldrive_is_archived,
                c.status AS conversation_status,
                COUNT(t.id) FILTER (WHERE t.status IN ('planned', 'open', 'in_progress')) AS open_actions,
                COUNT(a.id) AS autoresponder_count,
                MAX(a.status) AS autoresponder_status
            FROM leads l
            JOIN conversations c ON c.lead_id = l.id
            LEFT JOIN tasks t ON t.lead_id = l.id
            LEFT JOIN schooldrive_whatsapp_autoresponders a ON a.lead_id = l.id
            WHERE l.schooldrive_lead_id LIKE ?
            GROUP BY l.id, c.id
            ORDER BY l.schooldrive_lead_id
            """,
            (f"%{run_id}%",),
        ).fetchall()
    issues = []
    for row in rows:
        schooldrive_id = row["schooldrive_lead_id"]
        if "queued" in schooldrive_id and row["open_actions"]:
            issues.append(f"{schooldrive_id} should not have an open action for queued WhatsApp.")
        if "archive" in schooldrive_id and row["conversation_status"] != "resolved":
            issues.append(f"{schooldrive_id} should be resolved after archive.")
    return {
        "name": "local DB side effects",
        "ok": bool(rows) and not issues,
        "row_count": len(rows),
        "issues": issues,
        "rows": [dict(row) for row in rows],
    }


def _schooldrive_url(schooldrive_id: str) -> str:
    kind, raw_id = schooldrive_id.split(":", 1)
    if kind == "lead":
        return f"https://schooldrive.essr.ch/sd/customers/leads(p1:sd/customers/leads/view/{raw_id})"
    return (
        "https://schooldrive.essr.ch/sd/customers/customers"
        f"(p1:sd/customers/customers/subscription/view/{raw_id})"
    )


def _smoke_course_id(schooldrive_id: str, course_name: str | None) -> str | None:
    if not course_name:
        return None
    return f"smoke-course-{schooldrive_id.replace(':', '-')}"


def _iso(value: datetime | str) -> str:
    if isinstance(value, str):
        return value
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
