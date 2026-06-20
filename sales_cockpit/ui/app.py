from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import sys

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
    complete_action_with_workflow,
    create_and_submit_twilio_template,
    create_bug_report,
    create_template_request,
    create_template,
    deactivate_course_default_session,
    deactivate_sequence_template_mapping,
    get_conversation,
    get_integration_readiness,
    get_next_action_for_lead,
    build_front_cutover_plan,
    get_recommended_template_for_action,
    get_template,
    list_actions_for_lead,
    list_conversations,
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
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    sync_twilio_templates,
    upsert_course_default_session,
    upsert_sequence_template_mapping,
    update_template_request_status,
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
WORK_SORTS = ["assignee_name", "lead_name", "due_at"]
ACTION_OUTCOMES = {
    "reply": ["reply_no_appointment", "setting_booked", "closing_booked", "not_relevant", "do_not_contact"],
    "follow_up": ["follow_up_sent", "template_missing", "sequence_completed_no_reply"],
    "setting_call": ["to_closing", "not_reached", "not_ready", "not_relevant", "do_not_contact"],
    "closing_call": ["signed", "will_sign", "not_reached", "undecided", "not_relevant"],
    "contact_review": ["maintain_do_not_contact", "lift_do_not_contact"],
    "other": ["done"],
}
REPLY_SEND_OUTCOMES = ["reply_no_appointment", "setting_booked", "closing_booked", "not_relevant", "do_not_contact"]
REPLY_SEND_OUTCOME_LABELS = {
    "reply_no_appointment": "Pas de RDV : relance Tanjona à +72h",
    "setting_booked": "RDV setting fixé : créer un appel",
    "closing_booked": "RDV closing fixé : créer un appel",
    "not_relevant": "Hors cible : clore la conversation",
    "do_not_contact": "Ne plus contacter : clore et bloquer",
}
CALL_ACTION_TYPES = {"setting_call", "closing_call"}
PILOTAGE_DEFAULT_CATEGORIES = ["APP", "AS", "FSM"]
PILOTAGE_CONFLICT_RULES = [
    {
        "Situation": "Le prospect répond",
        "Règle": "La réponse entrante interrompt les relances futures et crée une action Répondre au message pour Mihary.",
    },
    {
        "Situation": "Relance lead et relance cours au même moment",
        "Règle": "La relance liée au début du cours gagne. La relance liée au cycle du lead est annulée.",
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
    "neutral": "Neutre",
    "eligible": "Éligible",
    "not_relevant": "Non pertinent",
    "will_sign": "Va signer",
    "signed": "A signé",
    "contact_allowed": "Contact autorisé",
    "do_not_contact": "Ne plus contacter",
    "duplicate": "Doublon",
    "handled_elsewhere": "Traité ailleurs",
    "sequence_completed_no_reply": "Séquence terminée sans réponse",
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
    "closing_call": "Appel closing",
    "setting_call": "Appel setting",
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
    with st.sidebar:
        st.subheader("Sales Cockpit")
        st.caption(f"{display_user_name(user)} · {display_user_role(user)}")
        nav = st.radio(
            "Navigation",
            nav_options,
            label_visibility="collapsed",
            key="main_navigation",
        )
        render_bug_report_button(user, nav)
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

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


def render_bug_report_button(user: dict, page: str) -> None:
    if st.button("Bug", use_container_width=True):
        render_bug_report_dialog(user, page)


@st.dialog("Signaler un bug", width="large")
def render_bug_report_dialog(user: dict, page: str) -> None:
    st.caption("Décrivez ce qui semble incorrect ou améliorable. Le signalement sera relié à la page courante et, si possible, à la conversation ou à l'action sélectionnée.")
    with st.form("bug_report_form"):
        title = st.text_input("Titre court", placeholder="Ex. mauvaise prochaine action")
        description = st.text_area(
            "Ce qui semble incorrect ou améliorable",
            height=140,
        )
        actual = st.text_area("Ce que vous voyez", height=90)
        expected = st.text_area("Ce que vous attendiez", height=90)
        severity = st.selectbox(
            "Priorité",
            ["normal", "high", "urgent"],
            index=0,
            format_func=labelize,
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
            reopen_date = st.date_input("Date", value=datetime.now().date(), key=f"reopen_date_{conv['id']}")
            reopen_time = st.time_input("Heure", value=time(9, 0), key=f"reopen_time_{conv['id']}")
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
                st.rerun()


def identity_needs_review(item: dict) -> bool:
    return item.get("identity_status") in {"needs_identification", "ambiguous_identity"}


def identity_badge_html(item: dict) -> str:
    if not identity_needs_review(item):
        return ""
    return '<span class="sc-identity-badge">À identifier</span>'


def state_chip_html(label: str, value: str) -> str:
    return f'<span><strong>{escape_html(label)}</strong> {escape_html(value)}</span>'


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
        created = format_dt(message.get("created_at"))
        template = f" · modèle: {message['template_name']}" if message.get("template_name") else ""
        delivery = render_delivery_status(message)
        st.markdown(
            f"""
            <div class="sc-message-row {row_css}">
              <div class="sc-message {css}">
                <div class="sc-message-meta">{sender} · {created}{template}{delivery}</div>
                <div>{escape_html(message['body'])}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
            datetime.now().date(),
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
    outcome = st.selectbox(
        "Suite à créer après l'envoi",
        REPLY_SEND_OUTCOMES,
        format_func=lambda value: REPLY_SEND_OUTCOME_LABELS.get(value, labelize(value)),
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
            value=datetime.now().date(),
            key=f"{key_prefix}_reply_date",
        )
        appointment_time = st.time_input(
            "Heure",
            value=time(9, 0),
            key=f"{key_prefix}_reply_time",
        )
        call_label = "setting" if outcome == "setting_booked" else "closing"
        st.caption(f"Après l'envoi, un appel {call_label} sera créé le {appointment_date.strftime('%d.%m.%Y')} à {appointment_time.strftime('%H:%M')}.")
    elif outcome in {"not_relevant", "do_not_contact"}:
        st.warning("Cette réponse résoudra la conversation et annulera les relances futures.")
    else:
        st.caption("Après l'envoi, une relance Tanjona sera planifiée à +72h si le prospect ne répond pas.")


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
        with st.form(f"freeform_{conv['id']}"):
            body = st.text_area("Message libre", height=110)
            st.file_uploader("Pièces jointes, mock UI", accept_multiple_files=True)
            submitted = st.form_submit_button("Envoyer le message libre")
        if submitted:
            if not body.strip():
                st.error("Écrivez un message avant l'envoi.")
                return
            ok, message = send_freeform_message(
                conv["id"],
                user["id"],
                body.strip(),
                action_outcome=action_outcome,
                next_due_at=next_due_at,
                assigned_to_user_id=assigned_to_user_id,
                note=action_note,
            )
            show_result(ok, message)
            if ok:
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
    with st.form(f"template_request_{conv['id']}_{linked_task_id or 'general'}"):
        reason = st.text_input(
            "Modèle manquant",
            placeholder="Ex. relance financement pour APP",
        )
        context = st.text_area(
            "Contexte pour le modèle",
            value=conv.get("last_message_body") or "",
            height=90,
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
            <span class="sc-badge sc-badge-neutral">{escape_html(assignee)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def action_consequence(action_type: str, outcome: str) -> str:
    consequences = {
        ("setting_call", "to_closing"): "Le système crée un appel closing pour le closer et passe le parcours en Closing.",
        ("setting_call", "not_reached"): "Le système crée un rappel d'appel, puis une relance Tanjona si les rappels sont épuisés.",
        ("setting_call", "not_ready"): "Le système crée une relance Tanjona à +72h.",
        ("setting_call", "not_relevant"): "Résout la conversation et annule les relances futures.",
        ("setting_call", "do_not_contact"): "Passe le contact en Ne plus contacter, résout la conversation et bloque les relances.",
        ("closing_call", "signed"): "Marque la vente comme signée, résout la conversation et annule les relances.",
        ("closing_call", "will_sign"): "Le système crée une relance Tanjona à +72h, puis suit la séquence Va signer.",
        ("closing_call", "not_reached"): "Le système crée un rappel d'appel, puis une relance Tanjona si les rappels sont épuisés.",
        ("closing_call", "undecided"): "Le système crée une relance Tanjona à +72h.",
        ("closing_call", "not_relevant"): "Résout la conversation et annule les relances futures.",
        ("contact_review", "maintain_do_not_contact"): "Maintient le blocage Ne plus contacter et résout la conversation.",
        ("contact_review", "lift_do_not_contact"): "Le système lève le blocage et crée une action Répondre pour Setter 1.",
    }
    return consequences.get((action_type, outcome), "Le système appliquera la suite prévue par la règle métier.")


def render_current_action_card(action: dict) -> None:
    assignee = display_assignee_name(action)
    st.markdown(
        f"""
        <div class="sc-panel">
          <div class="sc-action-title">{escape_html(action['title'])}</div>
          <div class="sc-row-meta">
            {escape_html(labelize(action['type']))} · {escape_html(assignee)} ·
            {escape_html(format_due(action.get('due_at')))} · {escape_html(labelize(action.get('status')))} ·
            {escape_html(labelize(action.get('urgency')))}
          </div>
          {f"<div class='sc-action-description'>{escape_html(action['description'])}</div>" if action.get('description') else ""}
        </div>
        """,
        unsafe_allow_html=True,
    )


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
    outcomes = ACTION_OUTCOMES[action["type"]]
    with st.form(f"call_action_form_{action['id']}"):
        outcome = st.selectbox(
            "Résultat de l'appel",
            outcomes,
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
            next_date = st.date_input("Date du rendez-vous", value=datetime.now().date(), key=f"call_date_{action['id']}")
            next_time = st.time_input("Heure", value=time(9, 0), key=f"call_time_{action['id']}")
            next_due_at = local_due_at(next_date, next_time)
        submitted = st.form_submit_button("Enregistrer le résultat")
    if submitted:
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
            st.rerun()


def render_contact_review_action(user: dict, action: dict) -> None:
    st.warning("Ce prospect est marqué Ne plus contacter, mais il a réécrit. Lisez le message avant de décider.")
    note = st.text_area("Note de revue", height=80, key=f"contact_review_note_{action['id']}")
    cols = st.columns(2)
    if cols[0].button("Maintenir Ne plus contacter", use_container_width=True, key=f"maintain_dnc_{action['id']}"):
        ok, message = complete_action_with_workflow(
            action["id"],
            user["id"],
            "maintain_do_not_contact",
            note=note,
        )
        show_result(ok, message)
        if ok:
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
            st.rerun()


def render_manual_completion_advanced(user: dict, action: dict | None) -> None:
    if not action or action.get("type") not in {"reply", "follow_up"}:
        return
    st.markdown("**Message fait hors cockpit**")
    st.caption("À utiliser seulement si le message a réellement été envoyé ailleurs. Une note est obligatoire.")
    outcomes = (
        ["reply_no_appointment", "setting_booked", "closing_booked", "not_relevant", "do_not_contact"]
        if action["type"] == "reply"
        else ["follow_up_sent", "sequence_completed_no_reply"]
    )
    with st.form(f"manual_complete_{action['id']}"):
        outcome = st.selectbox("Résultat", outcomes, format_func=labelize, key=f"manual_complete_outcome_{action['id']}")
        note = st.text_area("Preuve / note obligatoire", height=90, key=f"manual_complete_note_{action['id']}")
        next_due_at = None
        assigned_to_user_id = None
        if outcome in {"setting_booked", "closing_booked"}:
            users = list_users()
            assignee_options = reply_call_assignee_options(users, outcome)
            assignee = st.selectbox("Responsable de l'appel", assignee_options, format_func=format_user, key=f"manual_complete_assignee_{action['id']}")
            next_date = st.date_input("Date du rendez-vous", value=datetime.now().date(), key=f"manual_complete_date_{action['id']}")
            next_time = st.time_input("Heure", value=time(9, 0), key=f"manual_complete_time_{action['id']}")
            next_due_at = local_due_at(next_date, next_time)
            assigned_to_user_id = assignee["id"]
        submitted = st.form_submit_button("Enregistrer hors cockpit")
    if submitted:
        if not note.strip():
            st.error("Ajoutez une note pour documenter l'action faite hors cockpit.")
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
            st.rerun()


def render_standard_action_planner(user: dict, conv: dict, users: list[dict], active_assignee_id: int) -> None:
    if conv.get("status") != "open":
        return

    st.markdown("**Programmer / attribuer une action**")
    st.caption("Choisissez la prochaine action standard. Elle remplace l'action ouverte actuelle et garde une note dans le fil.")
    action_type = st.selectbox(
        "Action",
        STANDARD_NEXT_ACTION_TYPES,
        format_func=standard_action_button_label,
        key=f"standard_action_type_{conv['id']}",
    )
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
        value=datetime.now().date(),
        key=f"standard_action_date_{conv['id']}",
    )
    action_time = st.time_input(
        "Heure",
        value=time(9, 0),
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
        disabled=not note.strip(),
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
            st.rerun()


def render_advanced_actions(user: dict, conv: dict, action: dict | None) -> None:
    if conv.get("status") != "open":
        return
    with st.expander("Actions avancées"):
        st.caption(
            "À utiliser seulement si le message a réellement été envoyé hors du cockpit."
        )
        render_manual_completion_advanced(user, action)


def render_next_action_box(user: dict, conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    users = list_users()
    active_assignee_id = default_assignee_id(conv, action, user)

    if action:
        st.markdown("**Action actuelle**")
        render_current_action_card(action)
        st.markdown('<div class="sc-action-form-gap"></div>', unsafe_allow_html=True)
        if action.get("status") == "blocked":
            render_blocked_action(user, conv, action)
        elif action["type"] in {"reply", "follow_up"}:
            render_whatsapp_action_guidance(user, conv, action)
        elif action["type"] in CALL_ACTION_TYPES:
            render_call_action_form(user, action)
        elif action["type"] == "contact_review":
            render_contact_review_action(user, action)
        else:
            st.info("Action personnalisée. Utilisez les actions avancées pour la documenter ou créer la suite.")
    elif conv["status"] == "open":
        st.warning("Anomalie : cette conversation est ouverte sans prochaine action.")
        st.caption("Créez immédiatement une action principale dans Actions avancées.")
    else:
        st.info("Aucune action ouverte pour cette conversation.")

    if conv["status"] == "open":
        st.divider()
        render_standard_action_planner(user, conv, users, active_assignee_id)
        render_advanced_actions(user, conv, action)
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
    with st.form(f"manual_note_{conv['id']}"):
        body = st.text_area("Résumé ou transcript privé", height=130)
        submitted = st.form_submit_button("Ajouter la note privée")
    if submitted:
        ok, message = add_manual_note(conv["id"], user["id"], body.strip(), True)
        show_result(ok, message)
        if ok:
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
    tasks = sort_work_items(tasks, "attention")

    if not tasks:
        st.info("Aucune action pour ce filtre.")
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
    st.title("Mode d'emploi")
    st.markdown(
        """
        Bienvenue dans Sales Cockpit. Cet outil sert à savoir très vite qui contacter, quand le faire, et quelle suite donner à chaque prospect. Il ne remplace pas SchoolDrive comme source de vérité, mais il regroupe le travail quotidien autour des conversations WhatsApp, des relances, des appels et des qualifications.

        ### Par où commencer

        La page **Tâches** est la page principale. Quand vous vous connectez, vous devez d'abord regarder cette page. Elle montre les actions qui vous sont attribuées : répondre à un message, envoyer une relance, faire un appel setting, faire un appel closing ou revoir un contact particulier. Par défaut, la page affiche votre propre file. Vous pouvez consulter la file d'une autre personne si nécessaire.

        La page **Inbox** sert à retrouver les conversations WhatsApp. Elle est utile pour lire l'historique complet, chercher un prospect, vérifier une conversation terminée ou comprendre ce qui s'est passé avant une action. Dans **Tâches**, on travaille par action. Dans **Inbox**, on consulte par conversation.

        ### Les rôles commerciaux

        **Setter 1** répond aux messages entrants, mène les échanges écrits actifs et réalise les appels de setting. Dans le cockpit, ce rôle correspond principalement aux actions de réponse immédiate et aux appels de setting.

        **Tanjona, Setter II** gère les relances structurées. Elle relit la conversation, choisit le bon modèle WhatsApp quand la fenêtre est fermée, et crée une demande de modèle si aucun modèle existant ne convient.

        **Closer** gère les appels de closing. Après l'appel, il indique le résultat : signé, va signer, indécis, non joint ou non pertinent. Cette décision détermine la suite du parcours.

        ### Fenêtre WhatsApp et modèles

        La fenêtre WhatsApp est ouverte pendant 24 heures après un message entrant du prospect. Quand cette fenêtre est ouverte, vous pouvez envoyer un message libre.

        Quand la fenêtre est fermée, vous ne pouvez pas envoyer de message libre. Vous devez utiliser un modèle WhatsApp approuvé. Si aucun modèle ne correspond à la situation, créez une demande de modèle depuis l'action concernée. L'action reste alors bloquée jusqu'à ce qu'un modèle adapté soit disponible.

        Seuls les admins peuvent créer, synchroniser et soumettre des modèles à Twilio. Les autres utilisateurs peuvent chercher les modèles existants et demander un nouveau modèle si rien ne convient.

        Dans le fil de conversation, les messages envoyés par l'équipe peuvent afficher des coches : une coche signifie envoyé, deux coches signifient reçu, deux coches bleues signifient lu, et un point d'exclamation signale un échec.

        Le premier WhatsApp automatique envoyé après une demande d'information ne suffit pas à ouvrir la fenêtre. La fenêtre s'ouvre seulement quand le prospect répond.

        ### Conversations actives et terminées

        Une conversation active doit toujours avoir une prochaine action. S'il y a une conversation active sans prochaine action, c'est une anomalie à signaler.

        Une conversation terminée signifie qu'il n'y a plus rien à faire pour le moment. Elle peut être réactivée, mais il faut alors choisir immédiatement une prochaine action : répondre, relancer, appeler en setting ou appeler en closing.

        La conversation active ou terminée est différente de la fenêtre WhatsApp ouverte ou fermée. Une conversation peut être active alors que la fenêtre WhatsApp est fermée. Dans ce cas, la suite doit passer par un modèle approuvé.

        ### Fiches à identifier

        Quand un message WhatsApp arrive d'un numéro que le cockpit ne sait pas rattacher avec certitude, la fiche affiche **À identifier**. Cela veut dire soit qu'aucune fiche SchoolDrive connue ne correspond au numéro, soit que plusieurs fiches correspondent.

        Dans ce cas, l'équipe peut répondre au message, mais elle doit compléter les informations temporaires dans **Statuts** : prénom, nom, cours ou catégorie, et une note d'identification. Ces informations servent à travailler tout de suite. Elles doivent rester à vérifier dans SchoolDrive.

        ### Actions, statuts et preuves

        Une action est l'unité de travail du cockpit. Elle dit qui doit faire quoi, pour quel prospect, et à quel moment. Les actions principales sont : répondre au message, envoyer une relance, faire un appel setting, faire un appel closing et revoir un contact.

        Une action peut être planifiée, ouverte, en cours, terminée, annulée ou bloquée. Quand elle est terminée, elle doit laisser une preuve : message WhatsApp envoyé, résultat d'appel, mini-note, qualification ou demande de modèle.

        Pour les appels, la mini-note est obligatoire. Elle permet au prochain utilisateur de comprendre rapidement ce qui s'est passé et pourquoi la suite a été créée.

        Dans l'onglet **Actions**, utilisez **Programmer / attribuer une action** pour créer une prochaine action standard : répondre, relancer, programmer un appel setting ou programmer un appel closing. Le cockpit demande toujours l'action concernée, le responsable, la date et une note. Le parcours affiché en haut de la fiche est mis à jour par ces actions et ne se modifie pas manuellement.

        ### Chaînage des actions

        Quand une action est terminée, le cockpit crée la suite selon la règle métier. Si vous répondez à un prospect sans fixer de rendez-vous, l'action de réponse est terminée et une relance est planifiée pour Tanjona. Si vous fixez un rendez-vous de setting, l'action de réponse est terminée et un appel setting est créé. Si vous fixez directement un rendez-vous de closing, l'action de réponse est terminée et un appel closing est créé pour le closer. Si un appel setting doit passer au closing, une action de closing est créée pour le closer.

        Le chaînage peut être interrompu. Si le prospect répond, la conversation remonte avec une action de réponse immédiate. Si le prospect est marqué **Non pertinent**, **Ne plus contacter** ou **A signé**, les relances s'arrêtent. Si un prospect marqué **Ne plus contacter** écrit à nouveau, le cockpit crée une revue humaine au lieu de relancer automatiquement.

        ### Signaler un problème

        Le bouton **Bug** se trouve dans la barre latérale. Utilisez-le quand une action, une conversation, un statut, une relance ou un affichage vous semble incorrect. Décrivez ce que vous voyez et ce que vous attendiez. Le cockpit enregistre le signalement avec le contexte courant pour faciliter la vérification.
        """
    )


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

    st.subheader("Demandes de modèles à créer")
    requests = [
        item for item in list_template_requests()
        if item.get("status") in {"to_create", "submitted"}
    ]
    if requests:
        st.dataframe(requests, hide_index=True, use_container_width=True, height=220)
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
                    submitted = st.form_submit_button("Créer dans Twilio et soumettre")
                if submitted:
                    if not name.strip() or not body.strip():
                        st.error("Ajoutez un nom et un corps de modèle.")
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
            st.caption("Les demandes seront traitées par Laura, François ou Tiago.")
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
        submitted = st.form_submit_button("Créer le modèle Twilio")
    if submitted:
        if not name.strip() or not body.strip():
            st.error("Ajoutez un nom et un corps de modèle.")
            return
        placeholders = {
            item.strip(): ""
            for item in placeholders_raw.split(",")
            if item.strip()
        }
        ok, message, _template_id = create_and_submit_twilio_template(
            user["id"],
            name.strip(),
            body.strip(),
            category=category,
            placeholders=placeholders,
            submit_for_approval=submit_for_approval,
        )
        show_result(ok, message)
        if ok:
            st.rerun()


def format_sequence_step(step: dict) -> str:
    template = step.get("template_name") or "appel / sans template"
    return (
        f"{step['sequence_code']} #{step['step_index']} · {step['delay']} · "
        f"{template} · {step['meaning']}"
    )


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


def template_source_label(template: dict) -> str:
    if is_real_twilio_template(template):
        return "Twilio DEV"
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
        "Vue lisible pour régler les flux commerciaux avec Laura : sessions par défaut, templates par scénario, règles de conflit et simulation."
    )
    if user["role"] != "admin":
        st.warning("Cette page est réservée aux admins.")
        return

    tabs = st.tabs([
        "Vue d'ensemble",
        "Sessions par défaut",
        "Flux par scénario",
        "Règles de conflit",
        "Simulateur",
    ])
    with tabs[0]:
        render_pilotage_overview()
    with tabs[1]:
        render_pilotage_default_sessions(user)
    with tabs[2]:
        render_pilotage_scenario_tables()
    with tabs[3]:
        render_pilotage_conflict_rules()
    with tabs[4]:
        render_pilotage_simulator()


def render_pilotage_overview() -> None:
    sequences = list_sequences()
    mappings = list_sequence_template_mappings()
    default_sessions = list_course_default_sessions()
    real_templates = [item for item in list_templates() if is_real_twilio_template(item)]
    approved_real = [item for item in real_templates if item.get("status") == "approved"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("Flux actifs", len(sequences))
    metric_cols[1].metric("Templates réels", len(real_templates))
    metric_cols[2].metric("Templates approuvés", len(approved_real))
    metric_cols[3].metric("Sessions par défaut", len(default_sessions))

    st.markdown("### Comment lire cette page")
    st.markdown(
        """
        - **Sessions par défaut** : règle utilisée quand SchoolDrive envoie un Lead avec une catégorie, mais sans session précise.
        - **Flux par scénario** : liste des événements prévus, avec le template recommandé et le message complet.
        - **Règles de conflit** : ce qui gagne quand deux flux se chevauchent ou quand le prospect répond.
        - **Simulateur** : prévisualisation rapide de la timeline à partir d'un type de lead, d'une catégorie et d'une date de cours.

        La donnée SchoolDrive réelle gagne toujours. Une session par défaut ne sert qu'à piloter les relances liées au cours quand le Lead n'a pas encore de session explicite.
        """
    )

    st.markdown("### Flux normaux")
    overview_rows = [
        {
            "Flux": item["label"],
            "Déclencheur": item["trigger"],
            "Timeline": item["timeline"],
            "Responsable": item["owner"],
            "Arrêt": item["stop_when"],
        }
        for item in sequences
    ]
    st.dataframe(overview_rows, hide_index=True, use_container_width=True, height=300)

    st.markdown("### Points à régler avec Laura")
    missing = []
    for step in list_sequence_steps():
        has_mapping = any(
            mapping["sequence_code"] == step["sequence_code"]
            and int(mapping["sequence_step_index"]) == int(step["step_index"])
            for mapping in mappings
        )
        if step.get("template_name") and not has_mapping:
            missing.append(
                {
                    "Flux": label_sequence_code(step["sequence_code"]),
                    "Étape": step["step_index"],
                    "Quand": step["delay"],
                    "À décider": "Choisir le template réel Twilio",
                }
            )
    if missing:
        st.dataframe(missing, hide_index=True, use_container_width=True, height=260)
    else:
        st.success("Toutes les étapes avec template disposent déjà d'une recommandation.")


def render_pilotage_default_sessions(user: dict) -> None:
    st.markdown("### Sessions par défaut par catégorie")
    st.caption(
        "Utilisées uniquement quand un Lead SchoolDrive arrive sans session précise. Si SchoolDrive fournit une vraie session ou une vraie date de début, elle gagne."
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
        st.info("Aucune session par défaut configurée. Ajoute au minimum APP, AS et FSM avant le réglage fin des flux cours.")

    category_options = sorted(set(PILOTAGE_DEFAULT_CATEGORIES + [item["course_category"] for item in active_sessions]))
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
            "Session ou cours par défaut",
            value=(current or {}).get("default_course_name", ""),
            placeholder="Ex. APP VISIO E26",
        )
        session_name = st.text_input(
            "Nom session, optionnel",
            value=(current or {}).get("default_session_name") or "",
        )
        start_date = st.date_input(
            "Date de début",
            value=parse_iso_date_or_today((current or {}).get("default_start_date")),
        )
        schooldrive_url = st.text_input(
            "Lien SchoolDrive, optionnel",
            value=(current or {}).get("schooldrive_url") or "",
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


def render_pilotage_scenario_tables() -> None:
    st.markdown("### Flux par scénario")
    st.caption("Chaque étape montre le template recommandé, son SID Twilio et le message complet.")
    categories = pilotage_categories()
    sequences = list_sequences()
    col_a, col_b, col_c = st.columns([0.8, 0.8, 1.2])
    with col_a:
        lead_type = st.selectbox(
            "Type",
            ["lead", "presubscription", "all"],
            format_func=lambda value: {
                "lead": "Lead",
                "presubscription": "Préinscription",
                "all": "Tous",
            }[value],
        )
    with col_b:
        category = st.selectbox("Catégorie", categories)
    with col_c:
        sequence_code = st.selectbox(
            "Flux",
            [item["code"] for item in sequences],
            format_func=label_sequence_code,
        )

    render_sequence_timeline(sequence_code, lead_type, category)


def render_pilotage_conflict_rules() -> None:
    st.markdown("### Règles de conflit")
    st.caption("Ces règles expliquent ce qui doit se passer quand plusieurs flux ou événements se chevauchent.")
    for index, rule in enumerate(PILOTAGE_CONFLICT_RULES, start=1):
        st.markdown(f"**{index}. {rule['Situation']}**")
        st.write(rule["Règle"])
    st.markdown("### Règles métier de référence")
    selected = [
        item for item in OPERATING_RULES
        if item["rule"] in {
            "Fenêtre WhatsApp",
            "Premier template automatique",
            "Relances hors fenêtre",
            "Délai minimum WhatsApp",
            "Conflit lead vs cours",
            "Non pertinent",
            "Ne plus contacter",
        }
    ]
    st.dataframe(selected, hide_index=True, use_container_width=True, height=300)


def render_pilotage_simulator() -> None:
    st.markdown("### Simulateur de flux")
    st.caption("Prévisualisation simple. Le simulateur ne crée aucune tâche et n'envoie aucun message.")
    default_sessions = {item["course_category"]: item for item in list_course_default_sessions()}
    categories = pilotage_categories()
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        lead_type = st.selectbox(
            "Type de dossier",
            ["lead", "presubscription"],
            format_func=lambda value: "Lead" if value == "lead" else "Préinscription",
            key="pilotage_sim_lead_type",
        )
    with col_b:
        category = st.selectbox("Catégorie", categories, key="pilotage_sim_category")
    with col_c:
        selected_session = default_sessions.get(category)
        default_date = parse_iso_date_or_today((selected_session or {}).get("default_start_date"))
        start_date = st.date_input("Date de début utilisée", value=default_date, key="pilotage_sim_start")

    if lead_type == "lead" and selected_session:
        st.info(
            f"Pour un Lead {category} sans session SchoolDrive, le simulateur utilise : "
            f"{selected_session['default_course_name']} ({selected_session['default_start_date']})."
        )
    elif lead_type == "lead":
        st.warning(f"Aucune session par défaut n'est configurée pour {category}. Les relances liées au cours ne peuvent pas être calculées.")

    selected_sequences = ["lead_no_reply", "setter_no_next_step", "closer_will_sign", "course_start"]
    for code in selected_sequences:
        st.markdown(f"#### {label_sequence_code(code)}")
        rows = build_simulated_timeline(code, start_date)
        st.dataframe(rows, hide_index=True, use_container_width=True)


def render_sequence_timeline(sequence_code: str, lead_type: str, category: str) -> None:
    steps = list_sequence_steps(sequence_code)
    mappings = list_sequence_template_mappings()
    templates_by_name = {item["name"]: item for item in list_templates()}
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
        elif step.get("template_name"):
            template = templates_by_name.get(step["template_name"])

        with st.container(border=True):
            top_cols = st.columns([0.6, 1.2, 1.2, 1.1], vertical_alignment="top")
            top_cols[0].markdown(f"**Étape {step['step_index']}**")
            top_cols[1].markdown(f"**Quand**  \n{step['delay']}")
            top_cols[2].markdown(f"**Événement**  \n{step['meaning']}")
            if template:
                top_cols[3].markdown(
                    f"**Template**  \n{template.get('name') or 'Sans nom'}  \n"
                    f"`{template.get('twilio_content_sid') or 'SID absent'}`"
                )
            else:
                top_cols[3].markdown("**Template**  \nAucun")

            if template:
                status_cols = st.columns([0.5, 0.5, 2.0])
                status_cols[0].markdown(f"**Statut**  \n{template_status_label(template)}")
                status_cols[1].markdown(f"**Catégorie**  \n{labelize(template.get('category'))}")
                mapping_note = (mapping or {}).get("note") if mapping else ""
                status_cols[2].caption(mapping_note or "Mapping exact, spécifique ou fallback démo selon disponibilité.")
                st.markdown("**Message complet**")
                st.code(template.get("body") or "Corps de message indisponible.", language="text")
            else:
                st.warning("Aucun template n'est encore associé à cette étape.")


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
    configured = [item["course_category"] for item in list_course_default_sessions()]
    mapped = [
        item["course_category"]
        for item in list_sequence_template_mappings()
        if item.get("course_category") and item["course_category"] != "all"
    ]
    categories = sorted(set(PILOTAGE_DEFAULT_CATEGORIES + configured + mapped))
    return categories or PILOTAGE_DEFAULT_CATEGORIES


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
        due_label = simulate_due_label(step["delay"], anchor, course_start_date)
        rows.append(
            {
                "Étape": step["step_index"],
                "Quand": step["delay"],
                "Date simulée": due_label,
                "Action": step["meaning"],
                "Template démo": step.get("template_name") or "Aucun",
            }
        )
        if step["delay"].startswith("+"):
            anchor = advance_anchor(anchor, step["delay"])
    return rows


def simulate_due_label(delay: str, anchor: datetime, course_start_date) -> str:
    value = (delay or "").strip()
    if value.startswith("J-"):
        try:
            days = int(value.replace("J-", ""))
            return (course_start_date - timedelta(days=days)).isoformat()
        except ValueError:
            return value
    due = advance_anchor(anchor, value)
    return due.strftime("%Y-%m-%d %H:%M")


def advance_anchor(anchor: datetime, delay: str) -> datetime:
    value = (delay or "").strip().lower()
    if "72h" in value:
        return anchor + timedelta(hours=72)
    if "24h" in value:
        return anchor + timedelta(hours=24)
    if "2h" in value:
        return anchor + timedelta(hours=2)
    if "30j" in value:
        return anchor + timedelta(days=30)
    if "7j" in value:
        return anchor + timedelta(days=7)
    return anchor


def render_admin(user: dict) -> None:
    st.title("Admin")
    if user["role"] != "admin":
        st.warning("Accès lecture seul. Les réglages sont réservés aux admins.")

    tabs = st.tabs(["État", "Utilisateurs", "Règles métier", "Workflow", "Séquences", "Templates", "Bugs & logs", "Intégrations"])
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
        st.subheader("Séquences de relance")
        st.dataframe(list_sequences(), hide_index=True, use_container_width=True)
        st.subheader("Étapes de séquence")
        sequence_steps = list_sequence_steps()
        st.dataframe(sequence_steps, hide_index=True, use_container_width=True, height=300)

        st.subheader("Templates recommandés par étape")
        mappings = list_sequence_template_mappings()
        if mappings:
            mapping_rows = [
                {
                    "Séquence": item["sequence_code"],
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
            st.info("Aucun template réel n'est encore recommandé pour les séquences.")

        st.markdown("**Ajouter ou modifier une recommandation**")
        real_templates = [item for item in list_templates() if is_real_twilio_template(item)]
        if not real_templates:
            st.warning("Synchronisez d'abord les vrais templates Twilio dans la page Modèles.")
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
        requests = list_template_requests()
        if requests:
            st.dataframe(requests, hide_index=True, use_container_width=True, height=320)
            with st.form("update_template_request_status"):
                request = st.selectbox(
                    "Demande",
                    requests,
                    format_func=lambda item: f"#{item['id']} · {lead_display_name(item)} · {labelize(item['status'])}",
                )
                status = st.selectbox(
                    "Nouveau statut",
                    [item["value"] for item in TEMPLATE_REQUEST_STATUSES],
                    index=safe_index([item["value"] for item in TEMPLATE_REQUEST_STATUSES], request["status"]),
                    format_func=labelize,
                )
                submitted = st.form_submit_button("Mettre à jour la demande")
            if submitted:
                ok, message = update_template_request_status(request["id"], user["id"], status)
                show_result(ok, message)
                if ok:
                    st.rerun()
        else:
            st.info("Aucune demande de modèle.")

    with tabs[6]:
        st.subheader("Signalements Bug")
        bug_reports = list_bug_reports()
        if bug_reports:
            st.dataframe(bug_reports, hide_index=True, use_container_width=True, height=320)
        else:
            st.info("Aucun signalement pour le moment.")
        st.subheader("Journal utilisateur")
        st.caption("Derniers événements métier, connexions et signalements. Les événements lead détaillés restent dans `lead_events`.")
        st.dataframe(list_user_activity_log(200), hide_index=True, use_container_width=True, height=420)

    with tabs[7]:
        st.subheader("Intégrations")
        st.markdown(
            """
            - Twilio : mock local actif, synchronisation templates à brancher.
            - SchoolDrive : connecteur read-only à brancher pour leads, types de leads et dates de cours.
            - Notion : connecteur read-only en V1, écriture future possible pour qualifications.
            - Front.io : lecture seule pour récupérer l'historique WhatsApp.
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
        return conv.get("schooldrive_url")
    return SchoolDriveConnector().get_lead_url(conv.get("schooldrive_lead_id"))


def show_result(ok: bool, message: str) -> None:
    if ok:
        st.success(message)
    else:
        st.error(message)


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
    return parsed.astimezone().strftime("%d.%m.%Y %H:%M")


def format_window_boundary(value: str | None) -> str:
    if not value:
        return "Non disponible"
    parsed = parse_dt(value)
    if not parsed:
        return "Non disponible"
    return parsed.astimezone().strftime("%d.%m.%Y à %H:%M")


def format_due(value: str | None) -> str:
    if not value:
        return "Aucune échéance"
    parsed = parse_dt(value)
    if not parsed:
        return "Échéance invalide"
    local = parsed.astimezone()
    today = datetime.now().date()
    if local.date() == today:
        return f"Aujourd’hui {local.strftime('%H:%M')}"
    return local.strftime("%d.%m.%Y %H:%M")


def format_action_datetime(value: str | None) -> str:
    if not value:
        return "Aucune échéance"
    parsed = parse_dt(value)
    if not parsed:
        return "Échéance invalide"
    return parsed.astimezone().strftime("%d.%m %H:%M")


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
    return local_due_at(datetime.now().date() + timedelta(days=days), time(9, 0))


def local_due_at(selected_date, selected_time: time) -> str:
    local_dt = datetime.combine(selected_date, selected_time)
    return local_dt.astimezone(timezone.utc).isoformat()


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
