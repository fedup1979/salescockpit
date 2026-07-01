#!/usr/bin/env python3
"""Synchronize sequence template mappings between two local SQLite databases.

This is an operational helper for cutover preparation. It copies only local
Sales Cockpit mapping rows and resolves target template ids through the real
Twilio Content SID. It never calls Twilio and never edits whatsapp_templates.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MappingKey:
    sequence_code: str
    sequence_step_index: int
    lead_type: str
    course_category: str


@dataclass(frozen=True)
class SourceMapping:
    key: MappingKey
    note: str | None
    twilio_content_sid: str


@dataclass(frozen=True)
class TargetMapping:
    id: int
    key: MappingKey
    template_id: int
    note: str | None
    active: bool


@dataclass(frozen=True)
class PlannedUpsert:
    source: SourceMapping
    target_template_id: int
    action: str


@dataclass(frozen=True)
class SyncPlan:
    source_count: int
    unchanged: int
    upserts: list[PlannedUpsert]
    deactivate: list[TargetMapping]


class SyncError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize active sequence_template_mappings from a source DB to a target DB "
            "by matching whatsapp_templates.twilio_content_sid."
        )
    )
    parser.add_argument("--source-db", required=True, help="Source SQLite DB, e.g. staging.")
    parser.add_argument("--target-db", required=True, help="Target SQLite DB, e.g. prod.")
    parser.add_argument("--apply", action="store_true", help="Write the planned changes.")
    parser.add_argument(
        "--deactivate-extra",
        action="store_true",
        help="Deactivate active target mappings that are absent from the source.",
    )
    parser.add_argument(
        "--expected-active-count",
        type=int,
        help="Abort unless the source has exactly this many active mappings.",
    )
    parser.add_argument(
        "--expected-split",
        action="append",
        default=[],
        metavar="CATEGORY=COUNT",
        help="Abort unless the source has this active mapping count for a category. Can repeat.",
    )
    return parser.parse_args()


def connect(path: str | Path, *, query_only: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if query_only:
        conn.execute("PRAGMA query_only = ON")
    return conn


def is_real_twilio_sid(value: str | None) -> bool:
    sid = (value or "").strip()
    return sid.startswith("HX") and not sid.startswith("HX_MOCK_")


def fetch_source_mappings(conn: sqlite3.Connection) -> list[SourceMapping]:
    rows = conn.execute(
        """
        SELECT
            lower(coalesce(nullif(trim(stm.lead_type), ''), 'all')) AS lead_type,
            upper(coalesce(nullif(trim(stm.course_category), ''), 'all')) AS course_category,
            trim(stm.sequence_code) AS sequence_code,
            stm.sequence_step_index,
            stm.note,
            wt.twilio_content_sid,
            wt.status AS template_status
        FROM sequence_template_mappings stm
        JOIN whatsapp_templates wt ON wt.id = stm.template_id
        WHERE stm.active = 1
        ORDER BY stm.sequence_code, stm.sequence_step_index, stm.lead_type, stm.course_category
        """
    ).fetchall()
    mappings: list[SourceMapping] = []
    seen: set[MappingKey] = set()
    for row in rows:
        key = MappingKey(
            sequence_code=str(row["sequence_code"]),
            sequence_step_index=int(row["sequence_step_index"]),
            lead_type=str(row["lead_type"]),
            course_category=str(row["course_category"]),
        )
        if key in seen:
            raise SyncError(f"Duplicate active source mapping for {format_key(key)}")
        seen.add(key)
        if row["template_status"] != "approved" or not is_real_twilio_sid(row["twilio_content_sid"]):
            raise SyncError(
                f"Source mapping {format_key(key)} is not linked to an approved real Twilio template"
            )
        mappings.append(
            SourceMapping(
                key=key,
                note=row["note"],
                twilio_content_sid=str(row["twilio_content_sid"]),
            )
        )
    return mappings


def fetch_target_mappings(conn: sqlite3.Connection) -> dict[MappingKey, TargetMapping]:
    rows = conn.execute(
        """
        SELECT
            id,
            sequence_code,
            sequence_step_index,
            lead_type,
            course_category,
            template_id,
            note,
            active
        FROM sequence_template_mappings
        """
    ).fetchall()
    mappings: dict[MappingKey, TargetMapping] = {}
    for row in rows:
        key = MappingKey(
            sequence_code=str(row["sequence_code"]),
            sequence_step_index=int(row["sequence_step_index"]),
            lead_type=str(row["lead_type"]),
            course_category=str(row["course_category"]),
        )
        mappings[key] = TargetMapping(
            id=int(row["id"]),
            key=key,
            template_id=int(row["template_id"]),
            note=row["note"],
            active=bool(row["active"]),
        )
    return mappings


def find_target_template_id(conn: sqlite3.Connection, sid: str) -> int:
    rows = conn.execute(
        """
        SELECT id
        FROM whatsapp_templates
        WHERE twilio_content_sid = ?
          AND status = 'approved'
          AND twilio_content_sid LIKE 'HX%'
          AND twilio_content_sid NOT LIKE 'HX_MOCK_%'
        ORDER BY id
        """,
        (sid,),
    ).fetchall()
    if not rows:
        raise SyncError(f"Target DB has no approved real template for Twilio SID {sid}")
    if len(rows) > 1:
        raise SyncError(f"Target DB has multiple approved templates for Twilio SID {sid}")
    return int(rows[0]["id"])


def validate_target_step(conn: sqlite3.Connection, key: MappingKey) -> None:
    row = conn.execute(
        """
        SELECT ss.id
        FROM sequence_steps ss
        WHERE ss.sequence_code = ?
          AND ss.step_index = ?
        """,
        (key.sequence_code, key.sequence_step_index),
    ).fetchone()
    if not row:
        raise SyncError(f"Target DB has no sequence step for {format_key(key)}")


def parse_expected_splits(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in values:
        if "=" not in item:
            raise SyncError(f"Invalid --expected-split value: {item}")
        category, raw_count = item.split("=", 1)
        category = category.strip().upper()
        if not category:
            raise SyncError(f"Invalid --expected-split category: {item}")
        try:
            count = int(raw_count)
        except ValueError as exc:
            raise SyncError(f"Invalid --expected-split count: {item}") from exc
        result[category] = count
    return result


def validate_source_expectations(
    mappings: list[SourceMapping],
    expected_active_count: int | None,
    expected_splits: dict[str, int],
) -> None:
    if expected_active_count is not None and len(mappings) != expected_active_count:
        raise SyncError(
            f"Source has {len(mappings)} active mappings; expected {expected_active_count}"
        )
    counts = Counter(mapping.key.course_category.upper() for mapping in mappings)
    for category, expected in expected_splits.items():
        actual = counts.get(category, 0)
        if actual != expected:
            raise SyncError(f"Source has {actual} active mappings for {category}; expected {expected}")


def build_plan(
    source_conn: sqlite3.Connection,
    target_conn: sqlite3.Connection,
    expected_active_count: int | None = None,
    expected_splits: dict[str, int] | None = None,
) -> SyncPlan:
    source_mappings = fetch_source_mappings(source_conn)
    validate_source_expectations(
        source_mappings,
        expected_active_count,
        expected_splits or {},
    )
    target_mappings = fetch_target_mappings(target_conn)
    source_keys = {mapping.key for mapping in source_mappings}
    unchanged = 0
    upserts: list[PlannedUpsert] = []

    for source in source_mappings:
        validate_target_step(target_conn, source.key)
        target_template_id = find_target_template_id(target_conn, source.twilio_content_sid)
        existing = target_mappings.get(source.key)
        if existing is None:
            upserts.append(PlannedUpsert(source, target_template_id, "insert"))
            continue
        if (
            not existing.active
            or existing.template_id != target_template_id
            or normalize_note(existing.note) != normalize_note(source.note)
        ):
            upserts.append(PlannedUpsert(source, target_template_id, "update"))
        else:
            unchanged += 1

    deactivate = [
        mapping
        for key, mapping in sorted(target_mappings.items(), key=lambda item: format_key(item[0]))
        if mapping.active and key not in source_keys
    ]
    return SyncPlan(
        source_count=len(source_mappings),
        unchanged=unchanged,
        upserts=upserts,
        deactivate=deactivate,
    )


def apply_plan(
    target_conn: sqlite3.Connection,
    plan: SyncPlan,
    deactivate_extra: bool,
) -> None:
    if plan.deactivate and not deactivate_extra:
        raise SyncError(
            "Target has active mappings absent from the source. Re-run with --deactivate-extra "
            "if mirroring the source is intended."
        )
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with target_conn:
        for item in plan.upserts:
            target_conn.execute(
                """
                INSERT INTO sequence_template_mappings (
                    sequence_code,
                    sequence_step_index,
                    lead_type,
                    course_category,
                    template_id,
                    note,
                    active,
                    created_by_user_id,
                    updated_by_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?)
                ON CONFLICT(sequence_code, sequence_step_index, lead_type, course_category)
                DO UPDATE SET
                    template_id = excluded.template_id,
                    note = excluded.note,
                    active = 1,
                    updated_by_user_id = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    item.source.key.sequence_code,
                    item.source.key.sequence_step_index,
                    item.source.key.lead_type,
                    item.source.key.course_category,
                    item.target_template_id,
                    item.source.note,
                    now,
                    now,
                ),
            )
        if deactivate_extra:
            for mapping in plan.deactivate:
                target_conn.execute(
                    """
                    UPDATE sequence_template_mappings
                    SET active = 0,
                        updated_by_user_id = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, mapping.id),
                )


def normalize_note(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def format_key(key: MappingKey) -> str:
    return (
        f"{key.sequence_code}/{key.sequence_step_index}/"
        f"{key.lead_type}/{key.course_category}"
    )


def print_plan(plan: SyncPlan) -> None:
    inserts = sum(1 for item in plan.upserts if item.action == "insert")
    updates = sum(1 for item in plan.upserts if item.action == "update")
    print(f"Source active mappings: {plan.source_count}")
    print(f"Unchanged target mappings: {plan.unchanged}")
    print(f"Planned inserts: {inserts}")
    print(f"Planned updates: {updates}")
    print(f"Planned deactivations: {len(plan.deactivate)}")
    for item in plan.upserts:
        print(f"  {item.action}: {format_key(item.source.key)} -> {item.source.twilio_content_sid}")
    for item in plan.deactivate:
        print(f"  deactivate: {format_key(item.key)}")


def main() -> int:
    args = parse_args()
    expected_splits = parse_expected_splits(args.expected_split)
    source_path = Path(args.source_db)
    target_path = Path(args.target_db)
    if not source_path.exists():
        raise SyncError(f"Source DB not found: {source_path}")
    if not target_path.exists():
        raise SyncError(f"Target DB not found: {target_path}")
    with connect(source_path, query_only=True) as source_conn, connect(target_path) as target_conn:
        plan = build_plan(
            source_conn,
            target_conn,
            expected_active_count=args.expected_active_count,
            expected_splits=expected_splits,
        )
        print_plan(plan)
        if not args.apply:
            print("Dry run only. Re-run with --apply to write changes.")
            return 0
        apply_plan(target_conn, plan, deactivate_extra=args.deactivate_extra)
        print("Applied mapping synchronization.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SyncError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
