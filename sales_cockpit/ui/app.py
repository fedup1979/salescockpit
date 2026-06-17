from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.whatsapp_rules import parse_dt
from sales_cockpit.services.schooldrive import SchoolDriveConnector
from sales_cockpit.store import (
    add_manual_note,
    authenticate,
    complete_task,
    create_call_task,
    create_template,
    get_conversation,
    get_template,
    list_conversations,
    list_messages,
    list_tasks,
    list_templates,
    list_users,
    send_freeform_message,
    send_template_message,
    set_conversation_status,
    update_lead_qualification,
)
from sales_cockpit.ui.styles import APP_CSS


SALES_STAGES = ["new", "setting", "appointment_booked", "closing", "won", "lost", "not_interesting", "no_show", "blacklist"]
TEMPERATURES = ["cold", "warm", "hot"]
LEAD_STATUSES = ["new", "suspect", "lead", "prospect", "deal_pending", "deal_confirmed", "dead_lead", "dead_prospect"]
URGENCIES = ["low", "normal", "high", "urgent"]
OUTCOMES = ["Reached", "No answer", "Wrong number", "Callback requested", "Appointment booked", "Not interested", "Converted", "Other"]

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
    "prospect": "Prospect",
    "deal_pending": "Deal en attente",
    "deal_confirmed": "Deal confirmé",
    "dead_lead": "Lead perdu",
    "dead_prospect": "Prospect perdu",
    "open": "Ouverte",
    "resolved": "Résolue",
    "in_progress": "En cours",
    "done": "Terminée",
    "cancelled": "Annulée",
    "low": "Faible",
    "normal": "Normale",
    "high": "Élevée",
    "urgent": "Urgente",
    "draft": "Brouillon",
    "pending": "En attente",
    "approved": "Approuvé",
    "utility": "Utilitaire",
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
}

