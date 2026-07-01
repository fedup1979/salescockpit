from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sales_cockpit.services.whatsapp_rules import parse_dt, utc_now


ACTIVE_ACTION_STATUSES = {"open", "in_progress", "planned", "blocked"}
CALL_ACTION_TYPES = {"setting_call", "closing_call"}
MANUAL_REPRISE_ACTION_TYPES = {"manual_reprise_setter", "manual_reprise_closer"}
FRONT_TRANSITION_REVIEW_ACTION = "front_transition_review"
FRONT_TRANSITION_FOLLOW_UP_ACTION = "front_transition_follow_up"
TERMINAL_QUALIFICATION_STATUSES = {"not_relevant", "signed"}
STOP_CONTACT_STATUSES = {"do_not_contact"}
SKIPPABLE_FLOW_ACTION_TYPES = {"follow_up", "manual_reprise_setter", "manual_reprise_closer"}


def build_action_tab_presentation(
    conv: dict[str, Any],
    current_action: dict[str, Any] | None,
    actions: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utc_now()
    active_actions = [action for action in actions if action.get("status") in ACTIVE_ACTION_STATUSES]
    active_call = first_active_call(actions)
    active_reprise = first_active_reprise(actions)
    terminal_reason = terminal_block_reason(conv)
    banner = action_banner(
        conv,
        current_action,
        active_actions=active_actions,
        active_call=active_call,
        terminal_reason=terminal_reason,
        now=now,
    )
    sections = {
        "schedule_call": schedule_call_section(conv, active_call, terminal_reason),
        "document_call": document_call_section(conv, active_call, terminal_reason, now),
        "request_manual_reprise": request_manual_reprise_section(conv),
        "document_manual_reprise": document_manual_reprise_section(conv, current_action, active_reprise),
        "skip_step": skip_step_section(conv, current_action, terminal_reason),
    }
    return {
        "banner": banner,
        "active_call": active_call,
        "active_reprise": active_reprise,
        "sections": sections,
        "system_action": (current_action or {}).get("type"),
        "terminal_reason": terminal_reason,
        "active_action_count": len(active_actions),
    }


def first_active_call(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    calls = [
        action for action in actions
        if action.get("type") in CALL_ACTION_TYPES and action.get("status") in ACTIVE_ACTION_STATUSES
    ]
    return first_by_due_at(calls)


def first_active_reprise(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    reprises = [
        action for action in actions
        if action.get("type") in MANUAL_REPRISE_ACTION_TYPES and action.get("status") in ACTIVE_ACTION_STATUSES
    ]
    return first_by_due_at(reprises)


def first_by_due_at(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not actions:
        return None
    return sorted(actions, key=action_sort_key)[0]


def action_sort_key(action: dict[str, Any]) -> tuple[datetime, int]:
    due_at = parse_dt(action.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc)
    return due_at, int(action.get("id") or 0)


def action_is_due(action: dict[str, Any] | None, now: datetime | None = None) -> bool:
    if not action:
        return False
    due_at = parse_dt(action.get("due_at"))
    if due_at is None:
        return True
    return due_at <= (now or utc_now())


def terminal_block_reason(conv: dict[str, Any]) -> str | None:
    if conv.get("contact_status") in STOP_CONTACT_STATUSES:
        return "Statut Ne plus contacter actif."
    if conv.get("lead_status") in TERMINAL_QUALIFICATION_STATUSES:
        return "Qualification terminale active."
    return None


def action_banner(
    conv: dict[str, Any],
    current_action: dict[str, Any] | None,
    *,
    active_actions: list[dict[str, Any]],
    active_call: dict[str, Any] | None,
    terminal_reason: str | None,
    now: datetime,
) -> dict[str, str]:
    if conv.get("status") == "resolved" and active_actions:
        return banner(
            "red",
            "Incohérence système",
            "Cette conversation est terminée mais une action active existe encore. Réactive ou corrige le statut avant de traiter l'action.",
        )
    if conv.get("status") == "resolved":
        return banner("blue", "Conversation terminée", "Aucune action standard n'est attendue tant que la conversation reste clôturée.")
    if not current_action:
        return banner(
            "red",
            "Incohérence système",
            "Cette conversation est active mais aucune prochaine action n'est ouverte. Programme un appel ou demande une reprise manuelle.",
        )

    action_type = current_action.get("type")
    if action_type == "other":
        return banner(
            "red",
            "Action obsolète",
            "Une action de revue humaine générique existe encore. Remplace-la par une reprise manuelle ou un appel documenté.",
        )
    if terminal_reason or action_type == "contact_review":
        return banner(
            "orange",
            "Statut à revoir",
            "Gère la qualification ou le statut de contact dans Statuts. Les relances et appels commerciaux restent bloqués.",
        )
    if current_action.get("status") == "blocked":
        if action_type == "follow_up":
            return banner(
                "orange",
                "Relance bloquée",
                "Aucun modèle WhatsApp approuvé ne convient. Demande ou synchronise le modèle, puis envoie depuis Conversation.",
            )
        return banner("orange", "Action bloquée", current_action.get("blocked_reason") or "Cette action doit être débloquée avant traitement.")
    if action_type == "reply":
        suffix = " L'appel déjà planifié reste actif." if active_call else ""
        return banner(
            "blue",
            "Répondre dans Conversation",
            f"Le prospect attend une réponse WhatsApp. Envoyez le message depuis Conversation ; l'envoi clôturera l'action.{suffix}",
        )
    if action_type == "follow_up":
        return banner(
            "blue",
            "Envoyer la relance dans Conversation",
            "Relisez la conversation, utilisez le modèle recommandé si nécessaire, puis envoyez depuis Conversation.",
        )
    if action_type in CALL_ACTION_TYPES:
        label = "setting" if action_type == "setting_call" else "closing"
        if action_is_due(current_action, now):
            return banner("blue", f"Appel {label} à documenter", "L'appel est dû. Appelez le prospect puis documentez le résultat ci-dessous.")
        return banner("blue", f"Appel {label} planifié", "Le rendez-vous est prévu plus tard. Vous pouvez modifier l'appel, mais la documentation reste grisée.")
    if action_type in MANUAL_REPRISE_ACTION_TYPES:
        label = "setter" if action_type == "manual_reprise_setter" else "closer"
        return banner("blue", f"Reprise manuelle {label}", "Relisez la conversation, décidez de la suite, puis documentez la reprise avec une note.")
    if action_type == FRONT_TRANSITION_REVIEW_ACTION:
        return banner(
            "blue",
            "Reprise transition Front",
            "Relisez l'historique importé Front, répondez si nécessaire, programmez une relance transition Front si utile, ou clôturez avec une note.",
        )
    if action_type == FRONT_TRANSITION_FOLLOW_UP_ACTION:
        if action_is_due(current_action, now):
            return banner(
                "blue",
                "Relance transition Front à traiter",
                "Relisez l'historique, envoyez un message depuis Conversation si utile, puis clôturez la relance avec une note.",
            )
        return banner(
            "blue",
            "Relance transition Front planifiée",
            "Cette relance de transition est prévue plus tard. Elle ne déclenche aucun flux V1 automatique.",
        )
    return banner(
        "red",
        "Action inconnue",
        "Le type d'action actif n'appartient pas au flux V1 normal. Corrige avec une reprise manuelle ou un appel.",
    )


def banner(severity: str, title: str, body: str) -> dict[str, str]:
    return {"severity": severity, "title": title, "body": body}


def schedule_call_section(
    conv: dict[str, Any],
    active_call: dict[str, Any] | None,
    terminal_reason: str | None,
) -> dict[str, Any]:
    if conv.get("status") != "open":
        return disabled_section("Conversation terminée.")
    if terminal_reason:
        return disabled_section(f"{terminal_reason} Modifie d'abord Statuts ou demande une reprise manuelle.")

    options = {
        "setting_call": {"enabled": True, "reason": ""},
        "closing_call": {"enabled": True, "reason": ""},
    }
    if active_call:
        active_type = active_call.get("type")
        inactive_type = "closing_call" if active_type == "setting_call" else "setting_call"
        options[active_type] = {"enabled": True, "reason": "Appel existant modifiable."}
        options[inactive_type] = {"enabled": False, "reason": "Un autre type d'appel est déjà actif."}
        return {"enabled": True, "reason": "", "options": options}
    return {"enabled": True, "reason": "", "options": options}


def document_call_section(
    conv: dict[str, Any],
    active_call: dict[str, Any] | None,
    terminal_reason: str | None,
    now: datetime,
) -> dict[str, Any]:
    if conv.get("status") != "open":
        return disabled_section("Conversation terminée.")
    if terminal_reason:
        return disabled_section(f"{terminal_reason} Les appels commerciaux sont bloqués.")
    if not active_call:
        return disabled_section("Aucun appel actif à documenter.")
    if not action_is_due(active_call, now):
        return disabled_section("Appel planifié plus tard.")
    return {"enabled": True, "reason": "", "action": active_call}


def request_manual_reprise_section(conv: dict[str, Any]) -> dict[str, Any]:
    if conv.get("status") != "open":
        return disabled_section("Conversation terminée.")
    return {"enabled": True, "reason": ""}


def document_manual_reprise_section(
    conv: dict[str, Any],
    current_action: dict[str, Any] | None,
    active_reprise: dict[str, Any] | None,
) -> dict[str, Any]:
    if conv.get("status") != "open":
        return disabled_section("Conversation terminée.")
    action = current_action if (current_action or {}).get("type") in MANUAL_REPRISE_ACTION_TYPES else active_reprise
    if not action:
        return disabled_section("Aucune reprise manuelle active.")
    return {"enabled": True, "reason": "", "action": action}


def skip_step_section(
    conv: dict[str, Any],
    current_action: dict[str, Any] | None,
    terminal_reason: str | None,
) -> dict[str, Any]:
    if conv.get("status") != "open":
        return disabled_section("Conversation terminée.")
    if not current_action:
        return disabled_section("Aucune action de flux active.")
    if current_action.get("type") == "other":
        return disabled_section("Action générique obsolète : remplace-la par une reprise ou un appel.")
    if terminal_reason:
        return disabled_section(f"{terminal_reason} Aucune étape commerciale ne doit continuer.")
    if current_action.get("type") not in SKIPPABLE_FLOW_ACTION_TYPES:
        return disabled_section("L'action courante n'est pas une étape de flux ignorable.")
    if not current_action.get("sequence_code") or not current_action.get("sequence_step_index"):
        return disabled_section("L'action courante n'appartient pas à un flux.")
    return {"enabled": True, "reason": "", "action": current_action}


def disabled_section(reason: str) -> dict[str, Any]:
    return {"enabled": False, "reason": reason}
