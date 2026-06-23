from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from html import escape
from pathlib import Path
import sys
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.business_rules import (
    ACTION_STATUSES,
    ASSIGNMENT_RULES,
    CONTACT_STATUSES,
    DEMO_TEMPLATE_CATALOG,
    LEAD_TYPES,
    MAIN_ACTION_TYPES,
    OPERATING_RULES,
    PILOTAGE_VALIDATION_CASES,
    QUALIFICATION_STATUSES,
    RESOLUTION_REASONS,
    SALES_ACTORS,
    SCHEDULE_RULES,
    SOURCE_TYPES,
    SUPPORT_ACTIONS,
    TEMPLATE_REQUEST_STATUSES,
    WORKFLOW_TRANSITIONS,
)
from sales_cockpit.config import get_settings
from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.whatsapp_rules import parse_dt, utc_now
from sales_cockpit.services.schooldrive import SchoolDriveConnector
from sales_cockpit.store import (
    add_manual_note,
    assign_standard_next_action,
    authenticate,
    cancel_call_action_without_replacement,
    complete_admin_action,
    complete_action_with_workflow,
    create_and_submit_twilio_template,
    create_bug_report,
    create_template_request,
    create_template,
    add_sequence_step,
    deactivate_course_category,
    deactivate_course_default_session,
    deactivate_sequence_step,
    deactivate_sequence_template_mapping,
    get_conversation,
    get_integration_readiness,
    get_next_action_for_lead,
    get_outbound_safeguards,
    build_front_cutover_plan,
    get_recommended_template_for_action,
    get_template,
    list_actions_for_lead,
    list_admin_actions,
    list_conversations,
    list_course_categories,
    list_course_default_sessions,
    list_front_import_records,
    list_messages,
    list_sequence_steps,
    list_sequence_template_mappings,
    list_sequences,
    list_tasks,
    list_template_requests,
    list_templates,
    list_bug_reports,
    list_user_activity_log,
    list_users,
    reactivate_sequence_step,
    reschedule_call_action,
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    sync_twilio_templates,
    upsert_course_category,
    upsert_course_default_session,
    upsert_sequence_step,
    upsert_sequence_template_mapping,
    update_template_request_status,
    update_outbound_safeguards,
    update_lead_qualification,
    update_temporary_identity,
)
from sales_cockpit.ui.styles import APP_CSS


LEAD_STATUSES = [item["value"] for item in QUALIFICATION_STATUSES]
CONTACT_STATUS_VALUES = [item["value"] for item in CONTACT_STATUSES]
RESOLUTION_REASON_VALUES = [item["value"] for item in RESOLUTION_REASONS]
URGENCIES = ["low", "normal", "high", "urgent"]
WORK_QUEUES = ["todo", "waiting", "resolved"]
INBOX_QUEUES = WORK_QUEUES + ["all"]
ACTION_QUEUES = ["due", "future", "completed", "all"]
STANDARD_NEXT_ACTION_TYPES = ["reply", "follow_up", "setting_call", "closing_call"]
DATE_INPUT_FORMAT = "DD.MM.YYYY"
DISPLAY_TZ = ZoneInfo("Europe/Zurich")
WIDGET_CLEAR_QUEUE_KEY = "_sales_cockpit_clear_widget_keys"
WORK_SORTS = ["assignee_name", "lead_name", "due_at"]
ACTION_OUTCOMES = {
    "reply": ["reply_no_appointment", "setting_booked", "closing_booked", "not_relevant", "do_not_contact"],
    "follow_up": ["follow_up_sent", "template_missing", "sequence_completed_no_reply"],
    "setting_call": ["to_closing", "not_reached", "not_ready", "not_relevant", "do_not_contact"],
    "closing_call": ["signed", "will_sign", "not_reached", "undecided", "not_relevant", "do_not_contact"],
    "contact_review": [
        "maintain_do_not_contact",
        "lift_do_not_contact",
        "keep_terminal_status",
        "requalify_and_reply",
    ],
    "other": ["done"],
}
REPLY_SEND_OUTCOMES = ["reply_no_appointment", "setting_booked", "closing_booked", "not_relevant", "do_not_contact"]
REPLY_SEND_OUTCOME_LABELS = {
    "reply_no_appointment": "Pas de RDV : relance Setter II à +72h",
    "setting_booked": "RDV setting fixé : créer un appel",
    "closing_booked": "RDV closing fixé : créer un appel",
    "not_relevant": "Hors cible : clore la conversation",
    "do_not_contact": "Ne plus contacter : clore et bloquer",
}
CALL_ACTION_TYPES = {"setting_call", "closing_call"}
PILOTAGE_SUPPORTED_CATEGORIES = ["FSM", "APP", "AS"]
SEQUENCE_STEP_ACTION_TYPES = ["follow_up", "setting_call", "closing_call", "other"]
SEQUENCE_STEP_ACTION_LABELS = {
    "follow_up": "Relance WhatsApp",
    "setting_call": "Appeler et documenter appel setting",
    "closing_call": "Appeler et documenter appel closing",
    "other": "Revue humaine",
}
SEQUENCE_STEP_OFFSET_UNITS = ["hours", "days"]
SEQUENCE_STEP_OFFSET_UNIT_LABELS = {
    "hours": "heures",
    "days": "jours",
}
SEQUENCE_STEP_OFFSET_DIRECTIONS = ["after", "before"]
SEQUENCE_STEP_OFFSET_DIRECTION_LABELS = {
    "after": "après le déclencheur",
    "before": "avant le déclencheur",
}
PILOTAGE_SEQUENCE_ORDER = {
    "lead_no_reply": 10,
    "setter_no_next_step": 20,
    "post_setting_undecided": 30,
    "setting_call_not_reached": 40,
    "post_closing_undecided": 50,
    "closing_call_not_reached": 60,
    "closer_will_sign": 70,
    "course_start": 80,
}
PILOTAGE_SEQUENCE_OWNER_LABELS = {
    "lead_no_reply": "Setter II",
    "setter_no_next_step": "Setter II",
    "post_setting_undecided": "Setter II",
    "setting_call_not_reached": "Setter I, puis Setter II",
    "post_closing_undecided": "Setter II",
    "closing_call_not_reached": "Closer, puis Setter II",
    "closer_will_sign": "Setter II",
    "course_start": "Setter II",
}
PILOTAGE_CONFLICT_RULES = [
    {
        "Situation": "Le prospect répond",
        "Règle": "La réponse entrante interrompt les relances futures et crée une action Répondre au message pour Setter I. Si un appel setting ou closing est déjà planifié, cet appel reste actif et visible.",
    },
    {
        "Situation": "Relance lead/préinscription et relance cours proches",
        "Règle": "Avant d'envoyer une relance lead/préinscription, le cockpit doit vérifier si une relance liée au cours est prévue dans les 24h. Si oui, la relance cours gagne et le flux lead/préinscription restant est annulé, sauf si un appel setting ou closing est déjà planifié.",
    },
    {
        "Situation": "Fenêtre WhatsApp fermée",
        "Règle": "Le message libre est interdit. L'utilisateur doit sélectionner un template WhatsApp approuvé.",
    },
    {
        "Situation": "Aucun template adapté",
        "Règle": "La relance est bloquée et une demande de modèle doit être créée avant l'envoi.",
    },
    {
        "Situation": "Ne plus contacter",
        "Règle": "Aucun message ne peut être envoyé tant que le statut n'est pas levé. Si le prospect réécrit, une revue Setter I est créée.",
    },
    {
        "Situation": "Signature, non pertinent ou conversation close",
        "Règle": "Toutes les actions ouvertes ou futures liées à la conversation sont arrêtées.",
    },
    {
        "Situation": "Signature confirmée par SchoolDrive",
        "Règle": "La donnée SchoolDrive gagne : le prospect passe en A signé, les relances sont arrêtées et la conversation est clôturée.",
    },
    {
        "Situation": "Opt-out ou Ne pas relancer transmis par SchoolDrive",
        "Règle": "Sales Cockpit applique Ne plus contacter, bloque les envois et clôt les relances, avec une note indiquant la provenance du signal.",
    },
    {
        "Situation": "Cours ou session complète",
        "Règle": "Les relances automatiques s'arrêtent. Setter I reçoit une action pour proposer une autre session au prospect.",
    },
    {
        "Situation": "Garde-fous d'envoi",
        "Règle": "Le kill switch WhatsApp et les plafonds par prospect/jour, prospect/semaine, global/jour et délai minimal entre relances bloquent l'envoi avant Twilio.",
    },
    {
        "Situation": "Conversation active ou clôturée",
        "Règle": "Une conversation reste active tant qu'il existe une action à traiter maintenant ou une action en suspens prévue plus tard. Elle est clôturée quand il n'y a plus rien à faire : signature, non pertinent, ne plus contacter ou fin de tous les flux de relance.",
    },
    {
        "Situation": "Session de référence déjà passée",
        "Règle": "Si la session de référence est déjà commencée quand le lead ou la préinscription arrive, le flux lié au début du cours ne doit pas être lancé sur cette session. Il faut choisir ou configurer la prochaine session de référence.",
    },
]
PILOTAGE_STATE_ROWS = [
    {
        "État": "Nouveau prospect",
        "Code": "new",
        "Sens": "Le prospect vient d'arriver ou n'a pas encore de parcours commercial avancé.",
        "Suite normale": "Réponse Setter I si le prospect écrit, ou relance Setter II si aucun message entrant.",
    },
    {
        "État": "Échange avec setter",
        "Code": "setting",
        "Sens": "Le prospect échange avec Setter I, mais aucun appel n'est encore fixé.",
        "Suite normale": "Fixer un appel setting, fixer directement un appel closing, ou relancer si l'échange s'arrête.",
    },
    {
        "État": "RDV setting agendé",
        "Code": "appointment_booked",
        "Sens": "Un rendez-vous de setting est prévu à une date et une minute précises.",
        "Suite normale": "Appeler le prospect puis documenter l'appel setting quand le moment du rendez-vous arrive.",
    },
    {
        "État": "RDV closing agendé",
        "Code": "closing",
        "Sens": "Un rendez-vous de closing est prévu pour le closer.",
        "Suite normale": "Appeler le prospect puis documenter l'appel closing : signé, va signer, indécis, non joint ou non pertinent.",
    },
    {
        "État": "Appel setting à documenter",
        "Code": "setting_call_due",
        "Sens": "Le moment prévu de l'appel setting est arrivé.",
        "Suite normale": "Setter I appelle, indique si le prospect a été joint, ajoute une note, puis choisit la suite.",
    },
    {
        "État": "Appel closing à documenter",
        "Code": "closing_call_due",
        "Sens": "Le moment prévu de l'appel closing est arrivé.",
        "Suite normale": "Closer appelle, indique si le prospect a été joint, ajoute une note, puis choisit la suite.",
    },
    {
        "État": "Va signer",
        "Code": "will_sign",
        "Sens": "Le closer estime que le prospect va signer.",
        "Suite normale": "Suivre le flux de relance Va signer jusqu'à signature ou fin du suivi.",
    },
    {
        "État": "Inscription confirmée",
        "Code": "won",
        "Sens": "Le prospect a signé. La vente est gagnée.",
        "Suite normale": "Clôturer la conversation et arrêter les relances commerciales.",
    },
    {
        "État": "Sans suite",
        "Code": "lost",
        "Sens": "Le suivi commercial est terminé sans inscription.",
        "Suite normale": "Conversation clôturée, sauf si le prospect réécrit plus tard.",
    },
    {
        "État": "Hors cible",
        "Code": "not_interesting",
        "Sens": "Le prospect n'est pas une opportunité commerciale utile.",
        "Suite normale": "Clôturer la conversation et arrêter les relances.",
    },
    {
        "État": "Absent au rendez-vous",
        "Code": "no_show",
        "Sens": "Le prospect n'a pas répondu ou ne s'est pas présenté à un appel prévu.",
        "Suite normale": "Créer les rappels d'appel prévus puis relancer si nécessaire.",
    },
    {
        "État": "Bloqué",
        "Code": "blacklist",
        "Sens": "Le prospect ne doit plus être contacté ou le contact est bloqué.",
        "Suite normale": "Aucun envoi tant que le statut de contact n'est pas levé.",
    },
]

DISPLAY_LABELS = {
    "all": "Toutes",
    "new": "Nouveau prospect",
    "setting": "Échange avec setter",
    "appointment_booked": "Appel setting prévu",
    "closing": "Appel closing",
    "won": "Inscription confirmée",
    "lost": "Sans suite",
    "not_interesting": "Hors cible",
    "no_show": "Absent au rendez-vous",
    "blacklist": "Bloqué",
    "cold": "Froid",
    "warm": "Tiède",
    "hot": "Chaud",
    "suspect": "Suspect",
    "lead": "Lead",
    "presubscription": "Préinscription",
    "prospect": "Prospect",
    "neutral": "Éligible",
    "eligible": "Éligible",
    "not_relevant": "Non pertinent",
    "will_sign": "Va signer",
    "signed": "A signé",
    "contact_allowed": "Contact autorisé",
    "do_not_contact": "Ne plus contacter",
    "duplicate": "Doublon",
    "handled_elsewhere": "Traité ailleurs",
    "sequence_completed_no_reply": "Suivi terminé sans réponse",
    "error": "Erreur",
    "deal_pending": "Deal en attente",
    "deal_confirmed": "Deal confirmé",
    "dead_lead": "Lead perdu",
    "dead_prospect": "Prospect perdu",
    "open": "Active",
    "resolved": "Terminée",
    "in_progress": "En cours",
    "planned": "Planifiée",
    "done": "Terminée",
    "cancelled": "Annulée",
    "blocked": "Bloquée",
    "todo": "À traiter",
    "due": "À traiter",
    "future": "En suspens",
    "completed": "Terminées",
    "follow_up": "Envoyer relance",
    "waiting": "En suspens",
    "reply": "Répondre au message",
    "call": "Appeler",
    "closing_call": "Appeler et documenter appel closing",
    "setting_call": "Appeler et documenter appel setting",
    "to_closing": "Passer au closing",
    "not_reached": "Non joint",
    "not_ready": "Indécis après setting",
    "undecided": "Indécis",
    "contact_review": "Revue contact",
    "other": "Autre",
    "assignee_name": "Responsable",
    "lead_name": "Prospect",
    "due_at": "Échéance",
    "low": "Faible",
    "normal": "Normale",
    "high": "Élevée",
    "urgent": "Urgente",
    "draft": "Brouillon",
    "pending": "En attente",
    "approved": "Approuvé",
    "rejected": "Rejeté",
    "matched": "Correspondance trouvée",
    "unmatched": "Non retrouvé",
    "ambiguous": "Ambigu",
    "ambiguous_identity": "À identifier",
    "needs_identification": "À identifier",
    "verified": "Identifié",
    "active": "Active",
    "manual_review": "Revue manuelle",
    "ready_to_convert": "Prête à basculer",
    "history_only": "Historique seul",
    "none": "Aucune",
    "twilio/text": "Texte",
    "twilio/call-to-action": "Bouton",
    "twilio/quick-reply": "Réponse rapide",
    "twilio/list-picker": "Liste",
    "twilio/media": "Média",
    "utility": "Utilitaire",
    "marketing": "Marketing",
    "admin": "Admin",
    "setter": "Setter",
    "closer": "Closer",
    "Reached": "Contacté",
    "No answer": "Pas de réponse",
    "Wrong number": "Mauvais numéro",
    "Callback requested": "Rappel demandé",
    "Appointment booked": "RDV pris",
    "Not interested": "Pas intéressé",
    "Converted": "Converti",
    "Other": "Autre",
    "reply_no_appointment": "Réponse envoyée sans RDV",
    "setting_booked": "RDV setting fixé",
    "closing_booked": "RDV closing fixé",
    "follow_up_sent": "Relance envoyée",
    "template_missing": "Modèle manquant",
    "to_closing": "Passer au closing",
    "not_reached": "Pas joint",
    "not_ready": "Pas prêt / pas de suite claire",
    "undecided": "Joint mais pas décidé",
    "maintain_do_not_contact": "Maintenir Ne plus contacter",
    "lift_do_not_contact": "Lever Ne plus contacter",
    "done": "Terminé",
    "to_create": "À créer",
    "submitted": "Soumis",
    "rejected": "Rejeté",
    "cancelled": "Annulé",
}

HELP_TEXTS = {
    "sales_stage": (
        "Étape du parcours commercial. En usage normal, elle suit les actions du cockpit. "
        "À modifier seulement pour forcer le prospect vers une autre étape après une correction externe."
    ),
    "lead_status": (
        "Qualification commerciale : probabilité que le prospect s'inscrive. Non pertinent et A signé arrêtent les relances."
    ),
    "contact_status": (
        "Statut de contact : le prospect accepte-t-il encore qu'on lui écrive ? Ne plus contacter bloque les relances."
    ),
}


def main() -> None:
    st.set_page_config(page_title="Sales Cockpit", page_icon="SC", layout="wide")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    seed_initial_data()
    apply_pending_widget_clears()

    if "user" not in st.session_state:
        render_login()
        return

    render_shell()


def render_login() -> None:
    st.title("Sales Cockpit")
    st.caption("Interface interne ESSR pour WhatsApp, actions commerciales et qualification des leads.")

    with st.form("login", clear_on_submit=False):
        email = st.text_input("E-mail", placeholder="prenom.nom@essr.ch")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", use_container_width=True)

    if submitted:
        user = authenticate(email.strip(), password)
        if user:
            st.session_state.user = user
            st.session_state.pop("work_queue_assignee_widget", None)
            st.session_state.pop("work_queue_assignee_selected_id", None)
            st.session_state.pop("work_queue_assignee_user_id", None)
            st.session_state.pop("selected_action_id", None)
            st.rerun()
        st.error("Identifiants invalides.")

    st.info("Mode local mock. Mot de passe initial par défaut : ChangeMe!2026")


def render_shell() -> None:
    user = refresh_current_user(st.session_state.user)
    st.session_state.user = user
    nav_options = ["Tâches", "Inbox", "Modèles", "Mode d'emploi"]
    if user["role"] == "admin":
        nav_options.insert(2, "Pilotage")
        nav_options.append("Admin")
    nav = resolve_navigation(nav_options)
    with st.sidebar:
        st.subheader("Sales Cockpit")
        st.caption(f"{display_user_name(user)} · {display_user_role(user)}")
        desktop_radio_kwargs = {
            "label": "Navigation",
            "options": nav_options,
            "label_visibility": "collapsed",
            "key": "desktop_navigation",
        }
        if "desktop_navigation" not in st.session_state:
            desktop_radio_kwargs["index"] = safe_index(nav_options, nav)
        st.radio(**desktop_radio_kwargs)
        render_bug_report_button(user, nav)
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

    with st.container(key="mobile_nav"):
        mobile_select_kwargs = {
            "label": "Page",
            "options": nav_options,
            "key": "mobile_navigation",
        }
        if "mobile_navigation" not in st.session_state:
            mobile_select_kwargs["index"] = safe_index(nav_options, nav)
        st.selectbox(**mobile_select_kwargs)

    if nav == "Tâches":
        render_work_queue(user)
    elif nav == "Inbox":
        render_inbox(user)
    elif nav == "Modèles":
        render_templates(user)
    elif nav == "Pilotage":
        render_pilotage(user)
    elif nav == "Mode d'emploi":
        render_user_guide()
    elif nav == "Admin":
        render_admin(user)


def resolve_navigation(nav_options: list[str]) -> str:
    fallback = nav_options[0]
    current = (
        st.session_state.get("active_navigation")
        or st.session_state.get("main_navigation")
        or fallback
    )
    if current not in nav_options:
        current = fallback

    desktop_value = st.session_state.get("desktop_navigation", current)
    mobile_value = st.session_state.get("mobile_navigation", current)
    last_desktop = st.session_state.get("_last_desktop_navigation", current)
    last_mobile = st.session_state.get("_last_mobile_navigation", current)

    if desktop_value in nav_options and desktop_value != last_desktop:
        current = desktop_value
    elif mobile_value in nav_options and mobile_value != last_mobile:
        current = mobile_value

    st.session_state["active_navigation"] = current
    st.session_state["desktop_navigation"] = current
    st.session_state["mobile_navigation"] = current
    st.session_state["_last_desktop_navigation"] = current
    st.session_state["_last_mobile_navigation"] = current
    return current


def render_bug_report_button(user: dict, page: str) -> None:
    if st.button("Bug", use_container_width=True):
        render_bug_report_dialog(user, page)


