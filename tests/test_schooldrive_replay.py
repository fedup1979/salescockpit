from __future__ import annotations

import json

from scripts.schooldrive_replay_payloads import _collect_json_files, _load_payloads, _validate_payload


def test_load_payloads_accepts_one_object(tmp_path) -> None:
    payload = _payload("evt_1")
    file_path = tmp_path / "payload.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")

    assert _load_payloads(file_path) == [payload]


def test_load_payloads_accepts_list(tmp_path) -> None:
    payloads = [_payload("evt_1"), _payload("evt_2")]
    file_path = tmp_path / "payloads.json"
    file_path.write_text(json.dumps(payloads), encoding="utf-8")

    assert _load_payloads(file_path) == payloads


def test_collect_json_files_from_directory(tmp_path) -> None:
    first = tmp_path / "01.json"
    second = tmp_path / "02.json"
    ignored = tmp_path / "notes.md"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    ignored.write_text("ignore", encoding="utf-8")

    assert _collect_json_files([str(tmp_path)]) == [first, second]


def test_validate_payload_enforces_expected_environment() -> None:
    payload = _payload("evt_1", environment="production")

    try:
        _validate_payload(payload, expected_environment="staging")
    except ValueError as exc:
        assert "expected 'staging'" in str(exc)
    else:
        raise AssertionError("Environment mismatch should fail.")


def test_validate_payload_returns_summary_fields() -> None:
    summary = _validate_payload(_payload("evt_1"), expected_environment="staging")

    assert summary["ok"] is True
    assert summary["event_id"] == "evt_1"
    assert summary["schooldrive_id"] == "lead:123"


def _payload(event_id: str, environment: str = "staging") -> dict:
    return {
        "schema_version": "1.0",
        "event_id": event_id,
        "occurred_at": "2026-06-18T08:26:19Z",
        "environment": environment,
        "data": {
            "schooldrive_id": "lead:123",
            "lead_type": "lead",
            "aggregated_updated_at": "2026-06-18T08:30:08Z",
        },
    }
