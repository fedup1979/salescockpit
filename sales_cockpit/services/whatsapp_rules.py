from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


WINDOW_HOURS = 24


@dataclass(frozen=True)
class WindowState:
    state: str
    is_open: bool
    last_inbound_at: datetime | None
    closes_at: datetime | None
    reason: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    dt = value or utc_now()
    return dt.astimezone(timezone.utc).isoformat()


def calculate_window(
    last_inbound_at: str | datetime | None, now: datetime | None = None
) -> WindowState:
    inbound_at = parse_dt(last_inbound_at)
    current = now or utc_now()
    if inbound_at is None:
        return WindowState(
            state="closed",
            is_open=False,
            last_inbound_at=None,
            closes_at=None,
            reason="No inbound WhatsApp message is recorded.",
        )

    closes_at = inbound_at + timedelta(hours=WINDOW_HOURS)
    if current < closes_at:
        return WindowState(
            state="open",
            is_open=True,
            last_inbound_at=inbound_at,
            closes_at=closes_at,
            reason="The customer service window is open.",
        )

    return WindowState(
        state="closed",
        is_open=False,
        last_inbound_at=inbound_at,
        closes_at=closes_at,
        reason="The 24-hour customer service window is closed.",
    )