HELP_TEXTS = {
    "sales_stage": (
        "Diagnostic commercial : où en est la personne dans le processus de vente. "
        "Exemples : setting, RDV pris, closing, gagné ou perdu."
    ),
    "temperature": (
        "Niveau d'intérêt estimé. Froid = peu engagé, tiède = intérêt réel mais pas urgent, "
        "chaud = forte probabilité d'action rapide."
    ),
    "lead_status": (
        "Statut CRM du contact. Il décrit la nature du contact dans le pipeline, "
        "par exemple nouveau, lead, prospect, deal en attente ou perdu."
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
    st.caption("Interface interne ESSR pour WhatsApp, tâches d'appel et qualification des leads.")

    with st.form("login", clear_on_submit=False):
        email = st.text_input("E-mail", placeholder="prenom.nom@essr.ch")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter", use_container_width=True)

    if submitted:
        user = authenticate(email.strip(), password)
        if user:
            st.session_state.user = user
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
            ["Inbox", "Tâches", "Modèles", "Admin"],
            label_visibility="collapsed",
        )
        if st.button("Déconnexion", use_container_width=True):
            st.session_state.pop("user", None)
            st.rerun()

    if nav == "Inbox":
        render_inbox(user)
    elif nav == "Tâches":
        render_tasks(user)
    elif nav == "Modèles":
        render_templates(user)
    elif nav == "Admin":
        render_admin(user)


def render_inbox(user: dict) -> None:
    st.title("Inbox WhatsApp")
    st.caption("Tous les leads sont visibles. Le texte libre est bloqué si la fenêtre WhatsApp est fermée.")

    filters = st.columns([2, 1])
    search = filters[0].text_input("Recherche", placeholder="Nom, téléphone, cours, message...")
    stage = filters[1].selectbox("Étape", ["all"] + SALES_STAGES, format_func=labelize)
    conversations = list_conversations(search=search, stage=stage)

    if not conversations:
        st.warning("Aucune conversation trouvée.")
        return

    left, right = st.columns([0.95, 1.45], gap="large")
    with left:
        st.subheader("Conversations")
        open_conversations = [
            conv for conv in conversations if conv["conversation_status"] != "resolved"
        ]
        resolved_conversations = [
            conv for conv in conversations if conv["conversation_status"] == "resolved"
        ]

        visible_ids = {conv["conversation_id"] for conv in conversations}
        if st.session_state.get("selected_conversation_id") not in visible_ids:
            default = open_conversations[0] if open_conversations else conversations[0]
            st.session_state.selected_conversation_id = default["conversation_id"]

        tabs = st.tabs(
            [
                f"Ouvertes ({len(open_conversations)})",
                f"Résolues ({len(resolved_conversations)})",
            ]
        )
        with tabs[0]:
            render_conversation_rows(open_conversations, "open")
        with tabs[1]:
            render_conversation_rows(resolved_conversations, "resolved")
        conversation_id = st.session_state.selected_conversation_id

    with right:
        render_conversation_detail(user, conversation_id)


def render_conversation_rows(conversations: list[dict], bucket: str) -> None:
    if not conversations:
        st.info("Aucune conversation dans cet onglet.")
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
    owner = conv.get("closer_name") or conv.get("setter_name") or "Non assigné"
    preview = compact_text(conv.get("last_message_body") or "Aucun message", 96)
    name = escape_html(f"{conv['first_name']} {conv['last_name']}")
    course = escape_html(conv.get("course_title") or "Sans cours")
    owner_html = escape_html(owner)
    preview_html = escape_html(preview)
    tasks = int(conv.get("open_tasks") or 0)
    task_label = f"{tasks} tâche" if tasks == 1 else f"{tasks} tâches"
    return f"""
        <div class="sc-conversation-row">
          <div class="sc-conversation-title"><strong>{name}</strong></div>
          <div class="sc-row-meta">{course} · {owner_html} · {task_label}</div>
          <div class="sc-preview">{preview_html}</div>
        </div>
    """


def render_conversation_detail(user: dict, conversation_id: int) -> None:
    conv = get_conversation(conversation_id)
    if not conv:
        st.error("Conversation introuvable.")
        return

    full_name = f"{conv['first_name']} {conv['last_name']}"
    header_col, status_action_col, schooldrive_col = st.columns(
        [0.48, 0.24, 0.28], vertical_alignment="center"
    )
    with header_col:
        st.subheader(full_name)
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
    badge_class = "sc-badge-open" if conv["window_is_open"] else "sc-badge-closed"
    window_text = "Fenêtre ouverte" if conv["window_is_open"] else "Fenêtre fermée"
    closes = format_dt(conv.get("window_closes_at")) if conv.get("window_closes_at") else "Non disponible"
    st.markdown(
        f"""
        <div class="sc-topline">
          <span class="sc-badge {badge_class}">{window_text}</span>
          <span>{conv.get('course_title') or 'Sans cours'}</span>
          <span>{conv.get('phone_e164') or ''}</span>
          <span>Ferme : {closes}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    info_cols = st.columns(4)
    info_cols[0].metric("Statut", labelize(conv["lead_status"]))
    info_cols[1].metric("Étape", labelize(conv["sales_stage"]))
    info_cols[2].metric("Température", labelize(conv["temperature"]))
    info_cols[3].metric("Conversation", labelize(conv["status"]))

    tabs = st.tabs(["Conversation", "Qualification", "Tâches", "Note privée"])
    with tabs[0]:
        render_messages(conversation_id)
        st.markdown('<div class="sc-reply-anchor"></div>', unsafe_allow_html=True)
        render_composer(user, conv)
    with tabs[1]:
        render_qualification(user, conv)
    with tabs[2]:
        render_task_box(user, conv)
    with tabs[3]:
        render_manual_note_box(user, conv)


def render_conversation_status_button(user: dict, conv: dict) -> None:
    if conv["status"] == "resolved":
        if st.button("Rouvrir la conversation", use_container_width=True):
            ok, message = set_conversation_status(conv["id"], user["id"], "open")
            show_result(ok, message)
            if ok:
                st.rerun()
    else:
        if st.button("Marquer comme résolue", use_container_width=True):
            ok, message = set_conversation_status(conv["id"], user["id"], "resolved")
            show_result(ok, message)
            if ok:
                st.rerun()


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


def render_composer(user: dict, conv: dict) -> None:
    if conv["window_is_open"]:
        st.success("Fenêtre WhatsApp ouverte : message libre autorisé.")
        with st.form(f"freeform_{conv['id']}"):
            body = st.text_area("Message libre", height=110)
            st.file_uploader("Pièces jointes, mock UI", accept_multiple_files=True)
            submitted = st.form_submit_button("Envoyer le message libre")
        if submitted:
            ok, message = send_freeform_message(conv["id"], user["id"], body.strip())
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
        ok, message = send_template_message(conv["id"], user["id"], template["id"], variables)
        show_result(ok, message)
        if ok:
            st.rerun()


def render_qualification(user: dict, conv: dict) -> None:
    with st.form(f"qualification_{conv['lead_id']}"):
        sales_stage = st.selectbox(
            "Étape commerciale",
            SALES_STAGES,
            index=safe_index(SALES_STAGES, conv["sales_stage"]),
            format_func=labelize,
            help=HELP_TEXTS["sales_stage"],
        )
        temperature = st.selectbox(
            "Température",
            TEMPERATURES,
            index=safe_index(TEMPERATURES, conv["temperature"]),
            format_func=labelize,
            help=HELP_TEXTS["temperature"],
        )
        lead_status = st.selectbox(
            "Statut du lead",
            LEAD_STATUSES,
            index=safe_index(LEAD_STATUSES, conv["lead_status"]),
            format_func=labelize,
            help=HELP_TEXTS["lead_status"],
        )
        submitted = st.form_submit_button("Mettre à jour")
    if submitted:
        update_lead_qualification(conv["lead_id"], user["id"], sales_stage, temperature, lead_status)
        st.success("Qualification mise à jour.")
        st.rerun()


def render_task_box(user: dict, conv: dict) -> None:
    tasks = [task for task in list_tasks("all") if task["lead_id"] == conv["lead_id"]]
    for task in tasks:
        status = labelize(task["status"])
        st.markdown(
            f"**{escape_html(task['title'])}** · {status} · {labelize(task['urgency'])} · {task.get('assigned_to_name') or 'Non assigné'}"
        )
        if task["status"] != "done":
            outcome = st.selectbox("Résultat", OUTCOMES, key=f"outcome_{task['id']}", format_func=labelize)
            if st.button("Marquer terminé", key=f"complete_{task['id']}"):
                complete_task(task["id"], user["id"], outcome)
                st.rerun()

    st.divider()
    with st.form(f"new_task_{conv['lead_id']}"):
        users = list_users()
        assignee = st.selectbox("Assigné à", users, format_func=lambda u: f"{u['full_name']} · {labelize(u['role'])}")
        title = st.text_input("Titre", value=f"Appeler {conv['first_name']}")
        urgency = st.selectbox("Urgence", URGENCIES, index=1, format_func=labelize)
        submitted = st.form_submit_button("Créer une tâche d'appel")
    if submitted:
        create_call_task(
            conv["lead_id"],
            conv["id"],
            title.strip(),
            assignee["id"],
            user["id"],
            urgency,
            due_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        )
        st.success("Tâche créée.")
        st.rerun()


def render_manual_note_box(user: dict, conv: dict) -> None:
    with st.form(f"manual_note_{conv['id']}"):
        body = st.text_area("Résumé ou transcript privé", height=130)
        include = st.checkbox("Inclure dans la base d'apprentissage future", value=True)
        submitted = st.form_submit_button("Ajouter la note privée")
    if submitted:
        ok, message = add_manual_note(conv["id"], user["id"], body.strip(), include)
        show_result(ok, message)
        if ok:
            st.rerun()


def render_tasks(user: dict) -> None:
    st.title("Tâches d'appel")
    status = st.selectbox("Statut", ["open", "in_progress", "done", "cancelled", "all"], format_func=labelize)
    tasks = list_tasks(status)
    if not tasks:
        st.info("Aucune tâche.")
        return
    for task in tasks:
        with st.container(border=True):
            st.write(f"**{task['title']}**")
            st.caption(
                f"{task['first_name']} {task['last_name']} · {task.get('course_title') or 'Sans cours'} · "
                f"{task.get('assigned_to_name') or 'Non assigné'} · {labelize(task['urgency'])} · {labelize(task['status'])}"
            )
            if task["status"] != "done":
                outcome = st.selectbox("Résultat", OUTCOMES, key=f"task_page_outcome_{task['id']}", format_func=labelize)
                if st.button("Terminer", key=f"task_page_complete_{task['id']}"):
                    complete_task(task["id"], user["id"], outcome)
                    st.rerun()


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
    st.subheader("Utilisateurs")
    st.dataframe(list_users(active_only=False), hide_index=True, use_container_width=True)
    st.subheader("Intégrations")
    st.markdown(
        """
        - Twilio : mock local actif.
        - SchoolDrive : connecteur read-only à brancher.
        - Notion : connecteur read-only à brancher.
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
