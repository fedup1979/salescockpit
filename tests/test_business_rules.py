from sales_cockpit.business_rules import (
    ACTION_STATUSES,
    CONTACT_STATUSES,
    MAIN_ACTION_TYPES,
    PILOTAGE_VALIDATION_CASES,
    RESOLUTION_REASONS,
    SEQUENCE_STEPS,
    SUPPORT_ACTIONS,
    TEMPLATE_REQUEST_STATUSES,
    WORKFLOW_TRANSITIONS,
)


def test_action_workflow_rules_are_structured() -> None:
    action_types = {item["type"] for item in MAIN_ACTION_TYPES}
    assert {"reply", "follow_up", "setting_call", "closing_call"} <= action_types

    statuses = {item["status"] for item in ACTION_STATUSES}
    assert {"planned", "open", "in_progress", "done", "cancelled", "blocked"} <= statuses

    assert any(item["support"] == "Qualification" for item in SUPPORT_ACTIONS)
    assert any(item["support"] == "Statut de contact" for item in SUPPORT_ACTIONS)
    assert len(WORKFLOW_TRANSITIONS) >= 20
    assert all(
        {
            "current_action",
            "trigger",
            "outcome",
            "next_action",
            "owner",
            "due",
            "conversation",
            "required_support",
            "side_effects",
        }
        <= set(item)
        for item in WORKFLOW_TRANSITIONS
    )


def test_pilotage_validation_cases_are_structured() -> None:
    required = {
        "statut",
        "depart",
        "evenement",
        "reponse_systeme",
        "utilisateur",
        "resolution_action",
        "prochaine_action",
    }
    assert len(PILOTAGE_VALIDATION_CASES) >= 30
    assert all(required <= set(item) for item in PILOTAGE_VALIDATION_CASES)
    assert any("Ne plus contacter" in item["depart"] for item in PILOTAGE_VALIDATION_CASES)
    assert any("début du cours" in item["evenement"].lower() for item in PILOTAGE_VALIDATION_CASES)
    assert any(item["statut"] != "Actif" for item in PILOTAGE_VALIDATION_CASES)


def test_validated_business_objects_are_declared() -> None:
    contact_statuses = {item["value"] for item in CONTACT_STATUSES}
    assert {"contact_allowed", "do_not_contact"} <= contact_statuses

    resolution_reasons = {item["value"] for item in RESOLUTION_REASONS}
    assert {"sequence_completed_no_reply", "other", "do_not_contact"} <= resolution_reasons

    request_statuses = {item["value"] for item in TEMPLATE_REQUEST_STATUSES}
    assert {"to_create", "submitted", "approved", "rejected"} <= request_statuses

    sequence_codes = {item["sequence_code"] for item in SEQUENCE_STEPS}
    assert {
        "lead_no_reply",
        "setter_no_next_step",
        "setting_call_not_reached",
        "closing_call_not_reached",
        "closer_will_sign",
        "course_start",
    } <= sequence_codes
