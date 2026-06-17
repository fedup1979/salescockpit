from datetime import timedelta

from sales_cockpit.services.whatsapp_rules import calculate_window, utc_now


def test_window_is_open_with_recent_inbound() -> None:
    now = utc_now()
    state = calculate_window(now - timedelta(hours=3), now=now)
    assert state.is_open is True
    assert state.state == "open"


def test_window_is_closed_after_24_hours() -> None:
    now = utc_now()
    state = calculate_window(now - timedelta(hours=25), now=now)
    assert state.is_open is False
    assert state.state == "closed"


def test_window_is_closed_without_inbound() -> None:
    state = calculate_window(None)
    assert state.is_open is False
    assert state.state == "closed"
