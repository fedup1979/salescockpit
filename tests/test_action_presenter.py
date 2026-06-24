from datetime import datetime, timedelta, timezone

from sales_cockpit.ui.action_presenter import build_action_tab_presentation


NOW = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)


def conv(**overrides):
    data = {
        "id": 1,
        "lead_id": 10,
        "status": "open",
        "lead_status": "eligible",
        "contact_status": "contact_allowed",
        "window_is_open": True,
    }
    data.update(overrides)
    return data


def action(action_type, **overrides):
    data = {
        "id": overrides.pop("id", 1),
        "lead_id": 10,
        "conversation_id": 1,
        "type": action_type,
        "status": "open",
        "urgency": "normal",
        "due_at": NOW.isoformat(),
        "assigned_to_user_id": 1,
    }
    data.update(overrides)
    return data


def presentation(current_action, actions=None, conversation=None):
    action_list = actions if actions is not None else ([current_action] if current_action else [])
    return build_action_tab_presentation(conversation or conv(), current_action, action_list, now=NOW)


def test_reply_banner_keeps_planned_call_visible() -> None:
    reply = action("reply", id=1, urgency="urgent")
    call = action("setting_call", id=2, due_at=(NOW + timedelta(days=1)).isoformat())

    result = presentation(reply, [reply, call])

    assert result["banner"]["severity"] == "blue"
    assert result["banner"]["title"] == "Répondre dans Conversation"
    assert result["active_call"]["id"] == call["id"]
    assert "appel déjà planifié" in result["banner"]["body"]


def test_followup_due_and_blocked_banners() -> None:
    followup = action("follow_up")
    blocked = action("follow_up", status="blocked", blocked_reason="template_missing")

    due_result = presentation(followup)
    blocked_result = presentation(blocked)

    assert due_result["banner"]["title"] == "Envoyer la relance dans Conversation"
    assert due_result["banner"]["severity"] == "blue"
    assert blocked_result["banner"]["title"] == "Relance bloquée"
    assert blocked_result["banner"]["severity"] == "orange"


def test_call_future_is_visible_but_documentation_is_disabled_until_due() -> None:
    future_call = action("setting_call", due_at=(NOW + timedelta(hours=2)).isoformat())
    due_call = action("closing_call", due_at=(NOW - timedelta(minutes=5)).isoformat())

    future_result = presentation(future_call)
    due_result = presentation(due_call)

    assert future_result["sections"]["schedule_call"]["enabled"] is True
    assert future_result["sections"]["document_call"]["enabled"] is False
    assert "plus tard" in future_result["sections"]["document_call"]["reason"]
    assert due_result["sections"]["document_call"]["enabled"] is True
    assert due_result["sections"]["document_call"]["action"]["type"] == "closing_call"


def test_manual_reprise_sections_and_skip_section() -> None:
    reprise = action(
        "manual_reprise_closer",
        sequence_code="post_closing_undecided",
        sequence_step_index=1,
    )

    result = presentation(reprise)

    assert result["banner"]["title"] == "Reprise manuelle closer"
    assert result["sections"]["document_manual_reprise"]["enabled"] is True
    assert result["sections"]["skip_step"]["enabled"] is True


def test_terminal_contact_blocks_calls_but_allows_manual_reprise_request() -> None:
    review = action("contact_review")

    result = presentation(review, conversation=conv(contact_status="do_not_contact"))

    assert result["banner"]["severity"] == "orange"
    assert result["sections"]["schedule_call"]["enabled"] is False
    assert result["sections"]["request_manual_reprise"]["enabled"] is True
    assert result["sections"]["skip_step"]["enabled"] is False


def test_open_without_action_and_other_action_are_red_anomalies() -> None:
    no_action = presentation(None, [])
    other = presentation(action("other"))

    assert no_action["banner"]["severity"] == "red"
    assert "aucune prochaine action" in no_action["banner"]["body"]
    assert other["banner"]["severity"] == "red"
    assert other["banner"]["title"] == "Action obsolète"


def test_resolved_conversation_with_active_action_is_system_inconsistency() -> None:
    result = presentation(action("follow_up"), conversation=conv(status="resolved"))

    assert result["banner"]["severity"] == "red"
    assert result["sections"]["request_manual_reprise"]["enabled"] is False
