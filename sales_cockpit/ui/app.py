from __future__ import annotations

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
from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.whatsapp_rules import parse_dt, utc_now
from sales_cockpit.services.schooldrive import SchoolDriveConnector
from sales_cockpit.store import (
    add_manual_note,
    authenticate,
    complete_action_with_workflow,
    create_next_action,
    create_template_request,
    create_template,
    get_conversation,
    get_next_action_for_lead,
    get_template,
    handoff_to_closer,
    list_actions_for_lead,
    list_conversations,
    list_messages,
    list_sequence_steps,
    list_sequences,
    list_tasks,
    list_template_requests,
    list_templates,
    list_users,
    schedule_followup,
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    update_template_request_status,
    update_lead_qualification,
)
from sales_cockpit.ui.styles import APP_CSS


SALES_STAGES = ["new", "setting", "appointment_booked", "closing", "won", "lost", "not_interesting", "no_show", "blacklist"]
LEAD_STATUSES = [item["value"] for item in QUALIFICATION_STATUSES]
CONTACT_STATUS_VALUES = [item["value"] for item in CONTACT_STATUSES]
RESOLUTION_REASON_VALUES = [item["value"] for item in RESOLUTION_REASONS]
URGENCIES = ["low", "normal", "high", "urgent"]
WORK_QUEUES = ["todo", "waiting", "resolved"]
INBOX_QUEUES = ["all"] + WORK_QUEUES
ACTION_QUEUES = ["due", "future", "completed", "all"]
ACTION_TYPES = ["reply", "follow_up", "setting_call", "closing_call", "contact_review", "other"]
WORK_SORTS = ["assignee_name", "lead_name", "due_at"]
ACTION_OUTCOMES = {
    "reply": ["reply_no_appointment", "setting_booked", "not_relevant", "do_not_contact"],
    "follow_up": ["follow_up_sent", "template_missing", "sequence_completed_no_reply"],
    "setting_call": ["to_closing", "not_reached", "not_ready", "not_relevant", "do_not_contact"],
    "closing_call": ["signed", "will_sign", "not_reached", "undecided", "not_relevant"],
    "contact_review": ["maintain_do_not_contact", "lift_do_not_contact"],
    "other": ["done"],
}
REPLY_SEND_OUTCOMES = ["reply_no_appointment", "setting_booked", "not_relevant", "do_not_contact"]
CALL_ACTION_TYPES = {"setting_call", "closing_call"}