@st.dialog("Signaler un bug", width="large")
def render_bug_report_dialog(user: dict, page: str) -> None:
    st.caption("Décrivez ce qui semble incorrect ou améliorable. Le signalement sera relié à la page courante et, si possible, à la conversation ou à l'action sélectionnée.")
    with st.form("bug_report_form"):
        title = st.text_input("Titre court", placeholder="Ex. mauvaise prochaine action", key="bug_report_title")
        description = st.text_area(
            "Ce qui semble incorrect ou améliorable",
            height=140,
            key="bug_report_description",
        )
        actual = st.text_area("Ce que vous voyez", height=90, key="bug_report_actual")
        expected = st.text_area("Ce que vous attendiez", height=90, key="bug_report_expected")
        severity = st.selectbox(
            "Priorité",
            ["normal", "high", "urgent"],
            index=0,
            format_func=labelize,
            key="bug_report_severity",
        )
        submitted = st.form_submit_button("Envoyer")
    if submitted:
        ok, message = create_bug_report(
            user["id"],
            page,
            title,
            description,
            expected_behavior=expected,
            actual_behavior=actual,
            severity=severity,
            conversation_id=st.session_state.get("selected_conversation_id"),
            action_id=st.session_state.get("selected_action_id"),
            metadata={
                "selected_conversation_id": st.session_state.get("selected_conversation_id"),
                "selected_action_id": st.session_state.get("selected_action_id"),
            },
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(
                "bug_report_title",
                "bug_report_description",
                "bug_report_actual",
                "bug_report_expected",
            )
            st.rerun()


@st.fragment(run_every="10s")
def render_inbox(user: dict) -> None:
    st.title("Inbox WhatsApp")

    search_col, header_col = st.columns([0.95, 1.45], gap="large")
    with search_col:
        search = st.text_input("Recherche", placeholder="Nom, téléphone, cours, message...")
    conversations = list_conversations(
        search=search,
    )
    conversations = sort_conversations_for_attention(conversations)

    if not conversations:
        st.warning("Aucune conversation trouvée.")
        return

    conversations_by_queue = {
        queue: conversations if queue == "all" else [
            conv for conv in conversations if conv["work_queue"] == queue
        ]
        for queue in INBOX_QUEUES
    }
    visible_ids = {conv["conversation_id"] for conv in conversations}
    if st.session_state.get("selected_conversation_id") not in visible_ids:
        default = next(
            (
                queue_conversations[0]
                for queue_conversations in conversations_by_queue.values()
                if queue_conversations
            ),
            conversations[0],
        )
        st.session_state.selected_conversation_id = default["conversation_id"]
    conversation_id = st.session_state.selected_conversation_id

    with header_col:
        st.markdown('<div class="sc-search-field-offset"></div>', unsafe_allow_html=True)
        render_conversation_header(user, conversation_id)

    left, right = st.columns([0.95, 1.45], gap="large")
    with left:
        st.subheader("Conversations")

        tabs = st.tabs(
            [
                f"{queue_label(queue)} ({len(conversations_by_queue[queue])})"
                for queue in INBOX_QUEUES
            ]
        )
        for index, queue in enumerate(INBOX_QUEUES):
            with tabs[index]:
                render_conversation_rows(conversations_by_queue[queue], queue)

    with right:
        render_conversation_detail(user, conversation_id)


def render_conversation_rows(conversations: list[dict], bucket: str) -> None:
    if not conversations:
        st.info("Aucune conversation dans cette file.")
        return

    for conv in conversations:
        selected = st.session_state.get("selected_conversation_id") == conv["conversation_id"]
        button_type = "primary" if selected else "secondary"
        with st.container(border=True):
            text_col, action_col = st.columns([0.78, 0.22], vertical_alignment="center")
            with text_col:
                st.markdown(conversation_row_html(conv), unsafe_allow_html=True)
            with action_col:
                if st.button(
                    "Voir",
                    key=f"open_conversation_{bucket}_{conv['conversation_id']}",
                    type=button_type,
                    use_container_width=True,
                ):
                    st.session_state.selected_conversation_id = conv["conversation_id"]
                    st.rerun()


def conversation_row_html(conv: dict) -> str:
    owner = normalize_user_display_name(
        conv.get("next_action_assigned_to_email"),
        conv.get("next_action_assigned_to_name")
        or conv.get("closer_name")
        or conv.get("setter_name")
        or "Non assigné",
    )
    preview = compact_text(conv.get("last_message_body") or "Aucun message", 96)
    action = conv.get("next_action_title") or "Aucune action ouverte"
    due = format_due(conv.get("next_action_due_at"))
    name = escape_html(lead_display_name(conv))
    lead_type = escape_html(labelize(conv.get("lead_type") or "lead"))
    identity_badge = identity_badge_html(conv)
    course = escape_html(conversation_course_label(conv))
    owner_html = escape_html(owner)
    preview_html = escape_html(preview)
    action_html = escape_html(compact_text(action_display_title(action), 92))
    due_html = escape_html(due)
    queue_html = escape_html(labelize(conv.get("work_queue")))
    waiting = client_waiting_state(conv)
    waiting_html = (
        f'<div class="sc-hot-signal">🔥 {escape_html(waiting)}</div>'
        if waiting
        else ""
    )
    return f"""
        <div class="sc-conversation-row">
          <div class="sc-lead-type-line">{lead_type}{identity_badge}</div>
          <div class="sc-conversation-title"><strong>{name}</strong></div>
          <div class="sc-row-meta">{course} · {owner_html}</div>
          {waiting_html}
          <div class="sc-next-action-line"><span>{queue_html}</span> · {action_html}</div>
          <div class="sc-row-meta">{due_html}</div>
          <div class="sc-preview">{preview_html}</div>
        </div>
    """


def conversation_course_label(conv: dict) -> str:
    if conv.get("lead_type") == "presubscription":
        return conv.get("course_title") or conv.get("course_category_short_title") or "Sans cours"
    return (
        conv.get("course_category_short_title")
        or conv.get("course_id")
        or conv.get("course_title")
        or "Sans cours"
    )


def render_conversation_detail(user: dict, conversation_id: int) -> None:
    conv = get_conversation(conversation_id)
    if not conv:
        st.error("Conversation introuvable.")
        return

    render_conversation_context(conv)
    render_compact_lead_state(conv)
    render_next_action_summary(conv)
    render_planned_call_notice(conv)

    tabs = st.tabs(["Conversation", "Actions", "Statuts", "Notes privées"])
    with tabs[0]:
        show_internal_notes = st.checkbox(
            "Afficher les notes internes",
            value=True,
            key=f"show_internal_notes_{conversation_id}",
        )
        render_messages(conversation_id, show_internal_notes=show_internal_notes)
        st.markdown('<div class="sc-reply-anchor"></div>', unsafe_allow_html=True)
        render_composer(user, conv)
    with tabs[1]:
        render_next_action_box(user, conv)
    with tabs[2]:
        render_qualification(user, conv)
    with tabs[3]:
        render_manual_note_box(user, conv)


def render_conversation_header(user: dict, conversation_id: int) -> None:
    conv = get_conversation(conversation_id)
    if not conv:
        return

    full_name = escape_html(lead_display_name(conv))
    header_col, status_action_col, schooldrive_col = st.columns(
        [0.48, 0.24, 0.28], vertical_alignment="center"
    )
    with header_col:
        st.markdown(f'<div class="sc-detail-title">{full_name}</div>', unsafe_allow_html=True)
    with status_action_col:
        render_conversation_status_button(user, conv)
    with schooldrive_col:
        schooldrive_url = get_schooldrive_url(conv)
        if schooldrive_url:
            st.markdown(
                f'<a class="sc-link-button" href="{escape_html(schooldrive_url)}" target="_blank" rel="noopener noreferrer">Ouvrir SchoolDrive</a>',
                unsafe_allow_html=True,
            )
        else:
            st.button("SchoolDrive indisponible", disabled=True, use_container_width=True)


def render_conversation_context(conv: dict) -> None:
    badge_class = "sc-badge-open" if conv["window_is_open"] else "sc-badge-closed"
    window_text = "Fenêtre ouverte" if conv["window_is_open"] else "Fenêtre fermée"
    if conv["window_is_open"]:
        window_boundary = f"Ferme le {format_window_boundary(conv.get('window_closes_at'))}"
    elif conv.get("window_closes_at"):
        window_boundary = f"Fermée le {format_window_boundary(conv.get('window_closes_at'))}"
    else:
        window_boundary = "Jamais ouverte"
    course = escape_html(conversation_course_label(conv))
    phone = escape_html(conv.get("phone_e164") or "Téléphone indisponible")
    st.markdown(
        f"""
        <div class="sc-conversation-meta-bar">
          <div class="sc-prospect-meta">
            <span>{course}</span>
            <span>{phone}</span>
          </div>
          <div class="sc-window-status">
            <span class="sc-badge {badge_class}">{window_text}</span>
            <span class="sc-window-close">{escape_html(window_boundary)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_conversation_status_button(user: dict, conv: dict) -> None:
    if conv["status"] == "resolved":
        with st.popover("Réactiver", use_container_width=True):
            users = list_users()
            action_type = st.selectbox(
                "Prochaine action",
                ["reply", "follow_up", "setting_call", "closing_call"],
                format_func=labelize,
                key=f"reopen_action_type_{conv['id']}",
            )
            assignee = st.selectbox(
                "Responsable",
                users,
                index=safe_user_index(users, user["id"]),
                format_func=format_user,
                key=f"reopen_assignee_{conv['id']}",
            )
            reopen_date = st.date_input(
                "Date",
                value=local_today(),
                key=f"reopen_date_{conv['id']}",
                format=DATE_INPUT_FORMAT,
            )
            reopen_time = st.time_input(
                "Heure",
                value=time(9, 0),
                step=timedelta(minutes=1),
                key=f"reopen_time_{conv['id']}",
            )
            reason = st.text_area("Raison de réactivation", height=80, key=f"reopen_reason_{conv['id']}")
            submitted = st.button(
                "Réactiver",
                key=f"submit_reopen_{conv['id']}",
                disabled=not reason.strip(),
            )
        if submitted:
            ok, message = set_conversation_status(
                conv["id"],
                user["id"],
                "open",
                reopen_action_type=action_type,
                reopen_assigned_to_user_id=assignee["id"],
                reopen_due_at=local_due_at(reopen_date, reopen_time),
                reopen_reason=reason.strip(),
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(
                    f"reopen_reason_{conv['id']}",
                    f"reopen_date_{conv['id']}",
                    f"reopen_time_{conv['id']}",
                )
                st.rerun()
    else:
        with st.popover("Clore la conversation", use_container_width=True):
            reason = st.selectbox(
                "Motif",
                RESOLUTION_REASON_VALUES,
                format_func=labelize,
                key=f"resolve_reason_header_{conv['id']}",
            )
            note = st.text_area("Note", height=80, key=f"resolve_note_header_{conv['id']}")
            submitted = st.button(
                "Clore la conversation",
                key=f"submit_resolve_header_{conv['id']}",
                disabled=not note.strip(),
            )
        if submitted:
            ok, message = set_conversation_status(
                conv["id"],
                user["id"],
                "resolved",
                resolution_reason=reason,
                resolution_note=note.strip(),
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(f"resolve_note_header_{conv['id']}")
                st.rerun()


def identity_needs_review(item: dict) -> bool:
    return item.get("identity_status") in {"needs_identification", "ambiguous_identity"}


def identity_badge_html(item: dict) -> str:
    if not identity_needs_review(item):
        return ""
    return '<span class="sc-identity-badge">À identifier</span>'


def state_chip_html(label: str, value: str) -> str:
    return (
        '<span class="sc-state-chip">'
        f'<strong>{escape_html(label)}</strong>'
        f'<span>{escape_html(value)}</span>'
        "</span>"
    )


def render_compact_lead_state(conv: dict) -> None:
    contact_html = ""
    if conv.get("contact_status") == "do_not_contact":
        contact_html = (
            state_chip_html(
                "Contact",
                labelize(conv["contact_status"]),
            )
        )
    stage_html = state_chip_html(
        "Parcours",
        labelize(conv["sales_stage"]),
    )
    qualification_html = state_chip_html(
        "Qualification",
        labelize(conv["lead_status"]),
    )
    identity_html = ""
    if identity_needs_review(conv):
        identity_html = state_chip_html("Identification", "À identifier")
    st.markdown(
        f"""
        <div class="sc-compact-state">
          {stage_html}
          {qualification_html}
          {identity_html}
          {contact_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_messages(conversation_id: int, show_internal_notes: bool = True) -> None:
    messages = list_messages(conversation_id)
    for message in messages:
        if message["direction"] == "manual_note" and not show_internal_notes:
            continue
        if message["direction"] == "inbound":
            css = "sc-message-inbound"
            row_css = "sc-message-row-inbound"
            sender = "Prospect"
        elif message["direction"] == "manual_note":
            css = "sc-message-note"
            row_css = "sc-message-row-outbound"
            sender = normalize_user_display_name(message.get("sender_email"), message.get("sender_name") or "Note")
        else:
            css = "sc-message-outbound"
            row_css = "sc-message-row-outbound"
            sender = normalize_user_display_name(message.get("sender_email"), message.get("sender_name") or "ESSR")
        created = format_dt(message_display_timestamp(message))
        template = f" · modèle: {message['template_name']}" if message.get("template_name") else ""
        delivery = render_delivery_status(message)
        attachments_html = render_message_attachments(message.get("attachments") or [])
        st.markdown(
            f"""
            <div class="sc-message-row {row_css}">
              <div class="sc-message {css}">
                <div class="sc-message-meta">{sender} · {created}{template}{delivery}</div>
                <div>{escape_html(message['body'])}</div>
                {attachments_html}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def message_display_timestamp(message: dict) -> str | None:
    if message.get("direction") == "outbound":
        return message.get("sent_at") or message.get("created_at")
    if message.get("direction") == "inbound":
        return message.get("received_at") or message.get("created_at")
    return message.get("created_at")


def render_message_attachments(attachments: list[dict]) -> str:
    if not attachments:
        return ""
    links = []
    for attachment in attachments:
        name = escape_html(attachment.get("file_name") or "Pièce jointe")
        size = format_bytes(attachment.get("size_bytes"))
        label = f"{name} · {escape_html(size)}" if size != "0 B" else name
        url = attachment.get("public_url")
        if url:
            links.append(
                f'<a class="sc-attachment-link" href="{escape_html(url)}" target="_blank" rel="noreferrer">{label}</a>'
            )
        else:
            links.append(f'<span class="sc-attachment-link">{label}</span>')
    return f'<div class="sc-attachment-list">{"".join(links)}</div>'


def render_delivery_status(message: dict) -> str:
    if message.get("direction") != "outbound":
        return ""
    status = (message.get("twilio_status") or "").lower()
    error = message.get("twilio_error_message") or message.get("twilio_error_code") or ""
    labels = {
        "accepted": ("…", "En file", "pending"),
        "queued": ("…", "En file", "pending"),
        "scheduled": ("…", "En file", "pending"),
        "sending": ("…", "Envoi", "pending"),
        "sent": ("✓", "Envoyé", "sent"),
        "delivered": ("✓✓", "Reçu", "delivered"),
        "read": ("✓✓", "Lu", "read"),
        "failed": ("!", f"Échec{': ' + error if error else ''}", "failed"),
        "undelivered": ("!", f"Non reçu{': ' + error if error else ''}", "failed"),
    }
    icon, title, css = labels.get(status, ("", "", ""))
    if not icon:
        return ""
    return (
        f' <span class="sc-delivery-status sc-delivery-{css}" '
        f'title="{escape_html(title)}">{escape_html(icon)}</span>'
    )


def next_action_context(conv: dict) -> dict | None:
    return get_next_action_for_lead(conv["lead_id"])


def reply_call_assignee_options(users: list[dict], outcome: str) -> list[dict]:
    if outcome == "setting_booked":
        options = [
            user for user in users
            if user.get("role") == "setter" and (user.get("email") or "").lower() != "setter2@essr.ch"
        ]
        return options or users
    if outcome == "closing_booked":
        options = [user for user in users if user.get("role") == "closer"]
        return options or users
    return users


def standard_action_assignee_options(users: list[dict], action_type: str) -> list[dict]:
    if action_type in {"reply", "setting_call"}:
        options = [
            user for user in users
            if user.get("role") == "setter" and (user.get("email") or "").lower() != "setter2@essr.ch"
        ]
        return options or users
    if action_type == "follow_up":
        tanjona = [
            user for user in users
            if (user.get("email") or "").lower() == "setter2@essr.ch"
        ]
        setters = [user for user in users if user.get("role") == "setter"]
        return tanjona or setters or users
    if action_type == "closing_call":
        closers = [user for user in users if user.get("role") == "closer"]
        return closers or users
    return users


def standard_action_button_label(action_type: str) -> str:
    labels = {
        "reply": "Répondre à un message",
        "follow_up": "Planifier une relance",
        "setting_call": "Programmer un appel setting",
        "closing_call": "Programmer un appel closing",
    }
    return labels.get(action_type, labelize(action_type))


def active_planned_call_for_lead(lead_id: int | None) -> dict | None:
    if not lead_id:
        return None
    calls = [
        action for action in list_actions_for_lead(lead_id, "all")
        if action.get("type") in CALL_ACTION_TYPES
        and action.get("status") in {"open", "in_progress", "planned", "blocked"}
    ]
    if not calls:
        return None
    calls.sort(key=lambda action: parse_dt(action.get("due_at")) or datetime.max.replace(tzinfo=timezone.utc))
    return calls[0]


def get_reply_send_plan(
    action: dict | None,
    key_prefix: str,
    users: list[dict],
) -> tuple[str | None, str | None, int | None, str]:
    if not action or action.get("type") != "reply":
        return None, None, None, ""

    outcome = st.session_state.get(f"{key_prefix}_reply_outcome", "reply_no_appointment")
    note = (st.session_state.get(f"{key_prefix}_reply_note") or "").strip()
    next_due_at = None
    assigned_to_user_id = None
    if outcome in {"setting_booked", "closing_booked"}:
        assignee_options = reply_call_assignee_options(users, outcome)
        assigned_to_user_id = st.session_state.get(
            f"{key_prefix}_reply_assignee_id",
            action.get("assigned_to_user_id") if outcome == "setting_booked" else None,
        )
        if not any(user["id"] == assigned_to_user_id for user in assignee_options):
            assigned_to_user_id = assignee_options[0]["id"] if assignee_options else None
        appointment_date = st.session_state.get(
            f"{key_prefix}_reply_date",
            local_today(),
        )
        appointment_time = st.session_state.get(
            f"{key_prefix}_reply_time",
            time(9, 0),
        )
        next_due_at = local_due_at(appointment_date, appointment_time)
    return outcome, next_due_at, assigned_to_user_id, note


def render_reply_send_plan_controls(
    action: dict | None,
    key_prefix: str,
    users: list[dict],
) -> None:
    if not action or action.get("type") != "reply":
        return

    st.markdown("**Après votre réponse, quelle suite faut-il créer ?**")
    st.caption("Si le prospect accepte un appel, choisissez `RDV setting fixé`, renseignez le rendez-vous, puis envoyez le message dans Conversation.")
    active_call = active_planned_call_for_lead(action.get("lead_id"))
    labels = dict(REPLY_SEND_OUTCOME_LABELS)
    if active_call:
        labels["reply_no_appointment"] = "Pas de nouveau RDV : conserver l'appel planifié"
    outcome = st.selectbox(
        "Suite à créer après l'envoi",
        REPLY_SEND_OUTCOMES,
        format_func=lambda value: labels.get(value, labelize(value)),
        key=f"{key_prefix}_reply_outcome",
    )
    note = st.text_area("Note interne, optionnelle", height=80, key=f"{key_prefix}_reply_note")
    if outcome in {"setting_booked", "closing_booked"}:
        assignee_options = reply_call_assignee_options(users, outcome)
        assignee = st.selectbox(
            "Responsable de l'appel",
            assignee_options,
            index=safe_user_index(
                assignee_options,
                action.get("assigned_to_user_id") if outcome == "setting_booked" else None,
            ),
            format_func=format_user,
            key=f"{key_prefix}_{outcome}_reply_assignee",
        )
        st.session_state[f"{key_prefix}_reply_assignee_id"] = assignee["id"]
        appointment_date = st.date_input(
            "Date du rendez-vous",
            value=local_today(),
            key=f"{key_prefix}_reply_date",
            format=DATE_INPUT_FORMAT,
        )
        appointment_time = st.time_input(
            "Heure",
            value=time(9, 0),
            step=timedelta(minutes=1),
            key=f"{key_prefix}_reply_time",
        )
        call_label = "setting" if outcome == "setting_booked" else "closing"
        st.caption(f"Après l'envoi, un appel {call_label} sera créé le {appointment_date.strftime('%d.%m.%Y')} à {appointment_time.strftime('%H:%M')}.")
    elif outcome in {"not_relevant", "do_not_contact"}:
        st.warning("Cette réponse clôturera la conversation et annulera les relances futures.")
    elif active_call:
        call_type = "setting" if active_call.get("type") == "setting_call" else "closing"
        st.caption(f"Après l'envoi, l'appel {call_type} déjà planifié restera actif.")
    else:
        st.caption("Après l'envoi, une relance Setter II sera planifiée à +72h si le prospect ne répond pas.")


def render_composer(user: dict, conv: dict) -> None:
    action = next_action_context(conv)
    users = list_users()
    action_outcome, next_due_at, assigned_to_user_id, action_note = get_reply_send_plan(
        action,
        f"reply_plan_{conv['id']}",
        users,
    )
    if conv.get("contact_status") == "do_not_contact":
        st.error("Contact bloqué : le prospect est marqué Ne plus contacter. Le statut doit être levé dans Actions avant tout envoi.")
        return
    if conv.get("status") == "resolved":
        st.info("Conversation terminée : réactivez la conversation dans Actions avant tout nouvel envoi.")
        return
    if conv["window_is_open"]:
        st.success("Fenêtre WhatsApp ouverte : message libre autorisé.")
        if action and action.get("type") == "reply":
            st.caption("Si votre message fixe un appel, choisissez d'abord la suite dans l'onglet Actions.")
        freeform_base_key = f"freeform_body_{conv['id']}"
        freeform_key = resettable_widget_key(freeform_base_key)
        attachment_base_key = f"freeform_attachments_{conv['id']}"
        attachment_key = resettable_widget_key(attachment_base_key)
        with st.form(f"freeform_{conv['id']}"):
            body = st.text_area("Message libre", height=110, key=freeform_key)
            uploaded_files = st.file_uploader(
                "Pièces jointes",
                accept_multiple_files=True,
                key=attachment_key,
                help="V1 : maximum 5 fichiers, 10 Mo par fichier. WhatsApp n'accepte les pièces jointes que pendant une fenêtre ouverte.",
            )
            submitted = st.form_submit_button("Envoyer le message libre")
        if submitted:
            attachments = [
                {
                    "file_name": file.name,
                    "mime_type": file.type or "application/octet-stream",
                    "content": file.getvalue(),
                }
                for file in uploaded_files or []
            ]
            if not body.strip() and not attachments:
                st.error("Écrivez un message ou ajoutez une pièce jointe avant l'envoi.")
                return
            ok, message = send_freeform_message(
                conv["id"],
                user["id"],
                body.strip(),
                action_outcome=action_outcome,
                next_due_at=next_due_at,
                assigned_to_user_id=assigned_to_user_id,
                note=action_note,
                attachments=attachments,
            )
            show_result(ok, message)
            if ok:
                reset_widget_key(freeform_base_key)
                reset_widget_key(attachment_base_key)
                clear_widget_keys(
                    freeform_key,
                    attachment_key,
                    f"reply_plan_{conv['id']}_reply_note",
                    f"reply_plan_{conv['id']}_reply_date",
                    f"reply_plan_{conv['id']}_reply_time",
                )
                st.rerun()
    else:
        st.warning("Fenêtre WhatsApp fermée : un modèle approuvé est obligatoire.")

    st.divider()
    st.subheader("Envoyer un modèle")
    recommended_template = None
    if action and action.get("type") == "follow_up":
        recommended_template = get_recommended_template_for_action(action["id"])
        if recommended_template:
            recommended_status = recommended_template.get("template_status") or "draft"
            message = (
                f"Modèle recommandé pour cette relance : "
                f"**{recommended_template['template_name']}** "
                f"({template_status_label({'status': recommended_status})})."
            )
            if recommended_status == "approved":
                st.info(message)
            else:
                st.warning(f"{message} Il ne sera envoyable qu'après approbation WhatsApp.")

    search_key = f"template_search_{conv['id']}"
    template_search = st.session_state.get(search_key, "")
    templates = list_templates(template_search, approved_only=True)
    if not templates:
        st.info("Aucun modèle approuvé ne correspond.")
        st.text_input(
            "Recherche de modèles",
            placeholder="Mot dans le nom ou le contenu",
            key=search_key,
        )
        render_template_request_form(user, conv, action)
        return

    selected_index = 0
    if recommended_template:
        for index, item in enumerate(templates):
            if item["id"] == recommended_template.get("template_id"):
                selected_index = index
                break
    selected = st.selectbox(
        "Liste des modèles",
        templates,
        index=selected_index,
        format_func=lambda t: f"{t['name']} · {t['language']} · {labelize(t['category'])}",
        key=f"template_select_{conv['id']}",
    )
    template = get_template(selected["id"])
    st.text_input(
        "Recherche de modèles",
        placeholder="Mot dans le nom ou le contenu",
        key=search_key,
    )
    variables: dict[str, str] = {}
    for placeholder in template["placeholders"]:
        key = placeholder["placeholder_key"]
        default = default_variable_value(conv, key) or placeholder.get("example_value") or ""
        variables[key] = st.text_input(f"{{{{{key}}}}}", value=default, key=f"tpl_{template['id']}_{key}")

    resolved_body = render_template_body(template["body"], variables)
    st.markdown("Aperçu du message")
    st.markdown(
        f'<div class="sc-template-preview">{escape_html(resolved_body)}</div>',
        unsafe_allow_html=True,
    )

    if st.button("Envoyer le modèle approuvé"):
        ok, message = send_template_message(
            conv["id"],
            user["id"],
            template["id"],
            variables,
            action_outcome=action_outcome,
            next_due_at=next_due_at,
            assigned_to_user_id=assigned_to_user_id,
            note=action_note,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(
                f"reply_plan_{conv['id']}_reply_note",
                *[f"tpl_{template['id']}_{placeholder['placeholder_key']}" for placeholder in template["placeholders"]],
            )
            st.rerun()
    render_template_request_form(user, conv, action)


def render_template_request_form(user: dict, conv: dict, action: dict | None) -> None:
    flash_key = f"template_request_flash_{conv['id']}"
    flash = st.session_state.pop(flash_key, None)
    if flash:
        st.success(flash)
    st.markdown("**Demander un nouveau modèle WhatsApp**")
    st.caption("À utiliser uniquement si aucun modèle approuvé ne convient.")
    linked_task_id = action["id"] if action and action.get("type") == "follow_up" else None
    request_key_prefix = f"template_request_{conv['id']}_{linked_task_id or 'general'}"
    default_context = "" if flash else conv.get("last_message_body") or ""
    reason_key = resettable_widget_key(f"{request_key_prefix}_reason")
    context_key = resettable_widget_key(f"{request_key_prefix}_context")
    with st.form(f"template_request_{conv['id']}_{linked_task_id or 'general'}"):
        reason = st.text_input(
            "Modèle manquant",
            placeholder="Ex. relance financement pour APP",
            key=reason_key,
        )
        context = st.text_area(
            "Contexte pour le modèle",
            value=default_context,
            height=90,
            key=context_key,
        )
        submitted = st.form_submit_button("Créer la demande de modèle")
    if submitted:
        ok, message = create_template_request(
            conv["id"],
            user["id"],
            reason,
            context,
            task_id=linked_task_id,
        )
        show_result(ok, message)
        if ok:
            st.session_state[flash_key] = message
            reset_widget_key(f"{request_key_prefix}_reason")
            reset_widget_key(f"{request_key_prefix}_context")
            clear_widget_keys(reason_key, context_key)
            st.rerun()


def render_identity_review(user: dict, conv: dict) -> None:
    if not identity_needs_review(conv):
        return

    st.warning(
        "Cette fiche est temporaire ou ambiguë. Complétez les informations utiles ici, puis vérifiez SchoolDrive dès que possible."
    )
    candidates = identity_candidates(conv)
    if candidates:
        st.caption("Correspondances possibles détectées par téléphone")
        st.dataframe(
            [
                {
                    "Lead SC": item.get("lead_id") or "",
                    "SchoolDrive": item.get("schooldrive_lead_id") or "",
                    "Nom": item.get("name") or "Inconnu(e)",
                    "Cours": item.get("course") or "",
                }
                for item in candidates
            ],
            hide_index=True,
            use_container_width=True,
            height=min(180, 38 + 34 * len(candidates)),
        )

    with st.form(f"identity_review_{conv['id']}"):
        col_a, col_b = st.columns(2)
        with col_a:
            first_name = st.text_input(
                "Prénom temporaire",
                value="" if conv.get("first_name") == "Inconnu(e)" else conv.get("first_name") or "",
            )
        with col_b:
            last_name = st.text_input("Nom temporaire", value=conv.get("last_name") or "")
        category = st.text_input(
            "Catégorie de cours",
            value=conv.get("course_category_short_title") or "",
            placeholder="Ex. APP, FSM, AS",
        )
        course = st.text_input(
            "Cours / session",
            value=conv.get("course_title") or "",
            placeholder="Ex. APP GE P26",
        )
        note = st.text_area(
            "Note d'identification",
            value=conv.get("identity_review_note") or "",
            height=80,
            placeholder="Ex. prospect retrouvé par téléphone, fiche SD à créer ou à vérifier.",
        )
        submitted = st.form_submit_button("Enregistrer l'identification temporaire")
    if submitted:
        ok, message = update_temporary_identity(
            conv["id"],
            user["id"],
            first_name,
            last_name,
            category,
            course,
            note,
        )
        show_result(ok, message)
        if ok:
            st.rerun()


def identity_candidates(conv: dict) -> list[dict]:
    raw = conv.get("identity_candidates_json")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def render_qualification(user: dict, conv: dict) -> None:
    render_identity_review(user, conv)
    with st.form(f"qualification_{conv['lead_id']}"):
        lead_status = st.selectbox(
            "Qualification (probabilité que le client s'inscrive)",
            LEAD_STATUSES,
            index=safe_index(LEAD_STATUSES, conv["lead_status"]),
            format_func=labelize,
            help=HELP_TEXTS["lead_status"],
        )
        contact_status = st.selectbox(
            "Statut de contact (le prospect refuse-t-il qu'on lui écrive ?)",
            CONTACT_STATUS_VALUES,
            index=safe_index(CONTACT_STATUS_VALUES, conv.get("contact_status")),
            format_func=labelize,
            help=HELP_TEXTS["contact_status"],
        )
        submitted = st.form_submit_button("Mettre à jour")
    if submitted:
        update_lead_qualification(
            conv["lead_id"],
            user["id"],
            conv["sales_stage"],
            lead_status,
            contact_status=contact_status,
        )
        st.success("Qualification mise à jour.")
        st.rerun()


def render_next_action_summary(conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    if conv["status"] == "resolved":
        title = "Aucune action nécessaire"
        assignee = "Terminée"
        due = "Aucune échéance"
    elif action:
        title = next_action_display_title(action)
        assignee = display_assignee_name(action)
        due = format_action_datetime(action.get("due_at"))
    else:
        title = "Aucune action ouverte"
        assignee = normalize_user_display_name(None, conv.get("setter_name") or "Non assigné")
        due = "À définir"

    st.markdown(
        f"""
        <div class="sc-action-panel">
          <div>
            <div class="sc-compact-label">Prochaine action</div>
            <div class="sc-action-title">{escape_html(title)}</div>
            <div class="sc-row-meta">{escape_html(due)}</div>
          </div>
          <div class="sc-action-badges">
            <span class="sc-badge sc-badge-muted">{escape_html(assignee)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_planned_call_notice(conv: dict) -> None:
    if conv.get("status") != "open":
        return
    call = active_planned_call_for_lead(conv.get("lead_id"))
    if not call:
        return
    call_type = "setting" if call.get("type") == "setting_call" else "closing"
    assignee = display_assignee_name(call)
    due = format_due(call.get("due_at"))
    st.markdown(
        f"""
        <div class="sc-planned-call-notice">
          <strong>Appel {escape_html(call_type)} planifié</strong>
          <span>{escape_html(due)} · {escape_html(assignee)} · modifiable dans Actions</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def action_consequence(action_type: str, outcome: str) -> str:
    consequences = {
        ("setting_call", "to_closing"): "Le système planifie un appel closing à documenter pour le closer et passe le parcours en Closing.",
        ("setting_call", "not_reached"): "Le système crée un rappel d'appel, puis une relance Setter II si les rappels sont épuisés.",
        ("setting_call", "not_ready"): "Le système crée une relance Setter II à +72h.",
        ("setting_call", "not_relevant"): "Clôture la conversation et annule les relances futures.",
        ("setting_call", "do_not_contact"): "Passe le contact en Ne plus contacter, clôture la conversation et bloque les relances.",
        ("closing_call", "signed"): "Marque la vente comme signée, clôture la conversation et annule les relances.",
        ("closing_call", "will_sign"): "Le système crée une relance Setter II à +72h, puis suit le flux Va signer.",
        ("closing_call", "not_reached"): "Le système crée un rappel d'appel, puis une relance Setter II si les rappels sont épuisés.",
        ("closing_call", "undecided"): "Le système crée une relance Setter II à +72h.",
        ("closing_call", "not_relevant"): "Clôture la conversation et annule les relances futures.",
        ("contact_review", "maintain_do_not_contact"): "Maintient le blocage Ne plus contacter et clôture la conversation.",
        ("contact_review", "lift_do_not_contact"): "Le système lève le blocage et crée une action Répondre pour Setter I.",
    }
    return consequences.get((action_type, outcome), "Le système appliquera la suite prévue par la règle métier.")


def render_blocked_action(user: dict, conv: dict, action: dict) -> None:
    st.warning("Relance bloquée : modèle WhatsApp manquant.")
    requests = [
        item for item in list_template_requests()
        if item.get("task_id") == action["id"]
    ]
    if requests:
        for request in requests:
            st.caption(
                f"Demande #{request['id']} · {labelize(request['status'])} · "
                f"{request.get('reason') or 'Sans motif'}"
            )
        return

    st.info("La demande de nouveau modèle se fait dans l'onglet Conversation, sous Envoyer un modèle.")


def render_whatsapp_action_guidance(user: dict, conv: dict, action: dict) -> None:
    if action["type"] == "reply":
        st.info("Le client attend une réponse. Cette action sera clôturée quand le message sera envoyé dans l'onglet Conversation.")
        st.caption("L'envoi se fait dans l'onglet Conversation. Sélectionnez la suite après envoi ici.")
        render_reply_send_plan_controls(action, f"reply_plan_{conv['id']}", list_users())
        return

    if action["type"] == "follow_up":
        if action.get("status") == "blocked":
            render_blocked_action(user, conv, action)
            return
        if conv["window_is_open"]:
            st.info("Relance à envoyer. La fenêtre WhatsApp est ouverte : message libre ou modèle approuvé possible.")
        else:
            st.warning("Relance à envoyer. Fenêtre WhatsApp fermée : modèle approuvé obligatoire.")
        st.caption("L'action sera clôturée uniquement quand le message ou le modèle aura été envoyé dans l'onglet Conversation.")


def render_call_action_form(user: dict, action: dict) -> None:
    users = list_users()
    current_dt = (parse_dt(action.get("due_at")) or utc_now()).astimezone(DISPLAY_TZ)
    current_date = current_dt.date()
    current_time = current_dt.time().replace(second=0, microsecond=0)
    reached_outcomes = [
        value for value in ACTION_OUTCOMES[action["type"]]
        if value != "not_reached"
    ]
    reached = st.radio(
        "Avez-vous pu joindre le prospect ?",
        ["yes", "no"],
        horizontal=True,
        format_func=lambda value: "Oui" if value == "yes" else "Non",
        key=f"call_reached_{action['id']}",
    )
    with st.form(f"call_action_form_{action['id']}"):
        if reached == "no":
            outcome = "not_reached"
            note = "Prospect non joint."
            assigned_to_user_id = None
            next_due_at = None
        else:
            outcome = st.selectbox(
                "Résultat de l'appel",
                reached_outcomes,
                format_func=labelize,
                key=f"call_outcome_{action['id']}",
            )
            st.caption(action_consequence(action["type"], outcome))
            note = st.text_area("Note d'appel obligatoire", height=100, key=f"call_note_{action['id']}")
            assigned_to_user_id = None
            next_due_at = None
            if outcome == "to_closing":
                closers = [item for item in users if item["role"] == "closer"]
                if closers:
                    closer = st.selectbox(
                        "Closer",
                        closers,
                        format_func=format_user,
                        key=f"call_closer_{action['id']}",
                    )
                    assigned_to_user_id = closer["id"]
                next_date = st.date_input(
                    "Date du rendez-vous",
                    value=local_today(),
                    key=f"call_date_{action['id']}",
                    format=DATE_INPUT_FORMAT,
                )
                next_time = st.time_input(
                    "Heure",
                    value=time(9, 0),
                    step=timedelta(minutes=1),
                    key=f"call_time_{action['id']}",
                )
                next_due_at = local_due_at(next_date, next_time)
        submitted = st.form_submit_button("Enregistrer le résultat")
    if submitted:
        if not note.strip():
            st.error("Une note d'appel est obligatoire.")
            return
        ok, message = complete_action_with_workflow(
            action["id"],
            user["id"],
            outcome,
            note=note,
            next_due_at=next_due_at,
            assigned_to_user_id=assigned_to_user_id,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(
                f"call_note_{action['id']}",
                f"call_date_{action['id']}",
                f"call_time_{action['id']}",
                f"call_closer_{action['id']}",
            )
            st.rerun()

    with st.expander("Déplacer ou annuler le RDV", expanded=False):
        with st.form(f"reschedule_call_form_{action['id']}"):
            next_date = st.date_input(
                "Nouvelle date",
                value=current_date,
                key=f"reschedule_date_{action['id']}",
                format=DATE_INPUT_FORMAT,
            )
            next_time = st.time_input(
                "Nouvelle heure",
                value=current_time,
                step=timedelta(minutes=1),
                key=f"reschedule_time_{action['id']}",
            )
            note = st.text_area(
                "Note de déplacement obligatoire",
                height=80,
                key=f"reschedule_note_{action['id']}",
            )
            submitted = st.form_submit_button("Déplacer le RDV")
        if submitted:
            if not note.strip():
                st.error("Une note de déplacement est obligatoire.")
                return
            ok, message = reschedule_call_action(
                action["id"],
                user["id"],
                local_due_at(next_date, next_time),
                note.strip(),
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(
                    f"reschedule_note_{action['id']}",
                    f"reschedule_date_{action['id']}",
                    f"reschedule_time_{action['id']}",
                )
                st.rerun()

        with st.form(f"cancel_call_form_{action['id']}"):
            note = st.text_area(
                "Note d'annulation obligatoire",
                height=80,
                key=f"cancel_call_note_{action['id']}",
            )
            submitted = st.form_submit_button("Annuler sans nouveau RDV")
        if submitted:
            if not note.strip():
                st.error("Une note d'annulation est obligatoire.")
                return
            ok, message = cancel_call_action_without_replacement(
                action["id"],
                user["id"],
                note.strip(),
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(f"cancel_call_note_{action['id']}")
                st.rerun()


def render_contact_review_action(user: dict, action: dict) -> None:
    is_do_not_contact = action.get("contact_status") == "do_not_contact"
    is_terminal_qualification = action.get("lead_status") in {"not_relevant", "signed"}
    if is_do_not_contact:
        st.warning("Ce prospect est marqué Ne plus contacter, mais il a réécrit. Lisez le message avant de décider.")
    elif is_terminal_qualification:
        st.warning("Ce prospect a une qualification terminale, mais il a réécrit. Lisez le message avant de décider.")
    else:
        st.warning("Ce prospect nécessite une revue humaine avant de répondre.")
    note = st.text_area("Note de revue", height=80, key=f"contact_review_note_{action['id']}")
    cols = st.columns(2)
    if is_do_not_contact:
        if cols[0].button("Maintenir Ne plus contacter", use_container_width=True, key=f"maintain_dnc_{action['id']}"):
            ok, message = complete_action_with_workflow(
                action["id"],
                user["id"],
                "maintain_do_not_contact",
                note=note,
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(f"contact_review_note_{action['id']}")
                st.rerun()
        if cols[1].button("Lever et répondre", use_container_width=True, key=f"lift_dnc_{action['id']}"):
            ok, message = complete_action_with_workflow(
                action["id"],
                user["id"],
                "lift_do_not_contact",
                note=note,
            )
            show_result(ok, message)
            if ok:
                clear_widget_keys(f"contact_review_note_{action['id']}")
                st.rerun()
        return

    if cols[0].button("Maintenir la clôture", use_container_width=True, key=f"keep_terminal_{action['id']}"):
        ok, message = complete_action_with_workflow(
            action["id"],
            user["id"],
            "keep_terminal_status",
            note=note,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(f"contact_review_note_{action['id']}")
            st.rerun()
    if cols[1].button("Requalifier et répondre", use_container_width=True, key=f"requalify_reply_{action['id']}"):
        ok, message = complete_action_with_workflow(
            action["id"],
            user["id"],
            "requalify_and_reply",
            note=note,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(f"contact_review_note_{action['id']}")
            st.rerun()


def render_other_action_form(user: dict, action: dict) -> None:
    st.info("Action de revue humaine. Ajoutez une note indiquant ce qui a été fait, puis marquez l'action terminée.")
    with st.form(f"other_action_form_{action['id']}"):
        note = st.text_area("Note obligatoire", height=90, key=f"other_action_note_{action['id']}")
        submitted = st.form_submit_button("Marquer l'action terminée")
    if submitted:
        if not note.strip():
            st.error("Ajoutez une note pour terminer cette action.")
            return
        ok, message = complete_action_with_workflow(
            action["id"],
            user["id"],
            "done",
            note=note,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(f"other_action_note_{action['id']}")
            st.rerun()


def render_standard_action_planner(user: dict, conv: dict, users: list[dict], active_assignee_id: int) -> None:
    if conv.get("status") != "open":
        return

    st.markdown("**Programmer / attribuer une action**")
    st.caption("Choisissez la prochaine action standard. Elle remplace l'action ouverte actuelle et garde une note dans le fil. Si un appel est déjà planifié, une réponse urgente peut être ajoutée sans annuler l'appel.")
    action_type = st.selectbox(
        "Action",
        STANDARD_NEXT_ACTION_TYPES,
        format_func=standard_action_button_label,
        key=f"standard_action_type_{conv['id']}",
    )
    active_call = active_planned_call_for_lead(conv.get("lead_id"))
    followup_blocked_by_call = action_type == "follow_up" and active_call is not None
    if action_type == "reply" and active_call:
        st.info("Un appel est déjà planifié. La réponse sera ajoutée sans annuler cet appel.")
    if followup_blocked_by_call:
        st.warning("Un appel est déjà planifié. Ne planifiez pas une relance parallèle : modifiez l'appel ou ajoutez une réponse urgente si nécessaire.")
    assignee_options = standard_action_assignee_options(users, action_type)
    if not assignee_options:
        st.warning("Aucun responsable compatible avec cette action.")
        return

    default_assignee = active_assignee_id
    if not any(item["id"] == default_assignee for item in assignee_options):
        default_assignee = assignee_options[0]["id"]

    assignee = st.selectbox(
        "Responsable",
        assignee_options,
        index=safe_user_index(assignee_options, default_assignee),
        format_func=format_user,
        key=f"standard_action_assignee_{conv['id']}_{action_type}",
    )
    action_date = st.date_input(
        "Date",
        value=local_today(),
        key=f"standard_action_date_{conv['id']}",
        format=DATE_INPUT_FORMAT,
    )
    action_time = st.time_input(
        "Heure",
        value=time(9, 0),
        step=timedelta(minutes=1),
        key=f"standard_action_time_{conv['id']}",
    )
    note = st.text_area(
        "Note obligatoire",
        height=80,
        key=f"standard_action_note_{conv['id']}",
        placeholder="Ex. RDV confirmé demain à 14h, relance à faire après lecture de la conversation.",
    )
    submitted = st.button(
        standard_action_button_label(action_type),
        key=f"standard_action_submit_{conv['id']}",
        disabled=not note.strip() or followup_blocked_by_call,
    )
    if submitted:
        ok, message = assign_standard_next_action(
            conv["id"],
            user["id"],
            action_type,
            assignee["id"],
            local_due_at(action_date, action_time),
            note,
        )
        show_result(ok, message)
        if ok:
            clear_widget_keys(
                f"standard_action_note_{conv['id']}",
                f"standard_action_date_{conv['id']}",
                f"standard_action_time_{conv['id']}",
            )
            st.rerun()


def render_next_action_box(user: dict, conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    users = list_users()
    active_assignee_id = default_assignee_id(conv, action, user)

    if action:
        if action.get("status") == "blocked":
            render_blocked_action(user, conv, action)
        elif action["type"] in {"reply", "follow_up"}:
            render_whatsapp_action_guidance(user, conv, action)
        elif action["type"] in CALL_ACTION_TYPES:
            render_call_action_form(user, action)
        elif action["type"] == "contact_review":
            render_contact_review_action(user, action)
        else:
            render_other_action_form(user, action)
    elif conv["status"] == "open":
        st.warning("Anomalie : cette conversation est ouverte sans prochaine action.")
        st.caption("Programmez immédiatement une action principale avec le bloc ci-dessous.")
    else:
        st.info("Aucune action ouverte pour cette conversation.")

    if conv["status"] == "open":
        st.divider()
        render_standard_action_planner(user, conv, users, active_assignee_id)
    else:
        st.caption("Conversation terminée : utilisez Réactiver en haut de la fiche pour créer une nouvelle action.")

    actions = list_actions_for_lead(conv["lead_id"], "all")
    if actions:
        st.divider()
        st.markdown("**Historique des actions**")
        for item in actions:
            proof = " · preuve message" if item.get("proof_message_id") else ""
            outcome = f" · {item['outcome']}" if item.get("outcome") else ""
            st.caption(
                f"{item['title']} · {labelize(item['type'])} · {labelize(item['status'])} · "
                f"{display_assignee_name(item)} · {format_due(item.get('due_at'))}"
                f"{outcome}{proof}"
            )


def render_manual_note_box(user: dict, conv: dict) -> None:
    note_base_key = f"manual_note_body_{conv['id']}"
    note_key = resettable_widget_key(note_base_key)
    with st.form(f"manual_note_{conv['id']}"):
        body = st.text_area("Résumé ou transcript privé", height=130, key=note_key)
        submitted = st.form_submit_button("Ajouter la note privée")
    if submitted:
        if not body.strip():
            st.error("Écris une note avant de l'ajouter.")
            return
        ok, message = add_manual_note(conv["id"], user["id"], body.strip(), True)
        show_result(ok, message)
        if ok:
            reset_widget_key(note_base_key)
            clear_widget_keys(note_key)
            st.rerun()


@st.fragment(run_every="10s")
def render_work_queue(user: dict) -> None:
    users = list_users()
    assignee_options = [{"id": "all", "full_name": "Tous", "role": "all"}] + users
    assignee_by_id = {
        option["id"]: option
        for option in assignee_options
    }
    default_assignee_id = user["id"]
    if st.session_state.get("work_queue_assignee_user_id") != user["id"]:
        st.session_state.work_queue_assignee_selected_id = default_assignee_id
        st.session_state.pop("work_queue_assignee_widget", None)
        st.session_state.work_queue_assignee_user_id = user["id"]

    selected_assignee_id = st.session_state.get("work_queue_assignee_selected_id", default_assignee_id)
    if selected_assignee_id not in assignee_by_id:
        selected_assignee_id = default_assignee_id
    assignee_ids = [option["id"] for option in assignee_options]
    selected_assignee_index = assignee_ids.index(selected_assignee_id)

    st.title("Tâches")
    filter_col, header_col = st.columns([0.95, 1.45], gap="large")
    with filter_col:
        selected_assignee_id = st.selectbox(
            "Responsable",
            assignee_ids,
            index=selected_assignee_index,
            format_func=lambda assignee_id: format_assignee_filter(
                assignee_by_id[assignee_id],
                current_user_id=user["id"],
            ),
            key="work_queue_assignee_widget",
        )
    st.session_state.work_queue_assignee_selected_id = selected_assignee_id
    assignee_filter = assignee_by_id[selected_assignee_id]

    tasks = list_tasks("all")
    if assignee_filter["id"] != "all":
        tasks = [
            task for task in tasks
            if task.get("assigned_to_user_id") == assignee_filter["id"]
        ]
    admin_actions = list_admin_actions("open") if user.get("role") == "admin" else []
    if assignee_filter["id"] != "all":
        admin_actions = [
            action for action in admin_actions
            if action.get("assigned_to_user_id") == assignee_filter["id"]
        ]
    tasks = sort_work_items(tasks, "attention")

    if admin_actions:
        render_admin_work_queue(user, admin_actions)

    if not tasks:
        st.info("Aucune action commerciale pour ce filtre.")
        return

    tasks_by_queue = {
        queue: tasks if queue == "all" else [
            task for task in tasks if classify_action_queue(task) == queue
        ]
        for queue in ACTION_QUEUES
    }
    visible_task_ids = {task["id"] for task in tasks}
    if st.session_state.get("selected_action_id") not in visible_task_ids:
        default = next(
            (
                queue_tasks[0]
                for queue_tasks in tasks_by_queue.values()
                if queue_tasks
            ),
            tasks[0],
        )
        st.session_state.selected_action_id = default["id"]
    selected_task = next(
        task for task in tasks
        if task["id"] == st.session_state.selected_action_id
    )

    with header_col:
        st.markdown('<div class="sc-search-field-offset"></div>', unsafe_allow_html=True)
        if selected_task.get("conversation_id"):
            render_conversation_header(user, selected_task["conversation_id"])

    left, right = st.columns([0.95, 1.45], gap="large")
    with left:
        st.subheader("File de travail")
        tabs = st.tabs(
            [
                f"{queue_label(queue)} ({len(tasks_by_queue[queue])})"
                for queue in ACTION_QUEUES
            ]
        )
        for index, queue in enumerate(ACTION_QUEUES):
            with tabs[index]:
                render_action_rows(tasks_by_queue[queue], queue)

    with right:
        if selected_task.get("conversation_id"):
            render_conversation_detail(user, selected_task["conversation_id"])
        else:
            st.info("Cette action n'est liée à aucune conversation.")


def render_action_rows(tasks: list[dict], bucket: str) -> None:
    if not tasks:
        st.info("Aucune action dans cette file.")
        return

    for task in tasks:
        selected = st.session_state.get("selected_action_id") == task["id"]
        button_type = "primary" if selected else "secondary"
        with st.container(border=True):
            text_col, action_col = st.columns([0.78, 0.22], vertical_alignment="center")
            with text_col:
                st.markdown(action_row_html(task), unsafe_allow_html=True)
            with action_col:
                if st.button(
                    "Voir",
                    key=f"open_action_{bucket}_{task['id']}",
                    type=button_type,
                    use_container_width=True,
                ):
                    st.session_state.selected_action_id = task["id"]
                    if task.get("conversation_id"):
                        st.session_state.selected_conversation_id = task["conversation_id"]
                    st.rerun()


def render_admin_work_queue(user: dict, actions: list[dict]) -> None:
    st.subheader("Actions admin")
    st.caption("Demandes de modèles, bugs et revues techniques à traiter par un admin.")
    rows = [
        {
            "ID": item["id"],
            "Type": labelize(item["type"]),
            "Titre": item["title"],
            "Prospect": lead_display_name(item),
            "Statut": labelize(item["status"]),
            "Assignée à": item.get("assigned_to_name") or "Admin",
            "Échéance": format_due(item.get("due_at")),
        }
        for item in actions
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True, height=min(260, 72 + 36 * len(rows)))
    with st.form("complete_admin_work_action_form"):
        action = st.selectbox(
            "Action admin à terminer",
            actions,
            format_func=lambda item: f"#{item['id']} · {item['title']}",
        )
        outcome = st.text_input("Résolution", value="Traité")
        submitted = st.form_submit_button("Marquer terminée", disabled=not outcome.strip())
    if submitted:
        ok, message = complete_admin_action(action["id"], user["id"], outcome.strip())
        show_result(ok, message)
        if ok:
            st.rerun()


def action_row_html(task: dict) -> str:
    lead_type = escape_html(labelize(task.get("lead_type") or "lead"))
    identity_badge = identity_badge_html(task)
    name = escape_html(lead_display_name(task))
    course = escape_html(conversation_course_label(task))
    owner = escape_html(display_assignee_name(task))
    action_type = escape_html(labelize(task.get("type")))
    title = escape_html(compact_text(action_display_title(task.get("title") or "Action sans titre"), 92))
    due = escape_html(format_due(task.get("due_at")))
    urgency = escape_html(labelize(task.get("urgency") or "normal"))
    waiting = client_waiting_state(task)
    waiting_html = (
        f'<div class="sc-hot-signal">🔥 {escape_html(waiting)}</div>'
        if waiting
        else ""
    )
    return f"""
        <div class="sc-conversation-row">
          <div class="sc-lead-type-line">{lead_type}{identity_badge}</div>
          <div class="sc-conversation-title"><strong>{name}</strong></div>
          <div class="sc-row-meta">{course} · {owner}</div>
          {waiting_html}
          <div class="sc-next-action-line"><span>{action_type}</span> · {title}</div>
          <div class="sc-row-meta">{due} · {urgency}</div>
        </div>
    """


def classify_action_queue(task: dict) -> str:
    if task.get("status") in {"done", "cancelled"}:
        return "completed"
    due_at = parse_dt(task.get("due_at"))
    if due_at and due_at > utc_now():
        return "future"
    return "due"


def render_user_guide() -> None:
    guide_path = ROOT_DIR / "docs" / "USER_GUIDE.md"
    try:
        guide = guide_path.read_text(encoding="utf-8")
    except OSError as exc:
        st.error(f"Mode d'emploi indisponible : {exc}")
        return
    st.markdown(guide)


def render_templates(user: dict) -> None:
    st.title("Modèles WhatsApp")
    is_admin = user.get("role") == "admin"
    settings = get_settings()
    twilio_mode = (settings.twilio_mode or "mock").lower()
    twilio_read_only = bool(settings.twilio_content_read_only)
    request_flash = st.session_state.pop("template_page_flash", None)
    if request_flash:
        st.success(request_flash)

    if is_admin:
        sync_col, sync_note_col = st.columns([0.22, 0.78], vertical_alignment="center")
        with sync_col:
            if st.button("Synchroniser Twilio", use_container_width=True):
                ok, message = sync_twilio_templates(user["id"])
                show_result(ok, message)
                if ok:
                    st.rerun()
        with sync_note_col:
            caption = "Récupère les templates Twilio, leurs ContentSid et leurs statuts d'approbation WhatsApp."
            if twilio_read_only:
                caption += " Mode lecture seule : aucune création ni soumission Twilio possible."
            st.caption(caption)
    else:
        st.info("Vous pouvez consulter les modèles. Seuls les admins peuvent créer ou synchroniser des modèles WhatsApp.")

    templates_for_linking = template_link_options(list_templates())
    st.subheader("Demandes de modèles à créer")
    requests = [
        item for item in list_template_requests()
        if item.get("status") in {"to_create", "submitted"}
    ]
    if requests:
        st.dataframe(requests, hide_index=True, use_container_width=True, height=220)
        if is_admin:
            with st.form("link_template_request_form"):
                request_to_link = st.selectbox(
                    "Demande à lier",
                    requests,
                    format_func=lambda item: f"#{item['id']} · {lead_display_name(item)} · {item.get('reason') or 'Sans motif'}",
                )
                linked_template = st.selectbox(
                    "Template Twilio synchronisé",
                    templates_for_linking,
                    index=template_link_index(templates_for_linking, request_to_link.get("template_id")),
                    format_func=template_link_label,
                )
                new_status = st.selectbox(
                    "Statut de la demande",
                    ["to_create", "submitted", "approved", "rejected", "cancelled"],
                    index=safe_index(
                        ["to_create", "submitted", "approved", "rejected", "cancelled"],
                        request_to_link.get("status"),
                    ),
                    format_func=labelize,
                )
                link_submitted = st.form_submit_button("Mettre à jour le lien")
            if link_submitted:
                selected_template_id = int(linked_template["id"]) if linked_template.get("id") else None
                ok, message = update_template_request_status(
                    request_to_link["id"],
                    user["id"],
                    new_status,
                    selected_template_id,
                )
                show_result(ok, message)
                if ok:
                    st.rerun()
        if is_admin and not twilio_read_only:
            with st.expander("Créer un modèle Twilio depuis une demande", expanded=False):
                with st.form("create_template_from_request"):
                    request = st.selectbox(
                        "Demande",
                        requests,
                        format_func=lambda item: f"#{item['id']} · {lead_display_name(item)} · {item.get('reason') or 'Sans motif'}",
                    )
                    name = st.text_input("Nom Twilio", value=f"demande_modele_{request['id']}")
                    body = st.text_area(
                        "Corps du modèle",
                        value="",
                        placeholder="Bonjour {{first_name}}, ...",
                        height=120,
                    )
                    category = st.selectbox(
                        "Catégorie WhatsApp",
                        ["utility", "marketing", "authentication"],
                        format_func=labelize,
                    )
                    placeholders_raw = st.text_input("Placeholders", value="first_name, course_title")
                    confirm_twilio_write = st.checkbox(
                        "Je confirme que cette action écrit dans le compte Twilio configuré.",
                        value=False,
                    )
                    submitted = st.form_submit_button("Créer dans Twilio et soumettre")
                if submitted:
                    if not name.strip() or not body.strip():
                        st.error("Ajoutez un nom et un corps de modèle.")
                        return
                    if not confirm_twilio_write:
                        st.error("Confirmez explicitement l'écriture dans Twilio avant de créer le modèle.")
                        return
                    placeholders = {
                        item.strip(): ""
                        for item in placeholders_raw.split(",")
                        if item.strip()
                    }
                    ok, message, template_id = create_and_submit_twilio_template(
                        user["id"],
                        name.strip(),
                        body.strip(),
                        category=category,
                        placeholders=placeholders,
                        submit_for_approval=True,
                    )
                    if ok and template_id:
                        update_template_request_status(
                            request["id"],
                            user["id"],
                            "submitted",
                            template_id,
                        )
                    show_result(ok, message)
                    if ok:
                        st.session_state.template_page_flash = (
                            "Modèle créé dans Twilio et lié à la demande. "
                            "Il sera utilisable dès approbation WhatsApp."
                        )
                        st.rerun()
        elif is_admin and twilio_read_only:
            st.caption("Compte Twilio en lecture seule : les demandes sont listées, mais la création Twilio est désactivée ici.")
        else:
            st.caption("Les demandes seront traitées par un admin.")
    else:
        st.info("Aucune demande de modèle à traiter.")

    st.divider()
    filter_col, search_col = st.columns([0.30, 0.70], vertical_alignment="bottom")
    with filter_col:
        source_filter = st.selectbox(
            "Source",
            ["twilio", "demo", "all"],
            index=0 if twilio_mode != "mock" else 2,
            format_func={
                "twilio": "Twilio",
                "demo": "Démo locale",
                "all": "Tout afficher",
            }.get,
        )
    with search_col:
        search = st.text_input("Recherche dynamique", placeholder="Ex. financement, rendez-vous, COVID")
    all_templates = list_templates(search)
    templates = [
        template for template in all_templates
        if template_matches_source_filter(template, source_filter)
    ]
    st.subheader("Bibliothèque")
    st.caption(
        f"{len(templates)} modèle(s) affiché(s). "
        "La recherche porte sur le nom, le contenu et la catégorie."
    )
    for template in templates:
        with st.container(border=True):
            cols = st.columns([0.58, 0.22, 0.20], vertical_alignment="center")
            with cols[0]:
                st.write(f"**{template['name']}**")
                sid = template.get("twilio_content_sid") or "Aucun ContentSid"
                content_type = labelize(template.get("twilio_content_type") or "twilio/text")
                st.caption(f"{template_source_label(template)} · {sid} · {content_type}")
            with cols[1]:
                st.caption(
                    f"{template_status_label(template)} · "
                    f"{template['language']} · {labelize(template['category'])}"
                )
            with cols[2]:
                if template.get("last_twilio_sync_at"):
                    st.caption(f"Sync {format_dt(template['last_twilio_sync_at'])}")
            st.write(template["body"])
            if template.get("rejection_reason"):
                st.error(f"Rejet WhatsApp : {template['rejection_reason']}")

    st.divider()
    st.subheader("Créer un modèle")
    if not is_admin:
        st.info("Création réservée aux admins.")
        return
    if twilio_read_only:
        st.info("Compte Twilio en lecture seule : création et soumission de modèles désactivées dans cet environnement.")
        return

    with st.form("create_twilio_template"):
        linked_requests = [{"id": 0, "label": "Aucune demande liée"}] + [
            {
                "id": item["id"],
                "label": f"#{item['id']} · {lead_display_name(item)} · {item.get('reason') or 'Sans motif'}",
            }
            for item in requests
        ]
        linked_request = st.selectbox(
            "Demande liée",
            linked_requests,
            format_func=lambda item: item["label"],
        )
        name = st.text_input("Nom Twilio", placeholder="relance_financement_fsm")
        body = st.text_area(
            "Corps du modèle",
            placeholder="Bonjour {{first_name}}, je reviens vers vous au sujet de {{course_title}}.",
            height=120,
        )
        category = st.selectbox(
            "Catégorie WhatsApp",
            ["utility", "marketing", "authentication"],
            format_func=labelize,
        )
        placeholders_raw = st.text_input("Placeholders", placeholder="first_name, course_title")
        submit_for_approval = st.checkbox("Soumettre immédiatement pour approbation WhatsApp", value=True)
        confirm_twilio_write = st.checkbox(
            "Je confirme que cette action écrit dans le compte Twilio configuré.",
            value=False,
        )
        submitted = st.form_submit_button("Créer le modèle Twilio")
    if submitted:
        if not name.strip() or not body.strip():
            st.error("Ajoutez un nom et un corps de modèle.")
            return
        if not confirm_twilio_write:
            st.error("Confirmez explicitement l'écriture dans Twilio avant de créer le modèle.")
            return
        placeholders = {
            item.strip(): ""
            for item in placeholders_raw.split(",")
            if item.strip()
        }
        ok, message, template_id = create_and_submit_twilio_template(
            user["id"],
            name.strip(),
            body.strip(),
            category=category,
            placeholders=placeholders,
            submit_for_approval=submit_for_approval,
        )
        if ok and template_id and linked_request.get("id"):
            update_template_request_status(
                int(linked_request["id"]),
                user["id"],
                "submitted" if submit_for_approval else "to_create",
                template_id,
            )
        show_result(ok, message)
        if ok:
            st.rerun()


def format_sequence_step(step: dict) -> str:
    action = sequence_step_action_label(step.get("action_type"))
    return (
        f"{step['sequence_code']} #{step['step_index']} · "
        f"{sequence_step_timing_label(step)} · {action} · {step['meaning']}"
    )


def sequence_step_action_label(action_type: str | None) -> str:
    return SEQUENCE_STEP_ACTION_LABELS.get(action_type or "", labelize(action_type))


def sequence_step_timing_label(step: dict) -> str:
    amount = int(step.get("offset_amount") or 0)
    unit = SEQUENCE_STEP_OFFSET_UNIT_LABELS.get(step.get("offset_unit"), "heures")
    direction = step.get("offset_direction") or "after"
    if direction == "before":
        return f"Déclencheur - {amount} {unit}"
    return f"Déclencheur + {amount} {unit}"


def sequence_step_delay_short(step: dict) -> str:
    amount = int(step.get("offset_amount") or 0)
    unit = "j" if step.get("offset_unit") == "days" else "h"
    sign = "-" if step.get("offset_direction") == "before" else "+"
    return f"T{sign}{amount}{unit}"


def template_matches_source_filter(template: dict, source_filter: str) -> bool:
    if source_filter == "twilio":
        return is_real_twilio_template(template)
    if source_filter == "demo":
        return is_demo_template(template)
    return True


def is_real_twilio_template(template: dict) -> bool:
    sid = str(template.get("twilio_content_sid") or "")
    return sid.startswith("HX") and not sid.startswith("HX_MOCK_")


def is_demo_template(template: dict) -> bool:
    sid = str(template.get("twilio_content_sid") or "")
    return sid.startswith("HX_MOCK_") or not sid


def is_approved_real_twilio_template(template: dict) -> bool:
    return is_real_twilio_template(template) and template.get("status") == "approved"


def template_link_options(templates: list[dict]) -> list[dict]:
    return [{"id": 0, "name": "Aucun template lié", "status": "", "twilio_content_sid": ""}] + [
        item for item in templates if is_real_twilio_template(item)
    ]


def template_link_index(options: list[dict], template_id: int | None) -> int:
    for index, item in enumerate(options):
        if item.get("id") == template_id:
            return index
    return 0


def template_link_label(template: dict) -> str:
    if not template.get("id"):
        return "Aucun template lié"
    sid = template.get("twilio_content_sid") or "Sans SID"
    return f"{template['name']} · {template_status_label(template)} · {sid}"


def mapping_has_approved_real_template(mapping: dict) -> bool:
    sid = str(mapping.get("twilio_content_sid") or "")
    return (
        mapping.get("template_status") == "approved"
        and sid.startswith("HX")
        and not sid.startswith("HX_MOCK_")
    )


def template_source_label(template: dict) -> str:
    if is_real_twilio_template(template):
        return "Twilio"
    if is_demo_template(template):
        return "Démo locale"
    return "Local"


def template_status_label(template: dict) -> str:
    if is_real_twilio_template(template) and template.get("status") == "draft":
        return "Non soumis"
    return labelize(template.get("status"))


def page_access_matrix() -> list[dict]:
    return [
        {
            "Rôle": "Admin",
            "Tâches": True,
            "Inbox": True,
            "Pilotage": True,
            "Modèles": True,
            "Mode d'emploi": True,
            "Admin": True,
        },
        {
            "Rôle": "Setter I",
            "Tâches": True,
            "Inbox": True,
            "Pilotage": False,
            "Modèles": True,
            "Mode d'emploi": True,
            "Admin": False,
        },
        {
            "Rôle": "Setter II",
            "Tâches": True,
            "Inbox": True,
            "Pilotage": False,
            "Modèles": True,
            "Mode d'emploi": True,
            "Admin": False,
        },
        {
            "Rôle": "Closer",
            "Tâches": True,
            "Inbox": True,
            "Pilotage": False,
            "Modèles": True,
            "Mode d'emploi": True,
            "Admin": False,
        },
    ]


def render_pilotage(user: dict) -> None:
    st.title("Pilotage")
    st.caption(
        "Vue lisible pour régler les flux commerciaux : cours traités, sessions de référence, étapes, templates, conflits et vue des flux."
    )
    if user["role"] != "admin":
        st.warning("Cette page est réservée aux admins.")
        return

    tabs = st.tabs([
        "Vue d'ensemble",
        "Cours traités",
        "Sessions par défaut",
        "Étapes des flux",
        "Flux par scénario",
        "Règles de conflit",
        "Vue des flux",
    ])
    with tabs[0]:
        render_pilotage_overview()
    with tabs[1]:
        render_pilotage_course_categories(user)
    with tabs[2]:
        render_pilotage_default_sessions(user)
    with tabs[3]:
        render_pilotage_sequence_steps(user)
    with tabs[4]:
        render_pilotage_scenario_tables(user)
    with tabs[5]:
        render_pilotage_conflict_rules()
    with tabs[6]:
        render_pilotage_simulator()


def render_pilotage_overview() -> None:
    sequences = sorted(list_sequences(), key=lambda item: pilotage_sequence_sort_key(item["code"]))
    course_categories = list_course_categories()
    real_templates = [item for item in list_templates() if is_real_twilio_template(item)]
    approved_real = [item for item in real_templates if is_approved_real_twilio_template(item)]
    metric_cols = st.columns(4)
    metric_cols[0].metric("Flux actifs", len(sequences))
    metric_cols[1].metric("Templates réels", len(real_templates))
    metric_cols[2].metric("Templates approuvés", len(approved_real))
    metric_cols[3].metric("Cours traités", len(course_categories))

    category_text = ", ".join(item["course_category"] for item in course_categories) or "aucun"
    st.info(
        "V1 : les réglages d'étapes et de templates ne changent que les nouveaux flux créés après enregistrement. "
        "Les actions déjà ouvertes ne sont pas recalculées automatiquement. V2 : ajouter un bouton de recalcul contrôlé."
    )

    st.markdown("### Comment lire cette page")
    st.markdown(
        f"""
        Le réglage commercial se fait en deux temps.

        1. **Définir les flux** : décider combien de messages existent dans chaque flux et à quel moment ils partent.
        2. **Appliquer les flux aux cours** : pour chaque flux, chaque événement et chaque cours traité, choisir le template précis à envoyer.

        Cours actuellement pilotés : **{category_text}**. Les autres catégories reçues depuis SchoolDrive restent visibles, mais passent en revue humaine tant qu'elles ne sont pas ajoutées ici.

        À ne pas confondre : le **Parcours** est l'état commercial visible sur la fiche du prospect, le **Flux** est le scénario de relance réglé ici, et l'**Action** est la tâche concrète qui apparaît dans la file de travail.

        - **Sessions de référence** : règle utilisée quand SchoolDrive envoie un Lead avec une catégorie, mais sans session précise.
        - **Flux par scénario** : liste des événements prévus, avec le template recommandé et le message complet.
        - **Règles de conflit** : ce qui gagne quand deux flux se chevauchent, quand le prospect répond ou quand un appel est déjà planifié.
        - **Vue des flux** : prévisualisation rapide de la timeline une fois les sessions de référence définies.

        La donnée SchoolDrive réelle gagne toujours. Une session par défaut ne sert qu'à piloter les relances liées au cours quand le Lead n'a pas encore de session explicite.
        """
    )

    st.markdown("### États, flux et actions")
    st.dataframe(
        [
            {
                "Notion": "État / Parcours",
                "Question": "Où en est le prospect ?",
                "Exemples": "Nouveau lead, appel setting prévu, closing, gagné, perdu",
                "Qui le modifie": "Le système, selon le résultat des actions",
            },
            {
                "Notion": "Flux",
                "Question": "Quel scénario de suivi s'applique ?",
                "Exemples": "Lead sans réponse, échange setter sans suite, va signer, début de cours",
                "Qui le modifie": "Admin, dans Pilotage",
            },
            {
                "Notion": "Action",
                "Question": "Qui doit faire quoi et quand ?",
                "Exemples": "Répondre, envoyer relance, documenter appel setting, documenter appel closing",
                "Qui le modifie": "Utilisateur dans Tâches ou Inbox",
            },
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("### Tous les états")
    st.caption("Ces états correspondent au parcours commercial visible sur la fiche du prospect.")
    st.dataframe(PILOTAGE_STATE_ROWS, hide_index=True, use_container_width=True, height=360)

    st.markdown("### Tous les flux")
    overview_rows = [
        {
            "Ordre": pilotage_sequence_rank(item["code"]),
            "Flux": item["label"],
            "Déclencheur": item["trigger"],
            "Timeline": item["timeline"],
            "Responsable": pilotage_sequence_owner(item),
            "Arrêt": item["stop_when"],
        }
        for item in sequences
    ]
    st.dataframe(overview_rows, hide_index=True, use_container_width=True, height=300)

    st.markdown("### Toutes les actions")
    action_rows = [
        {
            "Famille": "Principale",
            "Action": item["label"],
            "Code": item["type"],
            "Sens": item["meaning"],
            "Responsable par défaut": item["default_owner"],
            "Preuve attendue": item["expected_proof"],
        }
        for item in MAIN_ACTION_TYPES
    ]
    action_rows.extend(
        {
            "Famille": "Support",
            "Action": item["support"],
            "Code": "",
            "Sens": item["role"],
            "Responsable par défaut": "",
            "Preuve attendue": item["queue_visible_when"],
        }
        for item in SUPPORT_ACTIONS
    )
    st.dataframe(action_rows, hide_index=True, use_container_width=True, height=360)


def render_pilotage_course_categories(user: dict) -> None:
    st.markdown("### Cours traités")
    st.caption(
        "Une catégorie active signifie que Sales Cockpit peut appliquer les flux structurés. "
        "Une catégorie reçue depuis SchoolDrive mais non active reste visible et crée une revue humaine pour Setter I."
    )
    categories = list_course_categories(active_only=False)
    active_categories = [item for item in categories if item.get("active")]
    if active_categories:
        rows = [
            {
                "Catégorie": item["course_category"],
                "Libellé": item.get("label") or item["course_category"],
                "Active": bool(item.get("active")),
                "Note": item.get("note") or "",
            }
            for item in categories
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True, height=240)
    else:
        st.warning("Aucun cours n'est piloté. Les leads SchoolDrive seront tous mis en revue humaine.")

    with st.form("pilotage_course_category_form"):
        st.markdown("**Ajouter ou réactiver une catégorie**")
        course_category = st.text_input("Code catégorie", placeholder="Ex. NUTR")
        label = st.text_input("Libellé", placeholder="Ex. Nutrition")
        note = st.text_area(
            "Note",
            height=80,
            placeholder="Ex. À activer quand les templates Nutrition sont validés.",
        )
        submitted = st.form_submit_button("Enregistrer la catégorie")
    if submitted:
        ok, message = upsert_course_category(user["id"], course_category, label=label, note=note)
        show_result(ok, message)
        if ok:
            st.rerun()

    if active_categories:
        with st.expander("Désactiver une catégorie", expanded=False):
            with st.form("pilotage_course_category_deactivate_form"):
                category = st.selectbox(
                    "Catégorie",
                    active_categories,
                    format_func=lambda item: f"{item['course_category']} · {item.get('label') or item['course_category']}",
                )
                submitted = st.form_submit_button("Désactiver")
            if submitted:
                ok, message = deactivate_course_category(user["id"], int(category["id"]))
                show_result(ok, message)
                if ok:
                    st.rerun()


def render_pilotage_default_sessions(user: dict) -> None:
    st.markdown("### Sessions de référence par catégorie")
    st.caption(
        "Une session de référence sert à calculer les relances liées au début du cours quand un Lead arrive avec seulement une catégorie, par exemple APP, mais sans session précise. Si SchoolDrive fournit une vraie session ou une vraie date de début, elle gagne."
    )
    active_categories = pilotage_active_categories()
    st.info(
        "Configure une session de référence pour chaque cours traité. Le lien SchoolDrive est facultatif : il sert uniquement à ouvrir rapidement la fiche de la session de référence."
    )
    sessions = list_course_default_sessions(active_only=False)
    active_sessions = [item for item in sessions if item.get("active")]
    if active_sessions:
        rows = [
            {
                "Catégorie": item["course_category"],
                "Session par défaut": item["default_course_name"],
                "Nom session": item.get("default_session_name") or "",
                "Début": item["default_start_date"],
                "URL SchoolDrive": item.get("schooldrive_url") or "",
                "Note": item.get("note") or "",
            }
            for item in active_sessions
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True, height=260)
    else:
        st.info("Aucune session de référence configurée. Ajoute une session pour chaque cours traité avant le réglage fin des flux cours.")

    missing_categories = [
        category for category in active_categories
        if category not in {item["course_category"] for item in active_sessions}
    ]
    if missing_categories:
        st.warning(f"Sessions de référence manquantes : {', '.join(missing_categories)}.")

    category_options = sorted(set(active_categories + [item["course_category"] for item in active_sessions]))
    if not category_options:
        category_options = PILOTAGE_SUPPORTED_CATEGORIES.copy()
    with st.form("course_default_session_form"):
        edit_choice = st.selectbox(
            "Catégorie",
            category_options + ["Autre"],
            index=0,
        )
        custom_category = ""
        if edit_choice == "Autre":
            custom_category = st.text_input("Nouvelle catégorie", placeholder="Ex. AMS")
        category = custom_category if edit_choice == "Autre" else edit_choice
        current = next(
            (item for item in active_sessions if item["course_category"] == category),
            None,
        )
        course_name = st.text_input(
            "Session de référence",
            value=(current or {}).get("default_course_name", ""),
            placeholder="Ex. APP VISIO E26",
            help="La session utilisée par défaut pour planifier les relances liées au début du cours si SchoolDrive ne fournit pas de session précise.",
        )
        session_name = st.text_input(
            "Libellé complémentaire, optionnel",
            value=(current or {}).get("default_session_name") or "",
            help="Champ libre si tu veux préciser un campus, une volée ou un libellé interne. Il n'est pas nécessaire si le nom de la session suffit.",
        )
        start_date = st.date_input(
            "Date de début de référence",
            value=parse_iso_date_or_today((current or {}).get("default_start_date")),
            format=DATE_INPUT_FORMAT,
        )
        schooldrive_url = st.text_input(
            "Lien SchoolDrive de la session, optionnel",
            value=(current or {}).get("schooldrive_url") or "",
            help="Facultatif. Sert uniquement de raccourci humain vers la session SchoolDrive de référence.",
        )
        note = st.text_area(
            "Note",
            value=(current or {}).get("note") or "",
            height=80,
            placeholder="Ex. Session par défaut pour les leads APP tant qu'aucune session précise n'est connue.",
        )
        submitted = st.form_submit_button("Enregistrer la session par défaut")
    if submitted:
        ok, message = upsert_course_default_session(
            user["id"],
            category,
            course_name,
            start_date.isoformat(),
            default_session_name=session_name,
            schooldrive_url=schooldrive_url,
            note=note,
        )
        show_result(ok, message)
        if ok:
            st.rerun()

    if active_sessions:
        with st.expander("Désactiver une session par défaut", expanded=False):
            with st.form("deactivate_course_default_session_form"):
                session = st.selectbox(
                    "Session",
                    active_sessions,
                    format_func=lambda item: f"{item['course_category']} · {item['default_course_name']} · {item['default_start_date']}",
                )
                submitted = st.form_submit_button("Désactiver")
            if submitted:
                ok, message = deactivate_course_default_session(user["id"], int(session["id"]))
                show_result(ok, message)
                if ok:
                    st.rerun()


def render_pilotage_sequence_steps(user: dict) -> None:
    st.markdown("### Étapes des flux")
    st.caption(
        "Chaque étape est exprimée par rapport au déclencheur du flux. "
        "Une relance WhatsApp doit avoir un template recommandé dans Flux par scénario."
    )
    st.info(
        "Ces changements affectent seulement les nouveaux flux. Les actions déjà ouvertes ne sont pas recalculées automatiquement en V1."
    )
    sequences = sorted(list_sequences(), key=lambda item: pilotage_sequence_sort_key(item["code"]))
    if not sequences:
        st.warning("Aucun flux actif.")
        return

    sequence = st.selectbox(
        "Flux",
        sequences,
        format_func=lambda item: item["label"],
        key="pilotage_steps_sequence",
    )
    steps = list_sequence_steps(sequence["code"], active_only=False)
    if steps:
        rows = [
            {
                "Étape": item["step_index"],
                "État": "Active" if item.get("active") else "Inactive",
                "Type": sequence_step_action_label(item.get("action_type")),
                "Quand": sequence_step_timing_label(item),
                "Événement": item["meaning"],
            }
            for item in steps
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True, height=260)
    else:
        st.warning("Aucune étape n'existe encore pour ce flux.")

    edit_col, add_col = st.columns(2)
    with edit_col:
        st.markdown("**Modifier une étape**")
        if steps:
            with st.form("pilotage_sequence_step_edit_form"):
                selected = st.selectbox(
                    "Étape",
                    steps,
                    format_func=lambda item: (
                        f"Étape {item['step_index']} · "
                        f"{'active' if item.get('active') else 'inactive'} · "
                        f"{sequence_step_timing_label(item)}"
                    ),
                )
                action_type = st.selectbox(
                    "Type d'action",
                    SEQUENCE_STEP_ACTION_TYPES,
                    index=SEQUENCE_STEP_ACTION_TYPES.index(selected.get("action_type") or "follow_up")
                    if (selected.get("action_type") or "follow_up") in SEQUENCE_STEP_ACTION_TYPES
                    else 0,
                    format_func=sequence_step_action_label,
                )
                timing_cols = st.columns([0.8, 0.8, 1.2])
                with timing_cols[0]:
                    offset_amount = st.number_input(
                        "Délai",
                        min_value=0,
                        max_value=365,
                        value=int(selected.get("offset_amount") or 0),
                        step=1,
                    )
                with timing_cols[1]:
                    offset_unit = st.selectbox(
                        "Unité",
                        SEQUENCE_STEP_OFFSET_UNITS,
                        index=SEQUENCE_STEP_OFFSET_UNITS.index(selected.get("offset_unit") or "hours")
                        if (selected.get("offset_unit") or "hours") in SEQUENCE_STEP_OFFSET_UNITS
                        else 0,
                        format_func=lambda value: SEQUENCE_STEP_OFFSET_UNIT_LABELS[value],
                    )
                with timing_cols[2]:
                    offset_direction = st.selectbox(
                        "Point de départ",
                        SEQUENCE_STEP_OFFSET_DIRECTIONS,
                        index=SEQUENCE_STEP_OFFSET_DIRECTIONS.index(selected.get("offset_direction") or "after")
                        if (selected.get("offset_direction") or "after") in SEQUENCE_STEP_OFFSET_DIRECTIONS
                        else 0,
                        format_func=lambda value: SEQUENCE_STEP_OFFSET_DIRECTION_LABELS[value],
                    )
                meaning = st.text_area(
                    "Événement",
                    value=selected.get("meaning") or "",
                    height=100,
                )
                submitted = st.form_submit_button("Enregistrer l'étape")
            if submitted:
                ok, message = upsert_sequence_step(
                    user["id"],
                    selected["sequence_code"],
                    int(selected["step_index"]),
                    meaning,
                    action_type=action_type,
                    offset_direction=offset_direction,
                    offset_amount=int(offset_amount),
                    offset_unit=offset_unit,
                )
                show_result(ok, message)
                if ok:
                    st.rerun()

            active_steps = [item for item in steps if item.get("active")]
            inactive_steps = [item for item in steps if not item.get("active")]
            if active_steps:
                with st.form("pilotage_sequence_step_deactivate_form"):
                    step = st.selectbox(
                        "Désactiver",
                        active_steps,
                        format_func=lambda item: f"Étape {item['step_index']} · {sequence_step_timing_label(item)}",
                    )
                    submitted = st.form_submit_button("Désactiver l'étape")
                if submitted:
                    ok, message = deactivate_sequence_step(user["id"], int(step["id"]))
                    show_result(ok, message)
                    if ok:
                        st.rerun()
            if inactive_steps:
                with st.form("pilotage_sequence_step_reactivate_form"):
                    step = st.selectbox(
                        "Réactiver",
                        inactive_steps,
                        format_func=lambda item: f"Étape {item['step_index']} · {sequence_step_timing_label(item)}",
                    )
                    submitted = st.form_submit_button("Réactiver l'étape")
                if submitted:
                    ok, message = reactivate_sequence_step(user["id"], int(step["id"]))
                    show_result(ok, message)
                    if ok:
                        st.rerun()

    with add_col:
        st.markdown("**Ajouter une étape en fin de flux**")
        with st.form("pilotage_sequence_step_add_form"):
            action_type = st.selectbox(
                "Type d'action",
                SEQUENCE_STEP_ACTION_TYPES,
                index=0,
                format_func=sequence_step_action_label,
                key="pilotage_step_add_action",
            )
            timing_cols = st.columns([0.8, 0.8, 1.2])
            with timing_cols[0]:
                offset_amount = st.number_input(
                    "Délai",
                    min_value=0,
                    max_value=365,
                    value=72,
                    step=1,
                    key="pilotage_step_add_amount",
                )
            with timing_cols[1]:
                offset_unit = st.selectbox(
                    "Unité",
                    SEQUENCE_STEP_OFFSET_UNITS,
                    index=0,
                    format_func=lambda value: SEQUENCE_STEP_OFFSET_UNIT_LABELS[value],
                    key="pilotage_step_add_unit",
                )
            with timing_cols[2]:
                offset_direction = st.selectbox(
                    "Point de départ",
                    SEQUENCE_STEP_OFFSET_DIRECTIONS,
                    index=0,
                    format_func=lambda value: SEQUENCE_STEP_OFFSET_DIRECTION_LABELS[value],
                    key="pilotage_step_add_direction",
                )
            meaning = st.text_area(
                "Événement",
                height=100,
                placeholder="Ex. Relance supplémentaire après une semaine sans réponse.",
                key="pilotage_step_add_meaning",
            )
            submitted = st.form_submit_button("Ajouter l'étape")
        if submitted:
            ok, message = add_sequence_step(
                user["id"],
                sequence["code"],
                meaning,
                action_type=action_type,
                offset_direction=offset_direction,
                offset_amount=int(offset_amount),
                offset_unit=offset_unit,
            )
            show_result(ok, message)
            if ok:
                st.rerun()


def render_pilotage_scenario_tables(user: dict) -> None:
    st.markdown("### Flux par scénario")
    st.caption(
        "Chaque étape montre le template recommandé, son SID Twilio et le message complet. "
        "Lead et Préinscription sont traités ensemble dès qu'une session de référence est connue."
    )
    categories = pilotage_categories()
    sequences = list_sequences()
    col_a, col_b = st.columns([0.8, 1.2])
    with col_a:
        category = st.selectbox("Catégorie", categories)
    with col_b:
        sequence_code = st.selectbox(
            "Flux",
            [item["code"] for item in sorted(sequences, key=lambda item: pilotage_sequence_sort_key(item["code"]))],
            format_func=label_sequence_code,
        )

    render_sequence_timeline(user, sequence_code, "all", category)


def render_pilotage_conflict_rules() -> None:
    st.markdown("### Lecture de la logique métier")
    st.caption(
        "Cette section sert à valider la logique complète : état de départ, événement, réponse du système, "
        "geste utilisateur, résolution et prochaine action. Les cas utilisent un seul cours de référence, "
        "car la logique est identique pour APP, FSM, AS et les autres cours une fois configurés."
    )

    st.markdown("### Règles transversales")
    st.caption("Ces règles gagnent quand deux flux ou événements se chevauchent.")
    for index, rule in enumerate(PILOTAGE_CONFLICT_RULES, start=1):
        st.markdown(f"**{index}. {rule['Situation']}**")
        st.write(rule["Règle"])

    st.markdown("### Tous les cas à valider")
    st.caption(
        "Les lignes `Actif` décrivent le comportement actuellement attendu du cockpit. "
        "Les lignes `Partiel / à valider` ou `V2 / à valider` signalent les règles connues mais non finalisées."
    )
    render_wrapped_table(
        pilotage_rows_with_natural_language(PILOTAGE_VALIDATION_CASES, "validation_case"),
        max_height_rem=48,
    )

    st.markdown("### Règles métier de référence")
    st.caption("Table brute des règles générales utilisées par le système et par la matrice ci-dessus.")
    render_wrapped_table(
        pilotage_rows_with_natural_language(OPERATING_RULES, "operating_rule"),
        max_height_rem=28,
    )

    st.markdown("### Table technique de transition")
    st.caption(
        "Vue plus technique : action courante + trigger + résultat -> prochaine action. "
        "Elle complète la matrice métier et sert de garde-fou pour l'implémentation."
    )
    render_wrapped_table(
        pilotage_rows_with_natural_language(WORKFLOW_TRANSITIONS, "workflow_transition"),
        max_height_rem=34,
    )


def render_wrapped_table(rows: list[dict], max_height_rem: int = 42) -> None:
    if not rows:
        st.info("Aucune donnée.")
        return

    headers = list(rows[0].keys())
    head_html = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    body_html = []
    for row in rows:
        cells = "".join(
            f"<td>{escape(str(row.get(header, '')))}</td>"
            for header in headers
        )
        body_html.append(f"<tr>{cells}</tr>")

    st.markdown(
        f"""
        <div class="sc-wrapped-table-frame" style="max-height: {max_height_rem}rem;">
          <table class="sc-wrapped-table">
            <thead><tr>{head_html}</tr></thead>
            <tbody>{''.join(body_html)}</tbody>
          </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pilotage_rows_with_natural_language(rows: list[dict], kind: str) -> list[dict]:
    output = []
    for row in rows:
        normalized = {
            key: pilotage_function_text(value)
            for key, value in row.items()
        }
        normalized["Langage naturel"] = pilotage_natural_language(normalized, kind)
        output.append(normalized)
    return output


def pilotage_natural_language(row: dict, kind: str) -> str:
    if kind == "validation_case":
        return validation_case_natural_language(row)
    if kind == "operating_rule":
        return operating_rule_natural_language(row)
    if kind == "workflow_transition":
        return workflow_transition_natural_language(row)
    return ""


def validation_case_natural_language(row: dict) -> str:
    key = (row.get("depart", ""), row.get("evenement", ""))
    text = VALIDATION_CASE_NATURAL_LANGUAGE.get(key)
    if text:
        return text
    return (
        f"Quand le dossier est dans le cas suivant : {row.get('depart', '')}. "
        f"Événement : {row.get('evenement', '')} "
        f"Le système doit alors faire ceci : {row.get('reponse_systeme', '')} "
        f"Côté équipe, voici l'action attendue : {row.get('utilisateur', '')} "
        f"La situation se termine ainsi : {row.get('resolution_action', '')} "
        f"Suite prévue : {row.get('prochaine_action', '')}"
    )


def operating_rule_natural_language(row: dict) -> str:
    text = OPERATING_RULE_NATURAL_LANGUAGE.get(row.get("rule", ""))
    if text:
        return text
    return (
        f"Règle : {row.get('rule', '')}. "
        f"À retenir : {row.get('value', '')} "
        f"Conséquence dans Sales Cockpit : {row.get('effect', '')}"
    )


def workflow_transition_natural_language(row: dict) -> str:
    key = (
        row.get("current_action", ""),
        row.get("trigger", ""),
        row.get("outcome", ""),
    )
    text = WORKFLOW_TRANSITION_NATURAL_LANGUAGE.get(key)
    if text:
        return text
    return (
        f"Quand la situation technique « {row.get('trigger', '')} » se produit "
        f"et que le résultat constaté est : {row.get('outcome', '')}, "
        f"Sales Cockpit doit créer ou conserver l'action suivante : {row.get('next_action', '')}. "
        f"Responsable : {row.get('owner', '')}. Échéance : {row.get('due', '')}. "
        f"État de la conversation : {row.get('conversation', '')}. "
        f"Point à vérifier : {row.get('required_support', '')}. "
        f"Effet système : {row.get('side_effects', '')}"
    )


def lower_first(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:1].lower() + text[1:]


VALIDATION_CASE_NATURAL_LANGUAGE = {
    (
        "Aucune conversation Cockpit",
        "SchoolDrive crée un Lead ou une Préinscription et le premier WhatsApp automatique est envoyé.",
    ): (
        "Lorsqu'une personne remplit un formulaire sur le site et que SchoolDrive crée un Lead ou une Préinscription, "
        "SchoolDrive envoie automatiquement un premier WhatsApp. Sales Cockpit ouvre alors une conversation, garde les données SchoolDrive, "
        "et prévoit une relance pour Setter II 72 heures après ce WhatsApp. Si le prospect répond avant cette relance, la relance est annulée "
        "et la conversation passe à Setter I pour réponse immédiate."
    ),
    (
        "Lead ou Préinscription reçu de SchoolDrive",
        "Le WhatsApp automatique est encore queued, absent ou non envoyé.",
    ): (
        "Lorsqu'un Lead ou une Préinscription arrive mais que le premier WhatsApp automatique n'est pas encore confirmé comme envoyé, "
        "Sales Cockpit affiche le dossier et l'historique disponible, mais ne crée pas encore de relance. L'équipe n'a rien à faire automatiquement. "
        "Dès que SchoolDrive confirme qu'un WhatsApp a bien été envoyé, Sales Cockpit pourra programmer la suite."
    ),
    (
        "Flux Lead sans réponse initiale",
        "Les 72h après le WhatsApp automatique sont écoulées et le prospect n'a pas répondu.",
    ): (
        "Lorsqu'un prospect n'a toujours pas répondu 72 heures après le premier WhatsApp automatique, la relance devient une tâche à traiter pour Setter II. "
        "Setter II doit relire la conversation, vérifier le modèle recommandé, puis envoyer le modèle adapté. Après l'envoi, Sales Cockpit prépare l'étape suivante du même flux, "
        "ou termine la conversation si c'était la dernière relance prévue."
    ),
    (
        "Toute conversation active avec relance future",
        "Le prospect écrit un message WhatsApp entrant.",
    ): (
        "Lorsqu'un prospect écrit alors qu'une relance était prévue plus tard, sa réponse devient prioritaire. Sales Cockpit annule les relances futures concernées, "
        "remonte la conversation dans la file de Setter I et crée une action urgente Répondre au message. Après la réponse de Setter I, le système crée soit une relance pour Setter II, "
        "soit un appel planifié si Setter I a fixé un rendez-vous."
    ),
    (
        "Conversation avec appel setting ou closing déjà planifié",
        "Le prospect écrit avant l'appel.",
    ): (
        "Lorsqu'un prospect écrit alors qu'un appel setting ou closing est déjà prévu, Sales Cockpit demande à Setter I de lire et répondre au message, mais ne supprime pas l'appel. "
        "L'appel reste planifié, sauf si l'utilisateur décide explicitement de le modifier. Une fois la réponse envoyée, l'appel redevient la prochaine action visible."
    ),
    (
        "Prospect marqué Ne plus contacter",
        "Le prospect réécrit malgré le blocage.",
    ): (
        "Lorsqu'un prospect marqué Ne plus contacter écrit à nouveau, Sales Cockpit ne relance pas automatiquement et bloque l'envoi tant que le statut n'est pas levé. "
        "Setter I doit lire le message et choisir entre maintenir le blocage ou lever le statut pour répondre. Si le blocage est maintenu, il n'y a pas de suite commerciale. "
        "S'il est levé, une action Répondre au message est créée."
    ),
    (
        "Message entrant d'un numéro inconnu",
        "Aucune fiche SchoolDrive/Cockpit ne correspond au numéro.",
    ): (
        "Lorsqu'un message WhatsApp arrive depuis un numéro que Sales Cockpit ne connaît pas, le système crée une fiche temporaire Inconnu(e) à identifier. "
        "L'équipe peut répondre pour ne pas perdre le prospect, puis renseigner provisoirement le prénom, le nom, le cours et une note dans Statuts. "
        "Cette fiche reste à vérifier dans SchoolDrive."
    ),
    (
        "Message entrant avec plusieurs fiches possibles",
        "Plusieurs leads ou préinscriptions correspondent au même numéro.",
    ): (
        "Lorsqu'un même numéro peut correspondre à plusieurs fiches, Sales Cockpit ne choisit pas automatiquement pour éviter une mauvaise attribution. "
        "Il crée une fiche temporaire à identifier. L'équipe peut répondre si nécessaire et noter l'identité probable, mais la fusion définitive avec la bonne fiche SchoolDrive reste une étape V2."
    ),
    (
        "Action Répondre ouverte",
        "Setter I répond sans fixer de rendez-vous et sans appliquer de statut terminal.",
    ): (
        "Lorsque Setter I répond au prospect sans fixer d'appel et sans décider que le prospect est non pertinent ou à ne plus contacter, Sales Cockpit considère que la conversation reste ouverte. "
        "Le message envoyé clôt l'action Répondre, puis le système prévoit une relance pour Setter II 72 heures après ce dernier message sortant."
    ),
    (
        "Action Répondre ouverte",
        "Setter I fixe un appel setting.",
    ): (
        "Lorsque Setter I obtient un rendez-vous de setting, il choisit l'option correspondante, indique le responsable et la date de l'appel. "
        "Le message de confirmation envoyé au prospect clôt l'action Répondre. Sales Cockpit crée ensuite une action future pour appeler le prospect et documenter l'appel setting au moment du rendez-vous."
    ),
    (
        "Action Répondre ouverte",
        "Setter I fixe directement un appel closing.",
    ): (
        "Lorsque Setter I fixe directement un appel de closing, il choisit le closer et l'heure du rendez-vous. Le message de confirmation clôt l'action Répondre. "
        "Sales Cockpit passe alors le dossier en phase closing et crée une action future pour appeler le prospect et documenter l'appel closing."
    ),
    (
        "Action Répondre ou appel en cours de traitement",
        "L'utilisateur qualifie le prospect Non pertinent.",
    ): (
        "Lorsqu'un utilisateur décide qu'un prospect n'est pas un client potentiel, il le qualifie Non pertinent. Sales Cockpit clôt alors la conversation et annule les actions ouvertes ou futures. "
        "Il ne doit plus y avoir de relance, sauf si un utilisateur réactive manuellement la conversation plus tard."
    ),
    (
        "Action Répondre ou appel en cours de traitement",
        "Le prospect demande à ne plus être contacté.",
    ): (
        "Lorsqu'un prospect demande à ne plus être contacté, l'utilisateur doit sélectionner le statut Ne plus contacter. Sales Cockpit clôt la conversation, annule les relances et bloque les futurs envois. "
        "Si le prospect réécrit lui-même plus tard, le système créera une revue humaine au lieu de reprendre automatiquement les relances."
    ),
    (
        "Relance Setter II à traiter",
        "La fenêtre WhatsApp est ouverte.",
    ): (
        "Lorsqu'une relance est à faire et que le prospect a écrit dans les dernières 24 heures, la fenêtre WhatsApp est ouverte. Setter II peut donc envoyer un message libre ou utiliser un modèle. "
        "Après l'envoi, Sales Cockpit clôt cette relance et prépare la suite du flux si une autre étape existe."
    ),
    (
        "Relance Setter II à traiter",
        "La fenêtre WhatsApp est fermée et un template approuvé est disponible.",
    ): (
        "Lorsqu'une relance doit être envoyée mais que le prospect n'a pas écrit dans les dernières 24 heures, Setter II ne peut pas écrire librement. "
        "Il doit utiliser un modèle WhatsApp approuvé. Si un modèle recommandé existe pour ce cours et cette étape, Sales Cockpit le pré-sélectionne. "
        "L'envoi du modèle clôt la relance et déclenche la suite prévue du flux."
    ),
    (
        "Relance Setter II à traiter",
        "La fenêtre WhatsApp est fermée et aucun template adapté n'existe.",
    ): (
        "Lorsqu'une relance doit partir alors que la fenêtre WhatsApp est fermée, mais qu'aucun modèle adapté n'existe, Setter II ne doit pas improviser. "
        "Sales Cockpit bloque la relance et permet de créer une demande de modèle avec le contexte. La relance restera bloquée jusqu'à ce qu'un modèle approuvé soit disponible."
    ),
    (
        "Demande de modèle ouverte",
        "Un admin crée, soumet ou synchronise le template approuvé.",
    ): (
        "Lorsqu'une demande de modèle est ouverte, un admin doit créer, soumettre ou synchroniser le modèle dans Twilio. "
        "Tant que le modèle n'est pas approuvé pour WhatsApp, la relance concernée reste bloquée. Dès qu'un modèle approuvé est lié à la demande, Setter II peut reprendre la relance."
    ),
    (
        "Flux de relance en cours",
        "Une relance intermédiaire est envoyée.",
    ): (
        "Lorsqu'une relance intermédiaire est envoyée dans un flux, Sales Cockpit considère que cette étape est terminée. "
        "Le système garde le prospect dans le même flux et programme la prochaine relance à la date prévue, sauf si le prospect répond ou si une règle prioritaire interrompt le flux."
    ),
    (
        "Dernière étape d'un flux de relance",
        "La dernière relance est envoyée et le prospect ne répond pas.",
    ): (
        "Lorsqu'on arrive à la dernière relance prévue et que le prospect ne répond toujours pas, Sales Cockpit arrête le suivi automatique. "
        "La conversation est marquée terminée avec le motif Suivi terminé sans réponse. Si le prospect réécrit plus tard, la conversation pourra se réactiver."
    ),
    (
        "Lead ou Préinscription non signé avec date de cours connue",
        "Une relance liée au début du cours tombe dans les 24h d'une relance lead/préinscription.",
    ): (
        "Lorsqu'une relance liée au début du cours doit partir dans les 24 heures d'une relance classique, la relance liée au cours est prioritaire. "
        "Sales Cockpit annule la relance lead ou préinscription concurrente pour éviter deux messages trop rapprochés. Setter II suit alors le flux Début de cours."
    ),
    (
        "Appel setting ou closing déjà planifié",
        "Une relance liée au début du cours devient éligible.",
    ): (
        "Lorsqu'un appel setting ou closing est déjà planifié, une relance liée au début du cours ne doit pas remplacer cet appel. "
        "Sales Cockpit conserve l'appel comme action principale. Le responsable doit appeler le prospect puis documenter l'appel au moment prévu."
    ),
    (
        "Catégorie de cours active sans date SchoolDrive explicite",
        "Un Lead arrive avec seulement une catégorie de cours.",
    ): (
        "Lorsqu'un Lead arrive avec une catégorie de cours mais sans session précise, Sales Cockpit utilise la session de référence définie dans Pilotage pour cette catégorie. "
        "Cette date sert à calculer les relances liées au début du cours. L'admin doit donc garder ces sessions de référence à jour."
    ),
    (
        "Catégorie de cours active",
        "La session de référence est déjà passée.",
    ): (
        "Lorsqu'une session de référence est déjà passée, Sales Cockpit ne doit pas lancer de relances Début de cours sur cette ancienne session. "
        "L'admin doit sélectionner la prochaine session pertinente. En V1, cette correction s'applique seulement aux nouvelles actions créées après modification."
    ),
    (
        "Catégorie de cours non activée dans Pilotage",
        "SchoolDrive envoie un lead ou une préinscription pour cette catégorie.",
    ): (
        "Lorsqu'un prospect arrive pour une catégorie de cours qui n'est pas encore pilotée dans Sales Cockpit, le système conserve la conversation mais ne lance pas de flux de relance structuré. "
        "Setter I doit traiter le cas manuellement et décider de la prochaine action. L'admin pourra activer cette catégorie plus tard."
    ),
    (
        "Appel setting planifié",
        "Le moment de l'appel arrive.",
    ): (
        "Lorsqu'un appel setting arrive à son heure prévue, il devient une tâche à traiter pour Setter I. "
        "Setter I doit appeler le prospect, puis documenter le résultat avec une mini-note obligatoire. Cette note détermine la suite : closing, rappel d'appel, relance Setter II ou clôture."
    ),
    (
        "Appel setting à documenter",
        "L'appel est réussi et le prospect doit passer au closing.",
    ): (
        "Lorsqu'un appel setting a eu lieu et que le prospect doit passer au closing, Setter I documente l'appel, choisit le closer et indique la date du rendez-vous de closing. "
        "Sales Cockpit crée alors une action future pour appeler le prospect et documenter l'appel closing, puis affiche la note dans la conversation."
    ),
    (
        "Appel setting à documenter",
        "Le prospect n'est pas joint.",
    ): (
        "Lorsque Setter I n'arrive pas à joindre le prospect pour l'appel setting, il doit documenter la tentative. "
        "Sales Cockpit prévoit alors des rappels d'appel, d'abord environ 2 heures ouvrées plus tard, puis environ 24 heures ouvrées plus tard. "
        "Si les rappels sont épuisés, le dossier repasse sur une relance Setter II."
    ),
    (
        "Appel setting à documenter",
        "Le prospect est joint mais aucune suite claire n'est obtenue.",
    ): (
        "Lorsque l'appel setting a eu lieu mais qu'aucune suite claire n'est obtenue, Setter I documente ce qui s'est dit. "
        "Sales Cockpit clôt l'action d'appel et prévoit une relance pour Setter II 72 heures plus tard."
    ),
    (
        "Appel setting à documenter",
        "Le prospect est non pertinent ou demande à ne plus être contacté.",
    ): (
        "Lorsque l'appel setting montre que le prospect n'est pas pertinent ou qu'il demande à ne plus être contacté, Setter I doit le noter clairement. "
        "Sales Cockpit clôt alors la conversation et annule toutes les actions futures."
    ),
    (
        "Appel closing planifié",
        "Le moment de l'appel arrive.",
    ): (
        "Lorsqu'un appel closing arrive à son heure prévue, il devient une tâche à traiter pour le closer. "
        "Le closer doit appeler le prospect puis documenter le résultat avec une mini-note obligatoire. Cette note décide de la suite : signé, va signer, indécis, non joint ou non pertinent."
    ),
    (
        "Appel closing à documenter",
        "Le prospect signe.",
    ): (
        "Lorsqu'un prospect signe après l'appel closing, le closer sélectionne A signé et ajoute la note nécessaire. "
        "Sales Cockpit marque la vente comme gagnée, clôt la conversation et annule toutes les relances futures."
    ),
    (
        "Appel closing à documenter",
        "Le closer estime que le prospect va signer.",
    ): (
        "Lorsque le closer estime que le prospect va signer mais que la signature n'est pas encore acquise, il choisit Va signer et documente le contexte. "
        "Sales Cockpit lance alors le flux Va signer : Setter II devra relancer le prospect selon les étapes prévues."
    ),
    (
        "Appel closing à documenter",
        "Le prospect n'est pas joint.",
    ): (
        "Lorsque le closer n'arrive pas à joindre le prospect pour l'appel closing, il documente la tentative. "
        "Sales Cockpit prévoit des rappels d'appel, puis une relance Setter II si les rappels ne permettent toujours pas d'obtenir une réponse."
    ),
    (
        "Appel closing à documenter",
        "Le prospect est joint mais aucune décision claire n'est obtenue.",
    ): (
        "Lorsque l'appel closing a eu lieu mais que le prospect ne prend pas de décision claire, le closer documente l'échange et choisit Indécis. "
        "Sales Cockpit clôt l'action d'appel et prévoit une relance Setter II 72 heures plus tard."
    ),
    (
        "Appel closing à documenter",
        "Le prospect est non pertinent.",
    ): (
        "Lorsque le closer conclut que le prospect n'est pas pertinent, il doit l'indiquer et documenter la raison. "
        "Sales Cockpit clôt alors la conversation et annule toutes les actions futures."
    ),
    (
        "Conversation active",
        "Un utilisateur clôt manuellement la conversation.",
    ): (
        "Lorsqu'un utilisateur veut clôturer manuellement une conversation active, il doit indiquer un motif et une note. "
        "Cette action doit être utilisée seulement lorsqu'il n'y a réellement plus rien à faire. Sales Cockpit ferme alors les actions ouvertes et marque la conversation comme terminée."
    ),
    (
        "Conversation terminée",
        "Un utilisateur réactive la conversation.",
    ): (
        "Lorsqu'un utilisateur réactive une conversation terminée, il doit expliquer pourquoi et choisir immédiatement la prochaine action principale. "
        "La conversation redevient active seulement si une suite claire est définie : répondre, relancer, appel setting ou appel closing."
    ),
    (
        "SchoolDrive record existant dans le cockpit",
        "SchoolDrive envoie un snapshot archivé.",
    ): (
        "Lorsque SchoolDrive indique qu'un Lead ou une Préinscription est archivé, Sales Cockpit aligne le dossier sur SchoolDrive. "
        "La conversation est terminée et les actions ouvertes sont fermées, sauf si l'équipe décide de vérifier manuellement un archivage qui semble incohérent."
    ),
    (
        "Webhook SchoolDrive",
        "Snapshot duplicate ou plus ancien que le snapshot déjà accepté.",
    ): (
        "Lorsque SchoolDrive renvoie un événement déjà reçu ou une version plus ancienne d'un dossier, Sales Cockpit répond OK mais ignore cette donnée. "
        "Cela évite de remplacer un état récent par une information ancienne. La conversation et les actions ne changent pas."
    ),
    (
        "Prospect écrit hors horaires",
        "Message entrant en dehors des horaires entreprise ou utilisateur.",
    ): (
        "Lorsqu'un prospect écrit en dehors des horaires, la règle cible est de préparer la réponse pour le prochain créneau ouvré et, si on le valide, d'envoyer un accusé de réception automatique. "
        "En V1, cette automatisation reste partielle : l'équipe doit encore valider les textes, les week-ends, les jours fériés et les règles de backup."
    ),
    (
        "Action attribuée à une personne absente",
        "Le responsable est indisponible.",
    ): (
        "Lorsqu'une action appartient à une personne absente, la règle cible est de transférer l'action au backup prévu sans changer la nature du travail à faire. "
        "Si aucun backup n'est défini, l'action attend. Cette bascule automatique reste à finaliser après validation des horaires et absences."
    ),
}


OPERATING_RULE_NATURAL_LANGUAGE = {
    "Origine formulaire": (
        "Le point de départ est toujours un formulaire rempli sur le site. SchoolDrive crée ensuite le Lead ou la Préinscription, puis Sales Cockpit reçoit les données depuis SchoolDrive. "
        "SchoolDrive reste la source de vérité : Sales Cockpit organise le travail commercial, mais ne remplace pas la fiche SchoolDrive."
    ),
    "Lead vs Préinscription": (
        "Un Lead vient généralement des campagnes payantes, tandis qu'une Préinscription vient plutôt du trafic naturel et peut déjà être liée à une session précise. "
        "Sales Cockpit affiche donc soit une catégorie de cours, soit un cours/session plus précis, puis applique les mêmes règles de suivi une fois la session de référence connue."
    ),
    "Fenêtre WhatsApp": (
        "La fenêtre WhatsApp s'ouvre seulement quand le prospect écrit. Elle reste ouverte 24 heures après son dernier message entrant. "
        "Pendant cette période, l'équipe peut répondre librement ; après cette période, il faut utiliser un modèle WhatsApp approuvé."
    ),
    "Premier template automatique": (
        "Le premier WhatsApp est envoyé automatiquement par SchoolDrive/Twilio après la création du Lead ou de la Préinscription. "
        "Ce message sortant n'ouvre pas la fenêtre WhatsApp. La fenêtre s'ouvre uniquement si le prospect répond."
    ),
    "Relances hors fenêtre": (
        "Quand la fenêtre WhatsApp est fermée, Setter II ne doit pas écrire un message libre. Il doit utiliser un modèle approuvé par WhatsApp. "
        "Si aucun modèle adapté n'existe, il faut créer une demande de modèle plutôt que contourner la règle."
    ),
    "Délai minimum WhatsApp": (
        "Sales Cockpit doit éviter d'envoyer deux relances WhatsApp trop rapprochées. La règle de base est de laisser au moins 24 heures entre deux relances sortantes. "
        "Si deux relances se chevauchent, la plus prioritaire est gardée et l'autre est annulée ou reportée selon la règle métier."
    ),
    "Conflit lead vs cours": (
        "Les relances liées au début d'un cours sont prioritaires sur les relances classiques calculées depuis l'arrivée du lead. "
        "Si une relance cours doit partir dans les 24 heures d'une relance lead/préinscription, la relance classique est annulée. Un appel setting ou closing déjà planifié reste toutefois prioritaire."
    ),
    "Message entrant pendant appel planifié": (
        "Si un prospect écrit alors qu'un appel est déjà prévu, il faut lui répondre sans perdre le rendez-vous. "
        "Sales Cockpit crée donc une réponse urgente pour Setter I, mais conserve l'appel planifié. L'appel ne change que si l'utilisateur le modifie volontairement."
    ),
    "Non pertinent": (
        "La qualification Non pertinent signifie que le prospect n'est pas un client potentiel utile. "
        "Quand cette qualification est appliquée, Sales Cockpit arrête les relances, clôt la conversation et ne crée plus de suite commerciale."
    ),
    "Ne plus contacter": (
        "Le statut Ne plus contacter sert quand le prospect demande à ne plus être dérangé. "
        "Il est séparé de la qualification commerciale et bloque strictement les relances. Si le prospect réécrit lui-même, une revue humaine est créée avant toute réponse."
    ),
    "Automatisation V1": (
        "En V1, Sales Cockpit prépare les tâches et recommande les modèles, mais n'envoie pas automatiquement les relances à la place de l'équipe. "
        "Setter II reste responsable de relire, vérifier et envoyer. L'automatisation complète est gardée pour une version ultérieure."
    ),
}


WORKFLOW_TRANSITION_NATURAL_LANGUAGE = {
    (
        "Aucune",
        "web_form_submitted_then_schooldrive_lead_created",
        "SchoolDrive crée un Lead ou une Préinscription et envoie le WhatsApp automatique initial",
    ): (
        "Quand un nouveau prospect arrive depuis le site, SchoolDrive crée le dossier et envoie le premier WhatsApp automatique. "
        "Sales Cockpit crée la conversation et prévoit une relance Setter II 72 heures plus tard. Si le prospect répond avant cette échéance, cette relance est annulée."
    ),
    (
        "follow_up",
        "initial_message_no_reply_after_72h",
        "Le prospect n'a pas répondu au WhatsApp automatique initial",
    ): (
        "Si 72 heures passent après le premier WhatsApp automatique sans réponse du prospect, la tâche de relance devient à traiter immédiatement pour Setter II. "
        "Setter II doit relire la conversation, choisir un modèle approuvé ou demander un nouveau modèle si nécessaire."
    ),
    (
        "Toute action non terminale",
        "prospect_replied",
        "Dernier message entrant non répondu et contact autorisé",
    ): (
        "Quand un prospect écrit et que l'équipe a encore le droit de lui répondre, Sales Cockpit donne la priorité à cette réponse. "
        "Les relances futures sont annulées, la conversation remonte chez Setter I, et un signal d'urgence indique que le client attend. Un appel déjà planifié reste conservé."
    ),
    (
        "Toute action non terminale",
        "do_not_contact_prospect_replied",
        "Le prospect est Ne plus contacter mais réécrit",
    ): (
        "Quand un prospect marqué Ne plus contacter réécrit, Sales Cockpit ne reprend pas automatiquement les relances. "
        "Il crée une revue de contact pour Setter I. Tant que Setter I n'a pas levé le blocage, aucun message ne doit être envoyé."
    ),
    (
        "reply",
        "outbound_message_sent",
        "Réponse envoyée sans RDV et aucun appel déjà planifié",
    ): (
        "Quand Setter I répond au prospect sans fixer de rendez-vous, la réponse clôt l'action immédiate. "
        "Sales Cockpit prévoit ensuite une relance Setter II 72 heures après ce message, car la conversation reste ouverte mais sans prochaine étape humaine fixée."
    ),
    (
        "reply",
        "outbound_message_sent",
        "Réponse envoyée pendant qu'un appel est déjà planifié",
    ): (
        "Quand Setter I répond à un message alors qu'un appel est déjà prévu, Sales Cockpit clôt seulement l'interruption liée au message entrant. "
        "Il ne crée pas de relance parallèle. L'appel planifié redevient la prochaine action."
    ),
    (
        "reply",
        "setting_appointment_booked",
        "RDV setting fixé",
    ): (
        "Quand Setter I fixe un appel setting, Sales Cockpit annule la relance de sécurité et crée une action future pour documenter cet appel. "
        "Cette action sera due à la date et à l'heure du rendez-vous."
    ),
    (
        "reply",
        "written_exchange_terminal",
        "Prospect non pertinent ou Ne plus contacter",
    ): (
        "Quand l'échange écrit montre que le prospect n'est pas pertinent ou qu'il ne veut plus être contacté, Sales Cockpit arrête le suivi. "
        "Aucune nouvelle action n'est créée et les relances sont stoppées."
    ),
    (
        "follow_up",
        "follow_up_due",
        "Fenêtre WhatsApp ouverte",
    ): (
        "Quand une relance arrive à échéance alors que la fenêtre WhatsApp est ouverte, Setter II peut envoyer un message libre ou un modèle. "
        "Après l'envoi, Sales Cockpit avance selon le résultat de cette relance et respecte le délai minimum entre messages."
    ),
    (
        "follow_up",
        "follow_up_due",
        "Fenêtre WhatsApp fermée, template disponible",
    ): (
        "Quand une relance arrive à échéance alors que la fenêtre WhatsApp est fermée, Setter II doit utiliser un modèle approuvé. "
        "Si un modèle recommandé existe, il est proposé. Après l'envoi, Sales Cockpit avance dans le flux prévu."
    ),
    (
        "follow_up",
        "follow_up_due_template_missing",
        "Fenêtre fermée et aucun template adapté",
    ): (
        "Quand une relance doit partir avec fenêtre fermée mais sans modèle adapté, Sales Cockpit bloque l'action au lieu de laisser l'équipe improviser. "
        "Une demande de modèle doit être créée et liée à cette relance."
    ),
    (
        "template_request",
        "template_submitted",
        "Nouveau template soumis à validation",
    ): (
        "Quand un nouveau modèle est soumis à validation WhatsApp, la relance concernée reste bloquée. "
        "Setter II ne peut reprendre la relance qu'après approbation du modèle."
    ),
    (
        "template_request",
        "template_approved",
        "Relance débloquée",
    ): (
        "Quand le modèle demandé est approuvé, Sales Cockpit débloque la relance et la remet à traiter pour Setter II. "
        "Le modèle approuvé devient alors utilisable pour envoyer le message."
    ),
    (
        "follow_up",
        "outbound_template_sent",
        "Relance envoyée, flux non terminé",
    ): (
        "Quand Setter II envoie une relance qui n'est pas la dernière du flux, Sales Cockpit clôt cette étape et programme la prochaine relance prévue. "
        "Le prospect reste dans le même flux jusqu'à réponse, statut terminal, appel fixé ou fin du flux."
    ),
    (
        "follow_up",
        "outbound_template_sent_last_step",
        "Dernière relance du flux envoyée sans réponse",
    ): (
        "Quand la dernière relance prévue est envoyée et que le prospect ne répond pas, Sales Cockpit termine le suivi. "
        "La conversation est marquée terminée pour suivi terminé sans réponse, et aucune nouvelle action n'est créée."
    ),
    (
        "setting_call",
        "setting_call_completed",
        "À closer",
    ): (
        "Quand Setter I documente un appel setting réussi et décide que le prospect doit passer au closing, Sales Cockpit crée un appel closing pour le closer. "
        "La note de setting et la qualification setter restent visibles pour préparer le closing."
    ),
    (
        "setting_call",
        "setting_call_not_reached",
        "Prospect non joint",
    ): (
        "Quand Setter I ne joint pas le prospect lors d'un appel setting, il documente la tentative. "
        "Sales Cockpit prévoit des rappels d'appel, puis bascule vers une relance Setter II si les rappels ne suffisent pas."
    ),
    (
        "setting_call",
        "setting_call_completed_no_next_step",
        "Prospect joint mais pas prêt ou pas de suite claire",
    ): (
        "Quand l'appel setting a eu lieu mais que le prospect n'est pas prêt ou qu'aucune suite claire n'est fixée, Setter I documente l'échange. "
        "Sales Cockpit prévoit ensuite une relance Setter II 72 heures plus tard."
    ),
    (
        "setting_call",
        "setting_call_terminal",
        "Non pertinent ou Ne plus contacter",
    ): (
        "Quand l'appel setting aboutit à Non pertinent ou Ne plus contacter, Sales Cockpit arrête le suivi. "
        "La conversation est terminée, les relances sont stoppées, et la note d'appel sert de trace."
    ),
    (
        "closing_call",
        "closing_call_completed",
        "Signé",
    ): (
        "Quand le closer documente une signature, Sales Cockpit marque la vente comme gagnée. "
        "La conversation est terminée et aucune relance future n'est créée."
    ),
    (
        "closing_call",
        "closing_call_completed",
        "Va signer",
    ): (
        "Quand le closer estime que le prospect va signer mais que la vente n'est pas encore finalisée, Sales Cockpit lance le flux Va signer. "
        "Setter II reçoit une relance 72 heures plus tard, puis les étapes prévues du flux."
    ),
    (
        "closing_call",
        "closing_call_not_reached",
        "Prospect non joint",
    ): (
        "Quand le closer ne joint pas le prospect, il documente la tentative. "
        "Sales Cockpit prévoit des rappels d'appel closing, puis une relance Setter II si les rappels ne donnent rien."
    ),
    (
        "closing_call",
        "closing_call_completed_undecided",
        "Prospect joint mais pas de décision claire",
    ): (
        "Quand l'appel closing a eu lieu mais que le prospect ne décide pas, le closer documente l'échange. "
        "Sales Cockpit lance ensuite une relance Setter II 72 heures plus tard."
    ),
    (
        "closing_call",
        "closing_call_terminal",
        "Non pertinent",
    ): (
        "Quand le closer qualifie le prospect comme non pertinent, Sales Cockpit termine la conversation et stoppe les relances. "
        "La note de closing sert de justification."
    ),
    (
        "follow_up lead-relative, sauf appel planifié",
        "course_start_approaching",
        "Lead non signé, date de cours connue",
    ): (
        "Quand une date de début de cours approche pour un prospect non signé, Sales Cockpit peut créer une relance liée au cours. "
        "Cette relance annule une relance classique trop proche, mais elle ne remplace jamais un appel setting ou closing déjà planifié."
    ),
    (
        "Toute action",
        "terminal_status_applied",
        "not_relevant, do_not_contact ou signed",
    ): (
        "Quand un statut terminal est appliqué, Sales Cockpit arrête le suivi commercial. "
        "Non pertinent, Ne plus contacter et A signé ferment les relances et empêchent la création de nouvelles actions automatiques."
    ),
    (
        "Toute action",
        "conversation_resolved",
        "Utilisateur clôture avec motif obligatoire",
    ): (
        "Quand un utilisateur clôture une conversation, il doit choisir un motif et ajouter une note si nécessaire. "
        "Sales Cockpit ferme les actions ouvertes et garde l'historique de la clôture."
    ),
    (
        "Aucune",
        "conversation_reopened",
        "Utilisateur rouvre",
    ): (
        "Quand une conversation terminée est réactivée, l'utilisateur doit immédiatement définir une prochaine action. "
        "Sales Cockpit interdit qu'une conversation redevienne active sans savoir qui doit faire quoi et quand."
    ),
    (
        "Toute action",
        "business_hours_closed",
        "Prospect écrit hors disponibilité",
    ): (
        "Quand un prospect écrit hors horaires, Sales Cockpit doit préparer une réponse pour le prochain créneau disponible ou le backup prévu. "
        "Un accusé de réception automatique pourra être ajouté si les textes et règles d'horaires sont validés."
    ),
    (
        "Toute action",
        "assignee_unavailable",
        "Responsable absent",
    ): (
        "Quand le responsable d'une action est absent, Sales Cockpit doit conserver la même action mais l'attribuer au backup prévu, si un backup existe. "
        "Le transfert doit être historisé pour ne pas perdre la responsabilité."
    ),
}


def pilotage_function_text(value):
    if not isinstance(value, str):
        return value
    replacements = {
        "Tanjona": "Setter II",
        "Mihary": "Setter I",
        "Yasmine": "Closer",
        "Setter 1": "Setter I",
    }
    text = value
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def render_pilotage_simulator() -> None:
    st.markdown("### Vue des flux")
    st.caption("Prévisualisation simple. Cette vue ne crée aucune tâche et n'envoie aucun message.")
    default_sessions = {item["course_category"]: item for item in list_course_default_sessions()}
    active_categories = pilotage_active_categories()
    missing = [
        category for category in active_categories
        if category not in default_sessions
    ]
    if missing:
        st.warning(
            "Définis d'abord les sessions de référence pour tous les cours traités : "
            f"{', '.join(missing)}. La vue sera fiable seulement quand tous les cours actifs sont configurés."
        )
        return

    categories = pilotage_categories()
    col_a, col_b = st.columns(2)
    with col_a:
        category = st.selectbox("Catégorie", categories, key="pilotage_sim_category")
    with col_b:
        selected_session = default_sessions.get(category)
        default_date = parse_iso_date_or_today((selected_session or {}).get("default_start_date"))
        start_date = st.date_input(
            "Date de début utilisée",
            value=default_date,
            key="pilotage_sim_start",
            format=DATE_INPUT_FORMAT,
        )

    if selected_session:
        st.info(
            f"Pour {category}, la vue utilise la session de référence : "
            f"{selected_session['default_course_name']} ({selected_session['default_start_date']}). "
            "Lead et Préinscription suivent ensuite les mêmes flux de relance."
        )
    if start_date < utc_now().date():
        st.warning(
            "Cette date de début est déjà passée. Le flux lié au début du cours ne devrait pas être lancé sur cette session ; configure plutôt la prochaine session de référence."
        )

    selected_sequences = [
        "lead_no_reply",
        "setter_no_next_step",
        "post_setting_undecided",
        "setting_call_not_reached",
        "post_closing_undecided",
        "closing_call_not_reached",
        "closer_will_sign",
        "course_start",
    ]
    for code in selected_sequences:
        st.markdown(f"#### {label_sequence_code(code)}")
        rows = build_simulated_timeline(code, start_date)
        st.dataframe(rows, hide_index=True, use_container_width=True)


def render_sequence_timeline(user: dict, sequence_code: str, lead_type: str, category: str) -> None:
    steps = list_sequence_steps(sequence_code)
    mappings = list_sequence_template_mappings()
    approved_templates = [item for item in list_templates() if is_approved_real_twilio_template(item)]
    if not steps:
        st.warning("Aucune étape pour ce flux.")
        return
    sequence = next((item for item in list_sequences() if item["code"] == sequence_code), None)
    if sequence:
        st.markdown(f"#### {sequence['label']}")
        st.caption(f"{sequence['trigger']} Arrêt : {sequence['stop_when']}")
    for step in steps:
        mapping = resolve_mapping_for_step(mappings, step, lead_type, category)
        template = None
        if mapping:
            template = {
                "name": mapping.get("template_name"),
                "status": mapping.get("template_status"),
                "language": mapping.get("template_language"),
                "category": mapping.get("template_category"),
                "body": mapping.get("template_body") or "",
                "twilio_content_sid": mapping.get("twilio_content_sid"),
                "twilio_content_type": mapping.get("twilio_content_type"),
            }

        with st.container(border=True):
            top_cols = st.columns([0.45, 0.9, 1.0, 1.4], vertical_alignment="top")
            top_cols[0].markdown(f"**Étape {step['step_index']}**")
            top_cols[1].markdown(f"**Quand**  \n{sequence_step_timing_label(step)}")
            top_cols[2].markdown(f"**Action**  \n{sequence_step_action_label(step.get('action_type'))}")
            top_cols[3].markdown(f"**Événement**  \n{step['meaning']}")

            if step.get("action_type") == "follow_up":
                if not approved_templates:
                    st.warning("Aucun template Twilio approuvé n'est disponible. Synchronise d'abord les templates dans Modèles.")
                else:
                    exact_mapping = find_mapping_for_category(mappings, step, category, exact_only=True)
                    selected_mapping = exact_mapping or mapping
                    options = [{"id": 0, "name": "Aucun template sélectionné", "body": "", "twilio_content_sid": ""}] + approved_templates
                    selected_id = int((selected_mapping or {}).get("template_id") or 0)
                    selected_index = next(
                        (index for index, item in enumerate(options) if int(item["id"]) == selected_id),
                        0,
                    )
                    with st.form(f"pilotage_inline_mapping_{sequence_code}_{step['step_index']}_{category}"):
                        template_choice = st.selectbox(
                            "Template recommandé",
                            options,
                            index=selected_index,
                            format_func=lambda item: (
                                "Aucun template sélectionné"
                                if int(item["id"]) == 0
                                else f"{item['name']} · {item['language']} · {item.get('twilio_content_sid')}"
                            ),
                            key=f"pilotage_inline_tpl_{sequence_code}_{step['step_index']}_{category}",
                        )
                        note = st.text_input(
                            "Note interne",
                            value=(exact_mapping or {}).get("note") or "",
                            placeholder="Ex. Validé par l'équipe commerciale.",
                            key=f"pilotage_inline_note_{sequence_code}_{step['step_index']}_{category}",
                        )
                        submitted = st.form_submit_button("Enregistrer le template")
                    if submitted:
                        if int(template_choice["id"]) == 0:
                            show_result(False, "Une relance WhatsApp doit avoir un template recommandé.")
                        else:
                            ok, message = upsert_sequence_template_mapping(
                                user["id"],
                                step["sequence_code"],
                                int(step["step_index"]),
                                "all",
                                category,
                                int(template_choice["id"]),
                                note,
                            )
                            show_result(ok, message)
                            if ok:
                                st.rerun()
                if template:
                    status_cols = st.columns([0.5, 0.5, 2.0])
                    status_cols[0].markdown(f"**Statut**  \n{template_status_label(template)}")
                    status_cols[1].markdown(f"**Catégorie**  \n{labelize(template.get('category'))}")
                    mapping_note = (mapping or {}).get("note") if mapping else ""
                    status_cols[2].caption(mapping_note or "Mapping exact, spécifique ou fallback Tous selon disponibilité.")
                    st.markdown("**Message complet**")
                    st.code(template.get("body") or "Corps de message indisponible.", language="text")
                else:
                    st.warning("Template obligatoire non défini pour cette relance WhatsApp.")
            else:
                st.caption("Cette étape ne demande pas de template WhatsApp.")


def find_mapping_for_category(
    mappings: list[dict],
    step: dict,
    category: str,
    exact_only: bool,
) -> dict | None:
    allowed_categories = {category} if exact_only else {category, "all"}
    candidates = [
        item for item in mappings
        if item["sequence_code"] == step["sequence_code"]
        and int(item["sequence_step_index"]) == int(step["step_index"])
        and item["course_category"] in allowed_categories
        and item["lead_type"] in {"all", "lead", "presubscription"}
        and mapping_has_approved_real_template(item)
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            item["course_category"] == category,
            item["lead_type"] == "all",
            item.get("updated_at") or "",
        ),
        reverse=True,
    )[0]


def resolve_mapping_for_step(
    mappings: list[dict],
    step: dict,
    lead_type: str,
    category: str,
) -> dict | None:
    normalized_type = "all" if lead_type == "all" else lead_type
    normalized_category = "all" if category == "Toutes" else category.upper()
    candidates = [
        item for item in mappings
        if item["sequence_code"] == step["sequence_code"]
        and int(item["sequence_step_index"]) == int(step["step_index"])
        and item["lead_type"] in {"all", normalized_type}
        and item["course_category"] in {"all", normalized_category}
        and mapping_has_approved_real_template(item)
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            item["lead_type"] == normalized_type,
            item["course_category"] == normalized_category,
            item.get("updated_at") or "",
        ),
        reverse=True,
    )[0]


def pilotage_categories() -> list[str]:
    active = pilotage_active_categories()
    configured = [item["course_category"] for item in list_course_default_sessions()]
    mapped = [
        item["course_category"]
        for item in list_sequence_template_mappings()
        if item.get("course_category") and item["course_category"] != "all"
    ]
    categories = sorted(set(active + configured + mapped))
    return categories or active or PILOTAGE_SUPPORTED_CATEGORIES


def pilotage_active_categories() -> list[str]:
    categories = [item["course_category"] for item in list_course_categories()]
    return categories or PILOTAGE_SUPPORTED_CATEGORIES.copy()


def pilotage_sequence_sort_key(code: str) -> tuple[int, str]:
    return (PILOTAGE_SEQUENCE_ORDER.get(code, 999), code)


def pilotage_sequence_rank(code: str) -> int:
    ordered = sorted(PILOTAGE_SEQUENCE_ORDER, key=pilotage_sequence_sort_key)
    return ordered.index(code) + 1 if code in ordered else 99


def pilotage_sequence_owner(sequence: dict) -> str:
    return PILOTAGE_SEQUENCE_OWNER_LABELS.get(sequence["code"], sequence.get("owner") or "")


def label_sequence_code(code: str | None) -> str:
    if not code:
        return "Flux inconnu"
    sequence = next((item for item in list_sequences() if item["code"] == code), None)
    return sequence["label"] if sequence else code


def parse_iso_date_or_today(value: str | None):
    if value:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            pass
    return utc_now().date()


def build_simulated_timeline(sequence_code: str, course_start_date) -> list[dict]:
    anchor = utc_now()
    rows = []
    for step in list_sequence_steps(sequence_code):
        due_label = simulate_due_label(step, anchor, course_start_date)
        rows.append(
            {
                "Étape": step["step_index"],
                "Quand": sequence_step_timing_label(step),
                "Date simulée": due_label,
                "Type": sequence_step_action_label(step.get("action_type")),
                "Événement": step["meaning"],
                "Template": "Obligatoire" if step.get("action_type") == "follow_up" else "",
            }
        )
    return rows


def simulate_due_label(step: dict, anchor: datetime, course_start_date) -> str:
    amount = int(step.get("offset_amount") or 0)
    unit = step.get("offset_unit") or "hours"
    delta = timedelta(days=amount) if unit == "days" else timedelta(hours=amount)
    if step.get("offset_direction") == "before":
        return (course_start_date - delta).isoformat()
    due = anchor + delta
    return due.strftime("%Y-%m-%d %H:%M")


def render_admin(user: dict) -> None:
    st.title("Admin")
    if user["role"] != "admin":
        st.warning("Accès lecture seul. Les réglages sont réservés aux admins.")
        return

    tabs = st.tabs([
        "État",
        "Utilisateurs",
        "Règles métier",
        "Workflow",
        "Flux",
        "Templates",
        "Actions admin",
        "Garde-fous",
        "Bugs & logs",
        "Intégrations",
    ])
    with tabs[0]:
        render_admin_status_tab()

    with tabs[1]:
        st.subheader("Utilisateurs")
        users = sorted(list_users(active_only=False), key=lambda item: item["id"])
        user_rows = [
            {
                "ID": item["id"],
                "Nom": display_user_name(item),
                "Email": item["email"],
                "Rôle": display_user_role(item),
                "Actif": bool(item["active"]),
            }
            for item in users
        ]
        st.dataframe(user_rows, hide_index=True, use_container_width=True)
        st.subheader("Accès par rôle")
        st.dataframe(page_access_matrix(), hide_index=True, use_container_width=True)
        st.subheader("Rôles commerciaux")
        st.dataframe(SALES_ACTORS, hide_index=True, use_container_width=True)

    with tabs[2]:
        st.subheader("Qualifications")
        st.dataframe(QUALIFICATION_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Statuts de contact")
        st.dataframe(CONTACT_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Motifs de clôture")
        st.dataframe(RESOLUTION_REASONS, hide_index=True, use_container_width=True)
        st.subheader("Règles opérationnelles")
        st.dataframe(OPERATING_RULES, hide_index=True, use_container_width=True)
        st.subheader("Règles d'attribution")
        st.dataframe(ASSIGNMENT_RULES, hide_index=True, use_container_width=True)
        st.subheader("Horaires et bascules")
        st.dataframe(SCHEDULE_RULES, hide_index=True, use_container_width=True)
        st.subheader("Origines")
        st.dataframe(SOURCE_TYPES, hide_index=True, use_container_width=True)
        st.subheader("Types de leads SchoolDrive")
        st.dataframe(LEAD_TYPES, hide_index=True, use_container_width=True)

    with tabs[3]:
        st.subheader("Types d'actions principales")
        st.dataframe(MAIN_ACTION_TYPES, hide_index=True, use_container_width=True)
        st.subheader("Actions support")
        st.dataframe(SUPPORT_ACTIONS, hide_index=True, use_container_width=True)
        st.subheader("Statuts d'action")
        st.dataframe(ACTION_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Table de transitions")
        st.caption(
            "Cette table décrit le chaînage cible : action actuelle + événement/résultat -> prochaine action."
        )
        st.dataframe(WORKFLOW_TRANSITIONS, hide_index=True, use_container_width=True, height=520)

    with tabs[4]:
        st.subheader("Flux de relance")
        st.dataframe(list_sequences(), hide_index=True, use_container_width=True)
        st.subheader("Étapes du flux")
        sequence_steps = list_sequence_steps()
        st.dataframe(sequence_steps, hide_index=True, use_container_width=True, height=300)

        st.subheader("Templates recommandés par étape")
        mappings = list_sequence_template_mappings()
        if mappings:
            mapping_rows = [
                {
                    "Flux": item["sequence_code"],
                    "Étape": item["sequence_step_index"],
                    "Type": "Tous" if item["lead_type"] == "all" else labelize(item["lead_type"]),
                    "Catégorie": "Toutes" if item["course_category"] == "all" else item["course_category"],
                    "Template": item.get("template_name") or "Template supprimé",
                    "Statut": template_status_label({"status": item.get("template_status")}),
                    "Note": item.get("note") or "",
                }
                for item in mappings
            ]
            st.dataframe(mapping_rows, hide_index=True, use_container_width=True, height=260)
        else:
            st.info("Aucun template réel n'est encore recommandé pour les flux.")

        st.markdown("**Ajouter ou modifier une recommandation**")
        real_templates = [item for item in list_templates() if is_approved_real_twilio_template(item)]
        if not real_templates:
            st.warning("Synchronisez d'abord les vrais templates Twilio approuvés dans la page Modèles.")
        else:
            with st.form("sequence_template_mapping_form"):
                selected_step = st.selectbox(
                    "Étape",
                    sequence_steps,
                    format_func=format_sequence_step,
                )
                lead_type = st.selectbox(
                    "Type SchoolDrive",
                    ["all", "lead", "presubscription"],
                    format_func=lambda value: {
                        "all": "Tous",
                        "lead": "Lead",
                        "presubscription": "Préinscription",
                    }.get(value, labelize(value)),
                )
                course_category = st.text_input(
                    "Catégorie de cours",
                    value="all",
                    help="Ex. APP, FSM, AS. Garder `all` si le même template vaut pour toutes les catégories.",
                )
                template = st.selectbox(
                    "Template Twilio recommandé",
                    real_templates,
                    format_func=lambda item: (
                        f"{item['name']} · {template_status_label(item)} · "
                        f"{item['language']} · {labelize(item['category'])}"
                    ),
                )
                note = st.text_input("Note interne", placeholder="Ex. APP relance 3 avant appel.")
                submitted = st.form_submit_button("Enregistrer le mapping")
            if submitted:
                ok, message = upsert_sequence_template_mapping(
                    user["id"],
                    selected_step["sequence_code"],
                    int(selected_step["step_index"]),
                    lead_type,
                    course_category,
                    int(template["id"]),
                    note,
                )
                show_result(ok, message)
                if ok:
                    st.rerun()

        if mappings:
            with st.expander("Désactiver un mapping", expanded=False):
                with st.form("deactivate_sequence_template_mapping_form"):
                    mapping = st.selectbox(
                        "Mapping",
                        mappings,
                        format_func=lambda item: (
                            f"{item['sequence_code']} #{item['sequence_step_index']} · "
                            f"{item['lead_type']} · {item['course_category']} · "
                            f"{item.get('template_name') or 'template supprimé'}"
                        ),
                    )
                    submitted = st.form_submit_button("Désactiver")
                if submitted:
                    ok, message = deactivate_sequence_template_mapping(user["id"], int(mapping["id"]))
                    show_result(ok, message)
                    if ok:
                        st.rerun()

    with tabs[5]:
        st.subheader("Templates de démo")
        st.dataframe(DEMO_TEMPLATE_CATALOG, hide_index=True, use_container_width=True)
        st.caption("Les vrais templates seront synchronisés depuis Twilio. Les noms ci-dessus servent de mapping provisoire.")
        st.subheader("Statuts de demande de modèle")
        st.dataframe(TEMPLATE_REQUEST_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Demandes de modèles")
        st.caption("Chaque demande crée aussi une action Admin dans l'onglet Actions admin.")
        requests = list_template_requests()
        if requests:
            st.dataframe(requests, hide_index=True, use_container_width=True, height=320)
            templates_for_linking = template_link_options(list_templates())
            with st.form("update_template_request_status"):
                request = st.selectbox(
                    "Demande",
                    requests,
                    format_func=lambda item: f"#{item['id']} · {lead_display_name(item)} · {labelize(item['status'])}",
                )
                linked_template = st.selectbox(
                    "Template Twilio lié",
                    templates_for_linking,
                    index=template_link_index(templates_for_linking, request.get("template_id")),
                    format_func=template_link_label,
                )
                status = st.selectbox(
                    "Nouveau statut",
                    [item["value"] for item in TEMPLATE_REQUEST_STATUSES],
                    index=safe_index([item["value"] for item in TEMPLATE_REQUEST_STATUSES], request["status"]),
                    format_func=labelize,
                )
                submitted = st.form_submit_button("Mettre à jour la demande")
            if submitted:
                selected_template_id = int(linked_template["id"]) if linked_template.get("id") else None
                ok, message = update_template_request_status(
                    request["id"],
                    user["id"],
                    status,
                    selected_template_id,
                )
                show_result(ok, message)
                if ok:
                    st.rerun()
        else:
            st.info("Aucune demande de modèle.")

    with tabs[6]:
        render_admin_actions_tab(user)

    with tabs[7]:
        render_admin_safeguards_tab(user)

    with tabs[8]:
        st.subheader("Signalements Bug")
        st.caption("Chaque signalement conserve le contexte et crée aussi une action Admin terminable.")
        bug_reports = list_bug_reports()
        if bug_reports:
            st.dataframe(bug_reports, hide_index=True, use_container_width=True, height=320)
        else:
            st.info("Aucun signalement pour le moment.")
        st.subheader("Journal utilisateur")
        st.caption("Derniers événements métier, connexions et signalements. Les événements lead détaillés restent dans `lead_events`.")
        st.dataframe(list_user_activity_log(200), hide_index=True, use_container_width=True, height=420)

    with tabs[9]:
        st.subheader("Intégrations")
        st.markdown(
            """
            - Twilio : mode selon environnement, synchronisation Content API disponible, aucun envoi réel sans configuration explicite.
            - SchoolDrive : webhook snapshot actif ; enrichissement read-only complémentaire gardé pour V2.
            - Notion : connecteur read-only en V1, écriture future possible pour qualifications.
            - Front.io : lecture seule en zone tampon pour historique WhatsApp.
            """
        )
        st.subheader("Front.io historique")
        filter_cols = st.columns([0.25, 0.25, 0.25, 0.25], vertical_alignment="bottom")
        with filter_cols[0]:
            front_match_filter = st.selectbox(
                "Matching",
                ["all", "matched", "unmatched", "ambiguous"],
                format_func=labelize,
                key="front_match_filter",
            )
        with filter_cols[1]:
            front_migration_filter = st.selectbox(
                "Migration",
                ["all", "active", "resolved", "manual_review"],
                format_func=labelize,
                key="front_migration_filter",
            )
        with filter_cols[2]:
            front_action_filter = st.selectbox(
                "Action recommandée",
                ["all", "reply", "follow_up", "none"],
                format_func=labelize,
                key="front_action_filter",
            )
        with filter_cols[3]:
            front_limit = st.number_input(
                "Limite",
                min_value=10,
                max_value=500,
                value=100,
                step=10,
                key="front_limit",
            )
        front_records = list_front_import_records(
            int(front_limit),
            match_status=front_match_filter,
            migration_status=front_migration_filter,
            migration_action_type=front_action_filter,
        )
        if front_records:
            front_review_rows = [
                {
                    "Front ID": item["front_conversation_id"],
                    "Téléphone": item.get("phone_e164") or "",
                    "Matching": labelize(item.get("match_status")),
                    "Migration": labelize(item.get("migration_status")),
                    "Action": labelize(item.get("migration_action_type") or "none"),
                    "Messages": item.get("front_message_count") or 0,
                    "Attachés": item.get("attached_message_count") or 0,
                    "Prospect": lead_display_name(item) if item.get("lead_id") else "",
                    "SD ID": item.get("schooldrive_lead_id") or "",
                    "Statut Front": item.get("front_status") or "",
                    "Sujet": compact_text(item.get("subject") or "", 90),
                    "Raison": compact_text(item.get("migration_reason") or item.get("match_reason") or "", 120),
                }
                for item in front_records
            ]
            st.dataframe(front_review_rows, hide_index=True, use_container_width=True, height=360)
            st.caption(
                "Ces lignes restent en zone tampon. Elles ne créent aucune action et n'attachent aucun message au fil tant que l'import historique n'est pas explicitement lancé avec attachement."
            )
        else:
            st.info("Aucune conversation Front importée dans la zone tampon.")

        st.subheader("Plan de bascule Front")
        front_plan = build_front_cutover_plan(int(front_limit))
        render_count_table("Décisions", front_plan["counts"])
        if front_plan["rows"]:
            plan_rows = [
                {
                    "Décision": labelize(item["decision"]),
                    "Action": labelize(item.get("recommended_action") or "none"),
                    "Responsable": item.get("recommended_owner") or "",
                    "Front ID": item.get("front_conversation_id") or "",
                    "Téléphone": item.get("phone_e164") or "",
                    "Prospect": lead_display_name(item) if item.get("lead_id") else "",
                    "SD ID": item.get("schooldrive_lead_id") or "",
                    "Messages": item.get("front_message_count") or 0,
                    "Raison": compact_text(item.get("reason") or "", 120),
                }
                for item in front_plan["rows"]
            ]
            st.dataframe(plan_rows, hide_index=True, use_container_width=True, height=260)
        else:
            st.info("Aucune ligne à planifier.")


def render_admin_actions_tab(user: dict) -> None:
    st.subheader("Actions admin")
    st.caption("File de travail pour bugs, demandes de modèles et revues techniques. Une action terminée reste historisée.")
    open_actions = list_admin_actions("open")
    if open_actions:
        rows = [
            {
                "ID": item["id"],
                "Type": labelize(item["type"]),
                "Titre": item["title"],
                "Prospect": lead_display_name(item),
                "Statut": labelize(item["status"]),
                "Assignée à": item.get("assigned_to_name") or "Admin",
                "Échéance": format_due(item.get("due_at")),
                "Créée": format_dt(item.get("created_at")),
            }
            for item in open_actions
        ]
        st.dataframe(rows, hide_index=True, use_container_width=True, height=260)
        with st.form("complete_admin_action_form"):
            action = st.selectbox(
                "Action à terminer",
                open_actions,
                format_func=lambda item: f"#{item['id']} · {item['title']}",
            )
            outcome = st.text_input("Résolution", value="Traité")
            submitted = st.form_submit_button("Marquer terminée", disabled=not outcome.strip())
        if submitted:
            ok, message = complete_admin_action(action["id"], user["id"], outcome.strip())
            show_result(ok, message)
            if ok:
                st.rerun()
    else:
        st.info("Aucune action admin ouverte.")

    with st.expander("Historique des actions admin", expanded=False):
        history = list_admin_actions("all")
        if history:
            st.dataframe(history, hide_index=True, use_container_width=True, height=320)
        else:
            st.caption("Aucune action admin historisée.")


def render_admin_safeguards_tab(user: dict) -> None:
    st.subheader("Garde-fous WhatsApp")
    st.caption("Ces valeurs bloquent l'envoi avant Twilio. Elles protègent contre un emballement de relances ou une erreur de configuration.")
    safeguards = get_outbound_safeguards()
    with st.form("outbound_safeguards_form"):
        global_block = st.checkbox(
            "Bloquer tous les envois WhatsApp depuis Sales Cockpit",
            value=bool(safeguards["outbound_global_block"]),
        )
        cols = st.columns(4)
        with cols[0]:
            per_lead_day = st.number_input(
                "Max / prospect / jour",
                min_value=1,
                max_value=50,
                value=int(safeguards["outbound_max_per_lead_day"]),
                step=1,
            )
        with cols[1]:
            per_lead_week = st.number_input(
                "Max / prospect / semaine",
                min_value=1,
                max_value=100,
                value=int(safeguards["outbound_max_per_lead_week"]),
                step=1,
            )
        with cols[2]:
            global_day = st.number_input(
                "Max global / jour",
                min_value=1,
                max_value=5000,
                value=int(safeguards["outbound_max_global_day"]),
                step=10,
            )
        with cols[3]:
            min_hours = st.number_input(
                "Délai min relances (h)",
                min_value=1,
                max_value=168,
                value=int(safeguards["outbound_min_followup_hours"]),
                step=1,
            )
        submitted = st.form_submit_button("Enregistrer les garde-fous")
    if submitted:
        ok, message = update_outbound_safeguards(
            user["id"],
            {
                "outbound_global_block": global_block,
                "outbound_max_per_lead_day": per_lead_day,
                "outbound_max_per_lead_week": per_lead_week,
                "outbound_max_global_day": global_day,
                "outbound_min_followup_hours": min_hours,
            },
        )
        show_result(ok, message)
        if ok:
            st.rerun()


def render_admin_status_tab() -> None:
    readiness = get_integration_readiness()
    st.subheader("État des intégrations")
    st.caption(
        "Vue courte pour savoir si la bascule peut avancer. Les secrets ne sont jamais affichés ici."
    )

    status_cols = st.columns(len(readiness["checks"]))
    for col, check in zip(status_cols, readiness["checks"], strict=False):
        with col:
            render_readiness_tile(check)

    workflow = readiness["workflow"]
    blockers = []
    if workflow["open_conversations_without_action"]:
        blockers.append(
            {
                "Type": "Workflow",
                "Statut": "Bloquant",
                "Détail": f"{workflow['open_conversations_without_action']} conversation(s) active(s) sans prochaine action.",
            }
        )
    if workflow.get("resolved_conversations_with_action_count"):
        blockers.append(
            {
                "Type": "Workflow",
                "Statut": "Bloquant",
                "Détail": f"{workflow['resolved_conversations_with_action_count']} conversation(s) terminée(s) avec action active.",
            }
        )
    if workflow.get("conversations_with_multiple_main_actions"):
        blockers.append(
            {
                "Type": "Workflow",
                "Statut": "Bloquant",
                "Détail": f"{workflow['conversations_with_multiple_main_actions']} conversation(s) avec actions principales concurrentes.",
            }
        )
    if workflow["blocked_action_count"]:
        blockers.append(
            {
                "Type": "Actions",
                "Statut": "À surveiller",
                "Détail": f"{workflow['blocked_action_count']} action(s) bloquée(s).",
            }
        )
    if workflow["pending_template_request_count"]:
        blockers.append(
            {
                "Type": "Modèles",
                "Statut": "À traiter",
                "Détail": f"{workflow['pending_template_request_count']} demande(s) de modèle ouvertes.",
            }
        )
    if workflow["open_bug_count"]:
        blockers.append(
            {
                "Type": "Bugs",
                "Statut": "À surveiller",
                "Détail": f"{workflow['open_bug_count']} signalement(s) ouvert(s).",
            }
        )

    st.subheader("Blocages")
    if blockers:
        st.dataframe(blockers, hide_index=True, use_container_width=True)
    else:
        st.success("Aucun blocage critique détecté dans les données actuelles.")

    sd_col, front_col = st.columns(2)
    with sd_col:
        st.subheader("SchoolDrive")
        sd = readiness["schooldrive"]
        st.markdown(
            f"""
            <div class="sc-status-panel">
              <strong>{sd['lead_count']}</strong>
              <span>lead(s) ou préinscription(s) reçus depuis SchoolDrive</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_count_table("Événements webhook", sd["status_counts"])
        if sd["latest_events"]:
            st.dataframe(sd["latest_events"], hide_index=True, use_container_width=True, height=230)
        else:
            st.info("Aucun webhook SchoolDrive reçu.")

    with front_col:
        st.subheader("Front")
        front = readiness["front"]
        st.markdown(
            f"""
            <div class="sc-status-panel">
              <strong>{front['message_count']}</strong>
              <span>message(s) Front en zone tampon, {front['attached_message_count']} attaché(s) au fil</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_count_table("Matching", front["match_counts"])
        render_count_table("Migration", front["migration_counts"])
        if front["latest_records"]:
            st.dataframe(front["latest_records"], hide_index=True, use_container_width=True, height=230)
        else:
            st.info("Aucune conversation Front importée.")

    twilio_col, ops_col = st.columns(2)
    with twilio_col:
        st.subheader("Twilio")
        twilio = readiness["twilio"]
        sender = twilio["sender"] or "Non configuré"
        st.markdown(
            f"""
            <div class="sc-status-panel">
              <strong>{escape_html(twilio['mode'])}</strong>
              <span>Sender : {escape_html(sender)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_count_rows("Statuts messages", twilio["status_counts"], "status")
        if twilio["latest_messages"]:
            st.dataframe(twilio["latest_messages"], hide_index=True, use_container_width=True, height=230)
        else:
            st.info("Aucun message Twilio enregistré.")

    with ops_col:
        st.subheader("Opérations")
        backup = readiness["backup"]
        backup_label = "Aucun backup trouvé"
        if backup.get("exists"):
            backup_label = f"{format_bytes(backup['size_bytes'])} · {backup['updated_at']}"
        st.markdown(
            f"""
            <div class="sc-status-panel">
              <strong>{readiness['environment']}</strong>
              <span>Dernier backup : {escape_html(backup_label)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(
            [
                {"Indicateur": "Actions ouvertes", "Valeur": workflow["open_action_count"]},
                {"Indicateur": "Actions bloquées", "Valeur": workflow["blocked_action_count"]},
                {"Indicateur": "Demandes de modèles ouvertes", "Valeur": workflow["pending_template_request_count"]},
                {"Indicateur": "Bugs ouverts", "Valeur": workflow["open_bug_count"]},
                {
                    "Indicateur": "En attente du premier WhatsApp SchoolDrive",
                    "Valeur": workflow["schooldrive_waiting_first_autoresponder_count"],
                },
                {
                    "Indicateur": "Conversations actives sans prochaine action",
                    "Valeur": workflow["open_conversations_without_action"],
                },
                {
                    "Indicateur": "Conversations terminées avec action active",
                    "Valeur": workflow.get("resolved_conversations_with_action_count", 0),
                },
                {
                    "Indicateur": "Conversations avec actions concurrentes",
                    "Valeur": workflow.get("conversations_with_multiple_main_actions", 0),
                },
            ],
            hide_index=True,
            use_container_width=True,
        )


def render_readiness_tile(check: dict[str, str]) -> None:
    state = check["state"]
    labels = {
        "ready": "Prêt",
        "info": "Info",
        "warning": "À surveiller",
        "danger": "Bloquant",
    }
    st.markdown(
        f"""
        <div class="sc-readiness sc-readiness-{escape_html(state)}">
          <div class="sc-readiness-label">{escape_html(check['name'])}</div>
          <div class="sc-readiness-state">{escape_html(labels.get(state, state))}</div>
          <div class="sc-readiness-detail">{escape_html(check['detail'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_count_table(title: str, counts: dict[str, int]) -> None:
    rows = [{"Statut": labelize(key), "Nombre": value} for key, value in counts.items()]
    render_count_rows(title, rows, "Statut")


def render_count_rows(title: str, rows: list[dict] | dict, label_key: str) -> None:
    st.caption(title)
    if isinstance(rows, dict):
        rows = [{label_key: labelize(key), "count": value} for key, value in rows.items()]
    normalized = []
    for row in rows:
        normalized.append(
            {
                "Statut": labelize(row.get(label_key) or row.get("status") or row.get("key") or "unknown"),
                "Nombre": row.get("count") or row.get("Nombre") or 0,
            }
        )
    if normalized:
        st.dataframe(normalized, hide_index=True, use_container_width=True, height=min(180, 42 + 36 * len(normalized)))
    else:
        st.info("Aucune donnée.")


def format_bytes(size_bytes: int | None) -> str:
    size = float(size_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def default_variable_value(conv: dict, key: str) -> str:
    mapping = {
        "first_name": conv.get("first_name"),
        "last_name": conv.get("last_name"),
        "course_title": conv.get("course_title"),
        "phone": conv.get("phone_e164"),
    }
    return mapping.get(key) or ""


def render_template_body(body: str, variables: dict[str, str]) -> str:
    rendered = body
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value or f"{{{{{key}}}}}")
    return rendered


def get_schooldrive_url(conv: dict) -> str | None:
    if conv.get("schooldrive_url"):
        return whitelist_schooldrive_url(conv.get("schooldrive_url"))
    return whitelist_schooldrive_url(SchoolDriveConnector().get_lead_url(conv.get("schooldrive_lead_id")))


def whitelist_schooldrive_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "schooldrive.essr.ch":
        return None
    return url


def show_result(ok: bool, message: str) -> None:
    if ok:
        st.success(message)
    else:
        st.error(message)


def clear_widget_keys(*keys: str) -> None:
    pending = list(st.session_state.get(WIDGET_CLEAR_QUEUE_KEY, []))
    pending.extend(key for key in keys if key)
    st.session_state[WIDGET_CLEAR_QUEUE_KEY] = list(dict.fromkeys(pending))


def apply_pending_widget_clears() -> None:
    for key in st.session_state.pop(WIDGET_CLEAR_QUEUE_KEY, []):
        st.session_state.pop(key, None)


def resettable_widget_key(base_key: str) -> str:
    return f"{base_key}_{int(st.session_state.get(f'{base_key}_reset', 0))}"


def reset_widget_key(base_key: str) -> None:
    st.session_state[f"{base_key}_reset"] = int(st.session_state.get(f"{base_key}_reset", 0)) + 1


def labelize(value: str | None) -> str:
    if not value:
        return "Non défini"
    return DISPLAY_LABELS.get(value, value.replace("_", " ").capitalize())


def queue_label(value: str | None) -> str:
    labels = {
        "todo": "À traiter",
        "waiting": "En suspens",
        "resolved": "Terminées",
        "due": "À traiter",
        "future": "En suspens",
        "completed": "Terminées",
        "all": "Toutes",
    }
    return labels.get(value or "", labelize(value))


def lead_display_name(item: dict) -> str:
    first_name = str(item.get("first_name") or "").strip()
    last_name = str(item.get("last_name") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if not full_name or full_name.lower() == "whatsapp unknown":
        return "Inconnu(e)"
    return full_name


def action_display_title(value: str) -> str:
    return " ".join(value.replace("WhatsApp Unknown", "Inconnu(e)").split())


def safe_index(values: list[str], value: str | None) -> int:
    try:
        return values.index(value or "")
    except ValueError:
        return 0


def format_dt(value: str | None) -> str:
    if not value:
        return "Non disponible"
    parsed = parse_dt(value)
    if not parsed:
        return "Non disponible"
    return parsed.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y %H:%M")


def format_window_boundary(value: str | None) -> str:
    if not value:
        return "Non disponible"
    parsed = parse_dt(value)
    if not parsed:
        return "Non disponible"
    return parsed.astimezone(DISPLAY_TZ).strftime("%d.%m.%Y à %H:%M")


def format_due(value: str | None) -> str:
    if not value:
        return "Aucune échéance"
    parsed = parse_dt(value)
    if not parsed:
        return "Échéance invalide"
    local = parsed.astimezone(DISPLAY_TZ)
    today = local_today()
    if local.date() == today:
        return f"Aujourd’hui {local.strftime('%H:%M')}"
    return local.strftime("%d.%m.%Y %H:%M")


def format_action_datetime(value: str | None) -> str:
    if not value:
        return "Aucune échéance"
    parsed = parse_dt(value)
    if not parsed:
        return "Échéance invalide"
    return parsed.astimezone(DISPLAY_TZ).strftime("%d.%m %H:%M")


def next_action_display_title(action: dict) -> str:
    action_type = action.get("type")
    if action_type in {"reply", "follow_up", "setting_call", "closing_call"}:
        return labelize(action_type)
    return compact_text(action.get("title") or labelize(action_type), 54)


def client_waiting_since(item: dict) -> datetime | None:
    if item.get("conversation_status") == "resolved":
        return None
    if item.get("last_message_direction") == "inbound":
        return parse_dt(item.get("last_message_at") or item.get("last_inbound_at"))

    last_inbound = parse_dt(item.get("last_inbound_at"))
    if not last_inbound:
        return None
    last_outbound = parse_dt(item.get("last_outbound_at"))
    if last_outbound and last_outbound >= last_inbound:
        return None
    return last_inbound


def client_waiting_state(item: dict) -> str | None:
    waiting_since = client_waiting_since(item)
    if not waiting_since:
        return None
    elapsed = max(0, int((utc_now() - waiting_since).total_seconds() // 60))
    if elapsed < 1:
        return "Client attend maintenant"
    if elapsed < 60:
        return f"Client attend depuis {elapsed} min"
    hours = elapsed // 60
    minutes = elapsed % 60
    if hours < 24:
        if minutes:
            return f"Client attend depuis {hours} h {minutes:02d}"
        return f"Client attend depuis {hours} h"
    days = hours // 24
    return f"Client attend depuis {days} j"


def attention_sort_key(item: dict) -> tuple:
    waiting_since = client_waiting_since(item)
    if waiting_since:
        return (0, -waiting_since.timestamp())

    due_at = parse_dt(item.get("due_at") or item.get("next_action_due_at"))
    action_type = item.get("type") or item.get("next_action_type") or ""
    action_rank = {
        "reply": 0,
        "contact_review": 1,
        "closing_call": 2,
        "setting_call": 3,
        "follow_up": 4,
    }.get(action_type, 4)
    future_rank = 1 if due_at and due_at > utc_now() else 0
    due_rank = due_at.timestamp() if due_at else 9_999_999_999
    name_rank = (
        item.get("last_name") or "",
        item.get("first_name") or "",
    )
    return (1, future_rank, action_rank, due_rank, *name_rank)


def sort_conversations_for_attention(conversations: list[dict]) -> list[dict]:
    return sorted(conversations, key=attention_sort_key)


def detail_work_queue(conv: dict, action: dict | None) -> str:
    if conv["status"] == "resolved":
        return "resolved"
    if not action:
        return "waiting"
    due_at = parse_dt(action.get("due_at"))
    if due_at and due_at > datetime.now(timezone.utc):
        return "waiting"
    return "todo"


def default_assignee_id(conv: dict, action: dict | None, user: dict) -> int:
    if action and action.get("assigned_to_user_id"):
        return int(action["assigned_to_user_id"])
    if conv.get("sales_stage") in {"closing", "appointment_booked"} and conv.get("closer_user_id"):
        return int(conv["closer_user_id"])
    if conv.get("setter_user_id"):
        return int(conv["setter_user_id"])
    return int(user["id"])


def safe_user_index(users: list[dict], user_id: int | None) -> int:
    for index, item in enumerate(users):
        if item["id"] == user_id:
            return index
    return 0


def refresh_current_user(user: dict) -> dict:
    for item in list_users(active_only=False):
        if item["id"] == user["id"]:
            refreshed = {**user, **item}
            return refreshed
    return user


def normalize_user_display_name(email: str | None, full_name: str | None) -> str:
    if (email or "").lower() == "setter2@essr.ch":
        return "Tanjona"
    if (full_name or "").strip().lower() == "setter 2":
        return "Tanjona"
    return (full_name or "").strip() or "Non assigné"


def display_user_name(user: dict) -> str:
    return normalize_user_display_name(user.get("email"), user.get("full_name"))


def display_assignee_name(item: dict, name_key: str = "assigned_to_name", email_key: str = "assigned_to_email") -> str:
    return normalize_user_display_name(item.get(email_key), item.get(name_key))


def format_user(user: dict) -> str:
    return f"{display_user_name(user)} · {display_user_role(user)}"


def format_assignee_filter(user: dict, current_user_id: int | None = None) -> str:
    if user["id"] == "all":
        return "Tous"
    label = f"{display_user_name(user)} · {display_user_role(user)}"
    if current_user_id is not None and user["id"] == current_user_id:
        return f"{label} (moi)"
    return label


def display_user_role(user: dict) -> str:
    role = user.get("role")
    email = (user.get("email") or "").lower()
    if role == "admin":
        return "Admin"
    if role == "closer":
        return "Closer"
    if role == "setter":
        if email == "setter2@essr.ch":
            return "Setter II"
        return "Setter I"
    return labelize(role)


def sort_work_items(tasks: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "attention":
        return sorted(tasks, key=attention_sort_key)
    if sort_by == "lead_name":
        return sorted(
            tasks,
            key=lambda task: (
                task.get("last_name") or "",
                task.get("first_name") or "",
                task.get("due_at") or "",
            ),
        )
    if sort_by == "due_at":
        return sorted(tasks, key=lambda task: task.get("due_at") or "")
    return sorted(
        tasks,
        key=lambda task: (
            task.get("assigned_to_name") or "zzzz",
            task.get("last_name") or "",
            task.get("first_name") or "",
            task.get("due_at") or "",
        ),
    )


def quick_due_at(days: int) -> str:
    return local_due_at(local_today() + timedelta(days=days), time(9, 0))


def local_due_at(selected_date, selected_time: time) -> str:
    local_dt = datetime.combine(selected_date, selected_time, tzinfo=DISPLAY_TZ)
    return local_dt.astimezone(timezone.utc).isoformat()


def local_today():
    return utc_now().astimezone(DISPLAY_TZ).date()


def compact_text(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


if __name__ == "__main__":
    main()
