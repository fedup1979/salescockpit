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


DEFAULT_LOCAL_URL = "http://127.0.0.1:8000/webhooks/schooldrive/lead-or-presubscription"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay SchoolDrive webhook payload files.")
    parser.add_argument("paths", nargs="+", help="JSON file(s) or directories containing .json payloads.")
    parser.add_argument("--url", default=DEFAULT_LOCAL_URL, help="Webhook URL to POST to.")
    parser.add_argument(
        "--token",
        default="",
        help="Bearer token. Defaults to SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN.",
    )
    parser.add_argument(
        "--expected-environment",
        default="",
        help="Optional guard: refuse payloads whose envelope environment differs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without POSTing.")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop at first failed payload.")
    args = parser.parse_args()

    settings = get_settings()
    token = args.token.strip() or (settings.schooldrive_webhook_token or "").strip()
    if not token and not args.dry_run:
        raise SystemExit("Missing bearer token. Pass --token or set SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN.")

    files = _collect_json_files(args.paths)
    if not files:
        raise SystemExit("No JSON payload files found.")

    results = []
    for file_path in files:
        try:
            for index, payload in enumerate(_load_payloads(file_path), start=1):
                validation = _validate_payload(payload, args.expected_environment)
                if args.dry_run:
                    result = {
                        "file": str(file_path),
                        "index": index,
                        "dry_run": True,
                        **validation,
                    }
                else:
                    result = {
                        "file": str(file_path),
                        "index": index,
                        **validation,
                        **_post_payload(args.url, token, payload, args.timeout),
                    }
                results.append(result)
                if args.stop_on_error and not result.get("ok", False):
                    print(json.dumps(_summary(results), ensure_ascii=False, indent=2))
                    raise SystemExit(1)
        except Exception as exc:
            result = {"file": str(file_path), "ok": False, "error": str(exc)}
            results.append(result)
            if args.stop_on_error:
                print(json.dumps(_summary(results), ensure_ascii=False, indent=2))
                raise SystemExit(1) from exc

    print(json.dumps(_summary(results), ensure_ascii=False, indent=2))
    if any(not result.get("ok", False) for result in results):
        raise SystemExit(1)


def _collect_json_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(sorted(path.glob("*.json")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Payload path not found: {path}")
    return files


def _load_payloads(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError(f"{path} must contain one JSON object or a list of JSON objects.")


def _validate_payload(payload: dict[str, Any], expected_environment: str = "") -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    environment = str(payload.get("environment") or "")
    if expected_environment and environment != expected_environment:
        raise ValueError(
            f"Payload environment is {environment!r}, expected {expected_environment!r}."
        )
    required = {
        "event_id": payload.get("event_id"),
        "occurred_at": payload.get("occurred_at"),
        "environment": environment,
        "data.schooldrive_id": data.get("schooldrive_id"),
        "data.lead_type": data.get("lead_type"),
        "data.aggregated_updated_at": data.get("aggregated_updated_at"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f"Missing required field(s): {', '.join(missing)}.")
    return {
        "ok": True,
        "event_id": str(payload.get("event_id")),
        "environment": environment,
        "schooldrive_id": str(data.get("schooldrive_id")),
        "aggregated_updated_at": str(data.get("aggregated_updated_at")),
    }


def _post_payload(url: str, token: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )
    result: dict[str, Any] = {
        "http_status": response.status_code,
        "ok": 200 <= response.status_code < 300,
    }
    try:
        result["response"] = response.json()
    except ValueError:
        result["response_text"] = response.text[:500]
    return result


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for result in results:
        response = result.get("response")
        status = response.get("status") if isinstance(response, dict) else None
        if status:
            statuses[status] = statuses.get(status, 0) + 1
    return {
        "payload_count": len(results),
        "ok_count": sum(1 for result in results if result.get("ok")),
        "error_count": sum(1 for result in results if not result.get("ok")),
        "response_status_counts": statuses,
        "results": results,
    }


if __name__ == "__main__":
    main()