DISPLAY_LABELS = {
    "all": "Tous",
    "new": "Nouveau",
    "setting": "Setting",
    "appointment_booked": "RDV pris",
    "closing": "Closing",
    "won": "Gagné",
    "lost": "Perdu",
    "not_interesting": "Pas intéressant",
    "no_show": "No-show",
    "blacklist": "Blacklist",
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
    "open": "Ouverte",
    "resolved": "Résolue",
    "in_progress": "En cours",
    "planned": "Planifiée",
    "done": "Terminée",
    "cancelled": "Annulée",
    "blocked": "Bloquée",
    "todo": "À faire",
    "due": "À faire",
    "future": "À venir",
    "completed": "Terminées",
    "follow_up": "Relancer",
    "waiting": "À venir",
    "reply": "Répondre",
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
        "État du parcours commercial. Il indique où se trouve le prospect dans le processus."
    ),
    "lead_status": (
        "Qualification commerciale. Non pertinent et A signé arrêtent les relances."
    ),
    "contact_status": (
        "Statut de contact séparé. Ne plus contacter bloque les relances, mais une réponse entrante crée une revue humaine."
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
    user = st.session_state.user
    with st.sidebar:
        st.subheader("Sales Cockpit")
        st.caption(f"{user['full_name']} · {user['role']}")
        nav = st.radio(
            "Navigation",
            ["Tâches", "Inbox", "Modèles", "Admin"],
            label_visibility="collapsed",
        )
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

    if nav == "Tâches":
        render_work_queue(user)
    elif nav == "Inbox":
        render_inbox(user)
    elif nav == "Modèles":
        render_templates(user)
    elif nav == "Admin":
        render_admin(user)


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
        st.subheader("File de travail")

        tabs = st.tabs(
            [
                f"{labelize(queue)} ({len(conversations_by_queue[queue])})"
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
                    "Ouvrir",
                    key=f"open_conversation_{bucket}_{conv['conversation_id']}",
                    type=button_type,
                    use_container_width=True,
                ):
                    st.session_state.selected_conversation_id = conv["conversation_id"]
                    st.rerun()


def conversation_row_html(conv: dict) -> str:
    owner = (
        conv.get("next_action_assigned_to_name")
        or conv.get("closer_name")
        or conv.get("setter_name")
        or "Non assigné"
    )
    preview = compact_text(conv.get("last_message_body") or "Aucun message", 96)
    action = conv.get("next_action_title") or "Aucune action ouverte"
    due = format_due(conv.get("next_action_due_at"))
    name = escape_html(f"{conv['first_name']} {conv['last_name']}")
    lead_type = escape_html(labelize(conv.get("lead_type") or "lead"))
    course = escape_html(conversation_course_label(conv))
    owner_html = escape_html(owner)
    preview_html = escape_html(preview)
    action_html = escape_html(compact_text(action, 92))
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
          <div class="sc-lead-type-line">{lead_type}</div>
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

    tabs = st.tabs(["Conversation", "Actions", "Qualification", "Notes privées"])
    with tabs[0]:
        render_messages(conversation_id)
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

    full_name = escape_html(f"{conv['first_name']} {conv['last_name']}")
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
    closes = format_dt(conv.get("window_closes_at")) if conv.get("window_closes_at") else "Non disponible"
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
            <span class="sc-window-close">Ferme : {escape_html(closes)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_conversation_status_button(user: dict, conv: dict) -> None:
    if conv["status"] == "resolved":
        with st.popover("Rouvrir", use_container_width=True):
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
            reason = st.text_area("Raison de réouverture", height=80, key=f"reopen_reason_{conv['id']}")
            submitted = st.button("Rouvrir la conversation", key=f"submit_reopen_{conv['id']}")
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
        with st.popover("Marquer résolue", use_container_width=True):
            reason = st.selectbox(
                "Motif",
                RESOLUTION_REASON_VALUES,
                format_func=labelize,
                key=f"resolve_reason_header_{conv['id']}",
            )
            note = st.text_area("Note", height=80, key=f"resolve_note_header_{conv['id']}")
            submitted = st.button("Confirmer la résolution", key=f"submit_resolve_header_{conv['id']}")
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


def render_compact_lead_state(conv: dict) -> None:
    contact_html = ""
    if conv.get("contact_status") == "do_not_contact":
        contact_html = (
            f'<span><strong>Contact</strong> {escape_html(labelize(conv["contact_status"]))}</span>'
        )
    st.markdown(
        f"""
        <div class="sc-compact-state">
          <span><strong>Qualification</strong> {escape_html(labelize(conv["lead_status"]))}</span>
          <span><strong>Parcours</strong> {escape_html(labelize(conv["sales_stage"]))}</span>
          {contact_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_messages(conversation_id: int) -> None:
    messages = list_messages(conversation_id)
    for message in messages:
        if message["direction"] == "inbound":
            css = "sc-message-inbound"
            row_css = "sc-message-row-inbound"
            sender = "Prospect"
        elif message["direction"] == "manual_note":
            css = "sc-message-note"
            row_css = "sc-message-row-outbound"
            sender = message.get("sender_name") or "Note"
        else:
            css = "sc-message-outbound"
            row_css = "sc-message-row-outbound"
            sender = message.get("sender_name") or "ESSR"
        created = format_dt(message.get("created_at"))
        template = f" · modèle: {message['template_name']}" if message.get("template_name") else ""
        st.markdown(
            f"""
            <div class="sc-message-row {row_css}">
              <div class="sc-message {css}">
                <div class="sc-message-meta">{sender} · {created}{template}</div>
                <div>{escape_html(message['body'])}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def next_action_context(conv: dict) -> dict | None:
    return get_next_action_for_lead(conv["lead_id"])


def reply_send_plan_inputs(
    action: dict | None,
    key_prefix: str,
    users: list[dict],
) -> tuple[str | None, str | None, int | None, str]:
    if not action or action.get("type") != "reply":
        return None, None, None, ""

    st.markdown("**Suite après envoi**")
    outcome = st.selectbox(
        "Résultat de la réponse",
        REPLY_SEND_OUTCOMES,
        format_func=labelize,
        key=f"{key_prefix}_reply_outcome",
    )
    note = st.text_area("Note interne", height=80, key=f"{key_prefix}_reply_note")
    next_due_at = None
    assigned_to_user_id = None
    if outcome == "setting_booked":
        assignee = st.selectbox(
            "Responsable de l'appel",
            users,
            index=safe_user_index(users, action.get("assigned_to_user_id")),
            format_func=format_user,
            key=f"{key_prefix}_reply_assignee",
        )
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
        next_due_at = local_due_at(appointment_date, appointment_time)
        assigned_to_user_id = assignee["id"]
    elif outcome in {"not_relevant", "do_not_contact"}:
        st.warning("Cette réponse résoudra la conversation et annulera les relances futures.")
    else:
        st.caption("Après l'envoi, une relance Setter 2 sera planifiée à +72h si le prospect ne répond pas.")
    return outcome, next_due_at, assigned_to_user_id, note.strip()


def render_composer(user: dict, conv: dict) -> None:
    action = next_action_context(conv)
    users = list_users()
    action_outcome, next_due_at, assigned_to_user_id, action_note = reply_send_plan_inputs(
        action,
        f"reply_plan_{conv['id']}",
        users,
    )
    if conv["window_is_open"]:
        st.success("Fenêtre WhatsApp ouverte : message libre autorisé.")
        with st.form(f"freeform_{conv['id']}"):
            body = st.text_area("Message libre", height=110)
            st.file_uploader("Pièces jointes, mock UI", accept_multiple_files=True)
            submitted = st.form_submit_button("Envoyer le message libre")
        if submitted:
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
    search_key = f"template_search_{conv['id']}"
    template_search = st.session_state.get(search_key, "")
    templates = list_templates(template_search, approved_only=True)
    if not templates:
        st.info("Aucun modèle approuvé ne correspond. Crée un nouveau modèle dans l'onglet Modèles.")
        st.text_input(
            "Recherche de modèles",
            placeholder="Mot dans le nom ou le contenu",
            key=search_key,
        )
        with st.form(f"missing_template_request_{conv['id']}"):
            reason = st.text_input(
                "Demande de modèle",
                placeholder="Ex. relance financement pour APP",
            )
            context = st.text_area(
                "Contexte pour le modèle",
                value=conv.get("last_message_body") or "",
                height=90,
            )
            submitted = st.form_submit_button("Créer la demande de modèle")
        if submitted:
            action = get_next_action_for_lead(conv["lead_id"])
            ok, message = create_template_request(
                conv["id"],
                user["id"],
                reason,
                context,
                task_id=action["id"] if action else None,
            )
            show_result(ok, message)
            if ok:
                st.rerun()
        return

    selected = st.selectbox(
        "Liste des modèles",
        templates,
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

    with st.expander("Aucun modèle ne convient"):
        with st.form(f"template_request_{conv['id']}"):
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
            action = get_next_action_for_lead(conv["lead_id"])
            ok, message = create_template_request(
                conv["id"],
                user["id"],
                reason,
                context,
                task_id=action["id"] if action else None,
            )
            show_result(ok, message)
            if ok:
                st.rerun()


def render_qualification(user: dict, conv: dict) -> None:
    with st.form(f"qualification_{conv['lead_id']}"):
        sales_stage = st.selectbox(
            "Parcours",
            SALES_STAGES,
            index=safe_index(SALES_STAGES, conv["sales_stage"]),
            format_func=labelize,
            help=HELP_TEXTS["sales_stage"],
        )
        lead_status = st.selectbox(
            "Qualification",
            LEAD_STATUSES,
            index=safe_index(LEAD_STATUSES, conv["lead_status"]),
            format_func=labelize,
            help=HELP_TEXTS["lead_status"],
        )
        contact_status = st.selectbox(
            "Statut de contact",
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
            sales_stage,
            lead_status,
            contact_status=contact_status,
        )
        st.success("Qualification mise à jour.")
        st.rerun()


def render_next_action_summary(conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    if conv["status"] == "resolved":
        queue = "resolved"
        title = "Aucune action nécessaire"
        assignee = "Conversation résolue"
        due = "Aucune échéance"
        urgency = "normal"
    elif action:
        queue = detail_work_queue(conv, action)
        title = action["title"]
        assignee = action.get("assigned_to_name") or "Non assigné"
        due = format_due(action.get("due_at"))
        urgency = action.get("urgency") or "normal"
    else:
        queue = "waiting"
        title = "Aucune action ouverte"
        assignee = conv.get("setter_name") or "Non assigné"
        due = "À définir"
        urgency = "normal"

    st.markdown(
        f"""
        <div class="sc-action-panel">
          <div>
            <div class="sc-compact-label">Prochaine action</div>
            <div class="sc-action-title">{escape_html(title)}</div>
            <div class="sc-row-meta">{escape_html(assignee)} · {escape_html(due)}</div>
          </div>
          <div class="sc-action-badges">
            <span class="sc-badge sc-badge-neutral">{escape_html(labelize(queue))}</span>
            <span class="sc-badge sc-badge-neutral">{escape_html(labelize(urgency))}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_next_action_box_legacy(user: dict, conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    users = list_users()
    active_assignee_id = default_assignee_id(conv, action, user)

    if action:
        st.markdown("**Action en cours**")
        st.markdown(
            f"""
            <div class="sc-panel">
              <div class="sc-action-title">{escape_html(action['title'])}</div>
              <div class="sc-row-meta">
                {escape_html(labelize(action['type']))} · {escape_html(action.get('assigned_to_name') or 'Non assigné')} ·
                {escape_html(format_due(action.get('due_at')))} · {escape_html(labelize(action.get('urgency')))}
              </div>
              {f"<div class='sc-action-description'>{escape_html(action['description'])}</div>" if action.get('description') else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )
        outcomes = ACTION_OUTCOMES.get(action["type"], ACTION_OUTCOMES["other"])
        with st.form(f"complete_next_action_form_{action['id']}"):
            outcome = st.selectbox(
                "Résultat",
                outcomes,
                key=f"next_action_outcome_{action['id']}",
                format_func=labelize,
            )
            completion_note = st.text_area("Mini note", height=90, key=f"next_action_note_{action['id']}")
            users_for_outcome = list_users()
            assigned_to_user_id = None
            if outcome in {"to_closing", "setting_booked"}:
                assignee_label = "Closer" if outcome == "to_closing" else "Responsable de l'appel"
                candidates = (
                    [item for item in users_for_outcome if item["role"] == "closer"]
                    if outcome == "to_closing"
                    else users_for_outcome
                )
                assignee = st.selectbox(
                    assignee_label,
                    candidates,
                    format_func=format_user,
                    key=f"next_action_assignee_{action['id']}",
                )
                assigned_to_user_id = assignee["id"]
            needs_due = outcome in {"to_closing", "setting_booked"}
            next_due_at = None
            if needs_due:
                next_date = st.date_input("Date du rendez-vous", value=datetime.now().date(), key=f"next_action_date_{action['id']}")
                next_time = st.time_input("Heure", value=time(9, 0), key=f"next_action_time_{action['id']}")
                next_due_at = local_due_at(next_date, next_time)
            submitted = st.form_submit_button("Terminer l'action")
        if submitted:
            ok, message = complete_action_with_workflow(
                action["id"],
                user["id"],
                outcome,
                note=completion_note,
                next_due_at=next_due_at,
                assigned_to_user_id=assigned_to_user_id,
            )
            show_result(ok, message)
            if ok:
                st.rerun()
    else:
        st.info("Aucune action ouverte pour cette conversation.")

    st.divider()
    st.markdown("**Décision rapide**")
    quick_cols = st.columns(3)
    if quick_cols[0].button("Relancer demain", use_container_width=True):
        ok, message = schedule_followup(
            conv["id"],
            user["id"],
            active_assignee_id,
            quick_due_at(days=1),
            urgency="normal",
        )
        show_result(ok, message)
        if ok:
            st.rerun()
    if quick_cols[1].button("Relancer dans 3 jours", use_container_width=True):
        ok, message = schedule_followup(
            conv["id"],
            user["id"],
            active_assignee_id,
            quick_due_at(days=3),
            urgency="normal",
        )
        show_result(ok, message)
        if ok:
            st.rerun()
    with quick_cols[2].popover("Résoudre", use_container_width=True):
        reason = st.selectbox(
            "Motif",
            RESOLUTION_REASON_VALUES,
            format_func=labelize,
            key=f"resolve_reason_action_{conv['id']}",
        )
        note = st.text_area("Note", height=80, key=f"resolve_note_action_{conv['id']}")
        submitted = st.button("Confirmer", key=f"resolve_confirm_action_{conv['id']}")
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

    st.divider()
    followup_col, closer_col = st.columns(2, gap="large")
    with followup_col:
        st.markdown("**Planifier une relance**")
        with st.form(f"schedule_followup_{conv['lead_id']}"):
            assignee = st.selectbox(
                "Assigné à",
                users,
                index=safe_user_index(users, active_assignee_id),
                format_func=format_user,
            )
            followup_date = st.date_input("Date", value=(datetime.now().date() + timedelta(days=1)))
            followup_time = st.time_input("Heure", value=time(9, 0))
            urgency = st.selectbox("Urgence", URGENCIES, index=1, format_func=labelize)
            notes = st.text_area("Note interne", height=90)
            submitted = st.form_submit_button("Planifier la relance")
        if submitted:
            ok, message = schedule_followup(
                conv["id"],
                user["id"],
                assignee["id"],
                local_due_at(followup_date, followup_time),
                urgency=urgency,
                notes=notes.strip() or None,
            )
            show_result(ok, message)
            if ok:
                st.rerun()

    with closer_col:
        st.markdown("**Passer au closer**")
        closers = [item for item in users if item["role"] == "closer"]
        if not closers:
            st.warning("Aucun closer actif.")
        else:
            with st.form(f"handoff_closer_{conv['lead_id']}"):
                closer = st.selectbox("Closer", closers, format_func=format_user)
                appointment_note = st.text_input("RDV / contexte", placeholder="Ex. disponible demain à 14h")
                notes = st.text_area("Remarques pour le closer", height=90)
                submitted = st.form_submit_button("Passer au closer")
            if submitted:
                ok, message = handoff_to_closer(
                    conv["id"],
                    user["id"],
                    closer["id"],
                    appointment_note.strip(),
                    notes.strip(),
                )
                show_result(ok, message)
                if ok:
                    st.rerun()

    with st.expander("Créer une action manuelle"):
        with st.form(f"manual_action_{conv['lead_id']}"):
            assignee = st.selectbox(
                "Responsable",
                users,
                index=safe_user_index(users, active_assignee_id),
                format_func=format_user,
            )
            action_type = st.selectbox("Type d’action", ACTION_TYPES, format_func=labelize)
            title = st.text_input("Titre", value=f"Contacter {conv['first_name']} {conv['last_name']}")
            action_date = st.date_input("Échéance", value=datetime.now().date())
            action_time = st.time_input("Heure", value=time(9, 0), key=f"manual_action_time_{conv['lead_id']}")
            urgency = st.selectbox("Urgence", URGENCIES, index=1, format_func=labelize, key=f"manual_action_urgency_{conv['lead_id']}")
            description = st.text_area("Description", height=90)
            submitted = st.form_submit_button("Créer l’action")
        if submitted:
            create_next_action(
                conv["lead_id"],
                conv["id"],
                action_type,
                title.strip(),
                assignee["id"],
                user["id"],
                urgency=urgency,
                due_at=local_due_at(action_date, action_time),
                description=description.strip() or None,
            )
            st.success("Action créée.")
            st.rerun()

    actions = list_actions_for_lead(conv["lead_id"], "all")
    if actions:
        st.divider()
        st.markdown("**Historique des actions**")
        for item in actions:
            st.caption(
                f"{item['title']} · {labelize(item['type'])} · {labelize(item['status'])} · "
                f"{item.get('assigned_to_name') or 'Non assigné'} · {format_due(item.get('due_at'))}"
            )


def action_consequence(action_type: str, outcome: str) -> str:
    consequences = {
        ("setting_call", "to_closing"): "Crée un appel de closing pour le closer et passe le parcours en Closing.",
        ("setting_call", "not_reached"): "Crée un rappel d'appel, puis une relance Setter 2 si les rappels sont épuisés.",
        ("setting_call", "not_ready"): "Crée une relance Setter 2 à +72h.",
        ("setting_call", "not_relevant"): "Résout la conversation et annule les relances futures.",
        ("setting_call", "do_not_contact"): "Passe le contact en Ne plus contacter, résout la conversation et bloque les relances.",
        ("closing_call", "signed"): "Marque la vente comme signée, résout la conversation et annule les relances.",
        ("closing_call", "will_sign"): "Crée une relance Setter 2 à +72h, puis suit la séquence Va signer.",
        ("closing_call", "not_reached"): "Crée un rappel d'appel, puis une relance Setter 2 si les rappels sont épuisés.",
        ("closing_call", "undecided"): "Crée une relance Setter 2 à +72h.",
        ("closing_call", "not_relevant"): "Résout la conversation et annule les relances futures.",
        ("contact_review", "maintain_do_not_contact"): "Maintient le blocage Ne plus contacter et résout la conversation.",
        ("contact_review", "lift_do_not_contact"): "Lève le blocage et crée une action Répondre pour Setter 1.",
    }
    return consequences.get((action_type, outcome), "Le système appliquera la suite prévue par la règle métier.")


def render_current_action_card(action: dict) -> None:
    st.markdown(
        f"""
        <div class="sc-panel">
          <div class="sc-action-title">{escape_html(action['title'])}</div>
          <div class="sc-row-meta">
            {escape_html(labelize(action['type']))} · {escape_html(action.get('assigned_to_name') or 'Non assigné')} ·
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

    with st.form(f"blocked_template_request_{action['id']}"):
        reason = st.text_input("Modèle manquant", placeholder="Ex. relance financement pour APP")
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
            task_id=action["id"],
        )
        show_result(ok, message)
        if ok:
            st.rerun()


def render_whatsapp_action_guidance(user: dict, conv: dict, action: dict) -> None:
    if action["type"] == "reply":
        st.info("Le client attend une réponse. Cette action sera clôturée quand le message sera envoyé dans l'onglet Conversation.")
        st.caption("Choisis la suite après envoi directement sous le message libre ou le modèle : relance +72h, RDV setting, Non pertinent ou Ne plus contacter.")
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
    st.warning("Ce prospect est marqué Ne plus contacter, mais il a réécrit. Lis le message avant de décider.")
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
        ["reply_no_appointment", "setting_booked", "not_relevant", "do_not_contact"]
        if action["type"] == "reply"
        else ["follow_up_sent", "sequence_completed_no_reply"]
    )
    with st.form(f"manual_complete_{action['id']}"):
        outcome = st.selectbox("Résultat", outcomes, format_func=labelize, key=f"manual_complete_outcome_{action['id']}")
        note = st.text_area("Preuve / note obligatoire", height=90, key=f"manual_complete_note_{action['id']}")
        next_due_at = None
        assigned_to_user_id = None
        if outcome == "setting_booked":
            users = list_users()
            assignee = st.selectbox("Responsable de l'appel", users, format_func=format_user, key=f"manual_complete_assignee_{action['id']}")
            next_date = st.date_input("Date du rendez-vous", value=datetime.now().date(), key=f"manual_complete_date_{action['id']}")
            next_time = st.time_input("Heure", value=time(9, 0), key=f"manual_complete_time_{action['id']}")
            next_due_at = local_due_at(next_date, next_time)
            assigned_to_user_id = assignee["id"]
        submitted = st.form_submit_button("Enregistrer hors cockpit")
    if submitted:
        if not note.strip():
            st.error("Ajoute une note pour documenter l'action faite hors cockpit.")
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


def render_advanced_actions(user: dict, conv: dict, action: dict | None, users: list[dict], active_assignee_id: int) -> None:
    with st.expander("Actions avancées"):
        render_manual_completion_advanced(user, action)
        st.divider()
        st.markdown("**Planifier une relance exceptionnelle**")
        with st.form(f"schedule_followup_{conv['lead_id']}"):
            assignee = st.selectbox(
                "Assigné à",
                users,
                index=safe_user_index(users, active_assignee_id),
                format_func=format_user,
            )
            followup_date = st.date_input("Date", value=(datetime.now().date() + timedelta(days=1)))
            followup_time = st.time_input("Heure", value=time(9, 0))
            urgency = st.selectbox("Urgence", URGENCIES, index=1, format_func=labelize)
            notes = st.text_area("Note interne", height=90)
            submitted = st.form_submit_button("Planifier la relance")
        if submitted:
            ok, message = schedule_followup(
                conv["id"],
                user["id"],
                assignee["id"],
                local_due_at(followup_date, followup_time),
                urgency=urgency,
                notes=notes.strip() or None,
            )
            show_result(ok, message)
            if ok:
                st.rerun()

        st.divider()
        st.markdown("**Passer au closer hors flux normal**")
        closers = [item for item in users if item["role"] == "closer"]
        if not closers:
            st.warning("Aucun closer actif.")
        else:
            with st.form(f"handoff_closer_{conv['lead_id']}"):
                closer = st.selectbox("Closer", closers, format_func=format_user)
                appointment_note = st.text_input("RDV / contexte", placeholder="Ex. disponible demain à 14h")
                notes = st.text_area("Remarques pour le closer", height=90)
                submitted = st.form_submit_button("Passer au closer")
            if submitted:
                ok, message = handoff_to_closer(
                    conv["id"],
                    user["id"],
                    closer["id"],
                    appointment_note.strip(),
                    notes.strip(),
                )
                show_result(ok, message)
                if ok:
                    st.rerun()

        st.divider()
        st.markdown("**Résoudre manuellement**")
        with st.form(f"resolve_action_{conv['id']}"):
            reason = st.selectbox("Motif", RESOLUTION_REASON_VALUES, format_func=labelize)
            note = st.text_area("Note", height=80)
            submitted = st.form_submit_button("Marquer résolue")
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

        st.divider()
        st.markdown("**Créer une action manuelle**")
        with st.form(f"manual_action_{conv['lead_id']}"):
            assignee = st.selectbox(
                "Responsable",
                users,
                index=safe_user_index(users, active_assignee_id),
                format_func=format_user,
            )
            action_type = st.selectbox("Type d'action", ACTION_TYPES, format_func=labelize)
            title = st.text_input("Titre", value=f"Contacter {conv['first_name']} {conv['last_name']}")
            action_date = st.date_input("Échéance", value=datetime.now().date())
            action_time = st.time_input("Heure", value=time(9, 0), key=f"manual_action_time_{conv['lead_id']}")
            urgency = st.selectbox("Urgence", URGENCIES, index=1, format_func=labelize, key=f"manual_action_urgency_{conv['lead_id']}")
            description = st.text_area("Description", height=90)
            submitted = st.form_submit_button("Créer l'action")
        if submitted:
            create_next_action(
                conv["lead_id"],
                conv["id"],
                action_type,
                title.strip(),
                assignee["id"],
                user["id"],
                urgency=urgency,
                due_at=local_due_at(action_date, action_time),
                description=description.strip() or None,
            )
            st.success("Action créée.")
            st.rerun()


def render_next_action_box(user: dict, conv: dict) -> None:
    action = get_next_action_for_lead(conv["lead_id"])
    users = list_users()
    active_assignee_id = default_assignee_id(conv, action, user)

    if action:
        st.markdown("**Action actuelle**")
        render_current_action_card(action)
        if action.get("status") == "blocked":
            render_blocked_action(user, conv, action)
        elif action["type"] in {"reply", "follow_up"}:
            render_whatsapp_action_guidance(user, conv, action)
        elif action["type"] in CALL_ACTION_TYPES:
            render_call_action_form(user, action)
        elif action["type"] == "contact_review":
            render_contact_review_action(user, action)
        else:
            st.info("Action personnalisée. Utilise les actions avancées pour la documenter ou créer la suite.")
    elif conv["status"] == "open":
        st.warning("Anomalie : cette conversation est ouverte sans prochaine action.")
        st.caption("Crée immédiatement une action principale dans Actions avancées.")
    else:
        st.info("Aucune action ouverte pour cette conversation.")

    render_advanced_actions(user, conv, action, users, active_assignee_id)

    actions = list_actions_for_lead(conv["lead_id"], "all")
    if actions:
        st.divider()
        st.markdown("**Historique des actions**")
        for item in actions:
            proof = " · preuve message" if item.get("proof_message_id") else ""
            outcome = f" · {item['outcome']}" if item.get("outcome") else ""
            st.caption(
                f"{item['title']} · {labelize(item['type'])} · {labelize(item['status'])} · "
                f"{item.get('assigned_to_name') or 'Non assigné'} · {format_due(item.get('due_at'))}"
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
                f"{labelize(queue)} ({len(tasks_by_queue[queue])})"
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
                    "Ouvrir",
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
    name = escape_html(f"{task['first_name']} {task['last_name']}")
    course = escape_html(conversation_course_label(task))
    owner = escape_html(task.get("assigned_to_name") or "Non assigné")
    action_type = escape_html(labelize(task.get("type")))
    title = escape_html(compact_text(task.get("title") or "Action sans titre", 92))
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
          <div class="sc-lead-type-line">{lead_type}</div>
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


def render_templates(user: dict) -> None:
    st.title("Modèles WhatsApp")
    search = st.text_input("Recherche dynamique", placeholder="Ex. financement, rendez-vous, COVID")
    templates = list_templates(search)
    st.subheader("Bibliothèque")
    for template in templates:
        with st.container(border=True):
            st.write(f"**{template['name']}**")
            st.caption(f"{labelize(template['status'])} · {template['language']} · {labelize(template['category'])}")
            st.write(template["body"])

    st.divider()
    st.subheader("Créer un modèle")
    with st.form("create_template"):
        name = st.text_input("Nom interne", placeholder="relance_financement_fsm")
        body = st.text_area(
            "Corps du modèle",
            placeholder="Bonjour {{first_name}}, je reviens vers vous au sujet de {{course_title}}.",
            height=120,
        )
        status = st.selectbox("Statut mock", ["draft", "pending", "approved"], index=0, format_func=labelize)
        placeholders_raw = st.text_input("Placeholders", placeholder="first_name, course_title")
        submitted = st.form_submit_button("Créer le modèle")
    if submitted:
        placeholders = {
            item.strip(): ""
            for item in placeholders_raw.split(",")
            if item.strip()
        }
        create_template(user["id"], name.strip(), body.strip(), status=status, placeholders=placeholders)
        st.success("Modèle créé localement.")
        st.rerun()


def render_admin(user: dict) -> None:
    st.title("Admin")
    if user["role"] != "admin":
        st.warning("Accès lecture seul. Les réglages sont réservés aux admins.")

    tabs = st.tabs(["Utilisateurs", "Règles métier", "Workflow", "Séquences", "Templates", "Intégrations"])
    with tabs[0]:
        st.subheader("Utilisateurs")
        st.dataframe(list_users(active_only=False), hide_index=True, use_container_width=True)
        st.subheader("Rôles commerciaux")
        st.dataframe(SALES_ACTORS, hide_index=True, use_container_width=True)

    with tabs[1]:
        st.subheader("Qualifications")
        st.dataframe(QUALIFICATION_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Statuts de contact")
        st.dataframe(CONTACT_STATUSES, hide_index=True, use_container_width=True)
        st.subheader("Motifs de résolution")
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

    with tabs[2]:
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

    with tabs[3]:
        st.subheader("Séquences de relance")
        st.dataframe(list_sequences(), hide_index=True, use_container_width=True)
        st.subheader("Étapes de séquence")
        st.dataframe(list_sequence_steps(), hide_index=True, use_container_width=True, height=420)
        st.info(
            "V1 affiche les règles. L'automatisation des séquences sera branchée après synchronisation SchoolDrive/Twilio."
        )

    with tabs[4]:
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
                    format_func=lambda item: f"#{item['id']} · {item['first_name']} {item['last_name']} · {labelize(item['status'])}",
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

    with tabs[5]:
        st.subheader("Intégrations")
        st.markdown(
            """
            - Twilio : mock local actif, synchronisation templates à brancher.
            - SchoolDrive : connecteur read-only à brancher pour leads, types de leads et dates de cours.
            - Notion : connecteur read-only en V1, écriture future possible pour qualifications.
            - Front.io : aucun changement de webhook en V1 locale.
            """
        )


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


def format_due(value: str | None) -> str:
    if not value:
        return "Aucune échéance"
    parsed = parse_dt(value)
    if not parsed:
        return "Échéance invalide"
    local = parsed.astimezone()
    now = datetime.now(timezone.utc)
    today = datetime.now().date()
    if parsed < now:
        return f"En retard depuis {local.strftime('%d.%m %H:%M')}"
    if local.date() == today:
        return f"Aujourd’hui {local.strftime('%H:%M')}"
    return local.strftime("%d.%m.%Y %H:%M")


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


def format_user(user: dict) -> str:
    return f"{user['full_name']} · {labelize(user['role'])}"


def format_assignee_filter(user: dict, current_user_id: int | None = None) -> str:
    if user["id"] == "all":
        return "Tous"
    if current_user_id is not None and user["id"] == current_user_id:
        return f"Moi · {user['full_name']}"
    return f"{user['full_name']} · {labelize(user['role'])}"


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
