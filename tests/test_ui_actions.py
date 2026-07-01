from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from sales_cockpit.db import seed_initial_data
from sales_cockpit.services.front_import import import_front_transition_records
from sales_cockpit.services.message_text import clean_message_body_text
from sales_cockpit.store import (
    authenticate,
    assign_standard_next_action,
    create_bug_report,
    create_template_request,
    get_next_action_for_lead,
    list_users,
    list_tasks,
    list_sequence_steps,
    list_conversations,
    record_inbound_message,
    send_freeform_message,
    set_conversation_status,
    upsert_course_default_session,
)
from sales_cockpit.ui.app import (
    CLOSURE_RESOLUTION_REASON_VALUES,
    admin_work_queue_visible_for_filter,
    conversation_journal_table_html,
    format_action_datetime,
    format_dt,
    format_due,
    labelize,
    login_hint_text,
    local_due_at,
    message_display_timestamp,
    message_body_html,
    simulated_template_label,
    visible_work_queue_tasks_for_user,
)
from sales_cockpit.ui.styles import APP_CSS


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:7]


def unique_front_phone() -> str:
    return "+4179" + "".join(str(int(char, 16) % 10) for char in uuid4().hex[:8])


def render_selected_action(action_id: int, user_email: str = "service.etudiants@essr.ch") -> AppTest:
    user = authenticate(user_email, "ChangeMe!2026")
    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = user
    app.session_state["selected_action_id"] = action_id
    app.run(timeout=10)
    return app


def set_navigation(app: AppTest, page: str) -> None:
    for key in [
        "active_navigation",
        "desktop_navigation",
        "_last_desktop_navigation",
    ]:
        app.session_state[key] = page


def dataframe_titles(app: AppTest) -> list[str]:
    titles: list[str] = []
    for dataframe in app.dataframe:
        if "Titre" in dataframe.value:
            titles.extend(dataframe.value["Titre"].tolist())
    return titles


def test_ui_dates_are_displayed_in_geneva_time() -> None:
    assert format_dt("2026-06-23T06:11:00Z") == "23.06.2026 08:11"
    assert format_action_datetime("2026-06-23T06:11:00Z") == "23.06 08:11"
    assert "08:11" in format_due("2026-06-23T06:11:00Z")
    assert local_due_at(date(2026, 6, 23), time(8, 11)) == "2026-06-23T06:11:00+00:00"
    assert (
        message_display_timestamp(
            {
                "direction": "outbound",
                "created_at": "2026-06-23T06:10:55Z",
                "sent_at": "2026-06-23T06:11:00Z",
            }
        )
        == "2026-06-23T06:11:00Z"
    )


def test_login_hint_uses_environment_seed_password_and_hides_prod() -> None:
    staging = SimpleNamespace(environment="staging", twilio_mode="mock", seed_password="SharedSecret")
    assert login_hint_text(staging) == "Mode staging mock. Mot de passe initial : SharedSecret"

    production = SimpleNamespace(environment="production", twilio_mode="mock", seed_password="SharedSecret")
    assert login_hint_text(production) is None


def test_sidebar_reopen_control_is_not_hidden_and_page_selector_is_removed() -> None:
    assert 'header[data-testid="stHeader"] {\n  height: 0;' not in APP_CSS
    assert 'data-testid="collapsedControl"' not in APP_CSS
    assert '[data-testid="stToolbar"]' not in APP_CSS
    assert ".st-key-mobile_nav" not in APP_CSS
    assert "@media (max-width: 900px)" in APP_CSS

    seed_initial_data()
    user = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = user
    app.run(timeout=10)

    assert len(app.exception) == 0
    assert "Page" not in [item.label for item in app.selectbox]


def test_message_body_cleanup_removes_trailing_orphan_html_tags_only() -> None:
    raw = "Bonjour Dévaki\n\nRépondez simplement 1 ou 2.\n\n          </div>\n        </div>"

    assert clean_message_body_text(raw) == "Bonjour Dévaki\n\nRépondez simplement 1 ou 2."
    assert clean_message_body_text("Je préfère <3\n</div>") == "Je préfère <3"
    assert clean_message_body_text("A < B et C > D") == "A < B et C > D"


def test_message_body_html_preserves_line_breaks_without_raw_html() -> None:
    html = message_body_html("Bonjour Dévaki,\n\nA < B\n\n          </div>\n        </div>")

    assert html == "Bonjour Dévaki,<br><br>A &lt; B"
    assert "\n" not in html
    assert "</div>" not in html


def test_front_transition_actions_have_human_labels() -> None:
    assert labelize("front_transition_review") == "Reprise transition Front"
    assert labelize("front_transition_follow_up") == "Reprise transition Front"


def test_front_transition_review_exposes_followup_planner() -> None:
    seed_initial_data()
    suffix = uuid4().hex[:8]
    phone = unique_front_phone()
    import_front_transition_records(
        [
            {
                "conversation": {
                    "id": f"cnv_front_transition_ui_{suffix}",
                    "subject": f"WhatsApp thread with {phone}",
                    "status": "assigned",
                    "assignee": {"name": "info@essr.ch"},
                },
                "messages": [
                    {
                        "id": f"msg_front_transition_ui_{suffix}",
                        "type": "whatsapp",
                        "is_inbound": True,
                        "created_at": datetime.now(timezone.utc).timestamp(),
                        "text": "Historique Front importé.",
                    }
                ],
            }
        ],
        f"front-transition-ui-{suffix}",
    )
    action = next(
        item
        for item in list_tasks("all")
        if item["type"] == "front_transition_review" and item["phone_e164"] == phone
    )

    app = render_selected_action(action["id"], action["assigned_to_email"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    captions = "\n".join(item.value for item in app.caption)
    button_labels = [item.label for item in app.button]
    text_area_labels = [item.label for item in app.text_area]
    selectbox_labels = [item.label for item in app.selectbox]
    assert "Action inconnue" not in markup
    assert "Transition Front" in markup
    assert "hors flux V1" in captions
    assert "Clôturer la transition Front" in markup
    assert "Programmer une relance transition Front" not in markup
    assert "Programmer relance transition Front" not in button_labels
    assert "Enregistrer la décision" in button_labels
    assert "Note obligatoire" in text_area_labels
    assert "Décision" in selectbox_labels


def test_reply_action_guides_to_conversation_send_without_generic_completion() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "reply"

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = user
    app.session_state["selected_action_id"] = action["id"]
    app.run(timeout=10)

    assert len(app.exception) == 0
    button_labels = [item.label for item in app.button]
    caption_texts = [item.value for item in app.caption]
    tab_labels = [item.label for item in app.tabs]
    markup = "\n".join(item.value for item in app.markdown)

    selectbox_labels = [item.label for item in app.selectbox]
    text_area_labels = [item.label for item in app.text_area]
    warning_texts = [item.value for item in app.warning]
    checkbox_labels = [item.label for item in app.checkbox]

    assert "Répondre dans Conversation" in markup
    assert "Après votre réponse" not in markup
    assert "Suite à créer après l'envoi" not in selectbox_labels
    assert "Note interne, optionnelle" not in text_area_labels
    assert any("faites-le dans Actions" in text for text in caption_texts)
    assert all("choisissez la suite" not in text for text in caption_texts)
    assert any(label.startswith("À traiter") for label in tab_labels)
    assert any(label.startswith("En suspens") for label in tab_labels)
    assert any(label.startswith("Terminées") for label in tab_labels)
    assert any(label.startswith("Toutes") for label in tab_labels)
    assert "Voir" in button_labels
    assert "Ouvrir" not in button_labels
    assert "Envoyer le message libre" in button_labels
    assert "Aucune réponse nécessaire" in button_labels
    assert "Ignorer cette étape" not in button_labels
    assert "Note obligatoire" in text_area_labels
    assert "Je confirme qu'aucune réponse n'est nécessaire." in checkbox_labels
    assert any("Attention danger" in text for text in warning_texts)
    assert "Terminer l'action" not in button_labels


def test_window_and_unknown_labels_render_in_french() -> None:
    seed_initial_data()
    unknown = next(item for item in list_conversations(search="+41790004016"))
    open_window = render_selected_action(unknown["next_action_id"])
    open_markup = "\n".join(item.value for item in open_window.markdown)
    assert len(open_window.exception) == 0
    assert "Inconnu(e)" in open_markup
    assert "Ferme le" in open_markup
    assert "Ferme :" not in open_markup
    assert "WhatsApp Unknown" not in open_markup

    closed = next(item for item in list_conversations(search="+41790004004"))
    closed_window = render_selected_action(closed["next_action_id"], "setter2@essr.ch")
    closed_markup = "\n".join(item.value for item in closed_window.markdown)
    assert len(closed_window.exception) == 0
    assert "Fermée le" in closed_markup
    assert "Ferme :" not in closed_markup

    never_opened = next(item for item in list_conversations(search="+41790004003"))
    never_opened_window = render_selected_action(never_opened["next_action_id"], "setter2@essr.ch")
    never_opened_markup = "\n".join(item.value for item in never_opened_window.markdown)
    assert len(never_opened_window.exception) == 0
    assert "Jamais ouverte" in never_opened_markup


def test_resolved_conversation_hides_whatsapp_send_controls() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Conversation a clore.")

    ok, _ = set_conversation_status(
        result["conversation_id"],
        admin["id"],
        "resolved",
        resolution_reason="other",
        resolution_note="Cloture test.",
    )
    assert ok is True

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.session_state["selected_conversation_id"] = result["conversation_id"]
    app.run(timeout=10)
    set_navigation(app, "Inbox")
    app.run(timeout=10)

    assert len(app.exception) == 0
    info_texts = [item.value for item in app.info]
    button_labels = [item.label for item in app.button]

    assert any("Conversation terminée" in text for text in info_texts)
    assert "Envoyer le modèle approuvé" not in button_labels
    assert "Envoyer le message libre" not in button_labels
    assert "Réactiver" in button_labels


def test_admin_users_table_formats_setter2_role() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Admin")
    app.run(timeout=10)

    assert len(app.exception) == 0
    users_df = next(dataframe.value for dataframe in app.dataframe if "Email" in dataframe.value.columns)
    row = users_df.loc[users_df["Email"] == "setter2@essr.ch"].iloc[0]
    assert row["Nom"] == "Tanjona"
    assert row["Rôle"] == "Setter II"


def test_pilotage_tabs_end_with_flux_views_and_business_logic() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Pilotage")
    app.run(timeout=10)

    assert len(app.exception) == 0
    tab_labels = [item.label for item in app.tabs]
    assert tab_labels[-3:] == ["Flux par scénario", "Vues des flux", "Logique métier"]
    assert "Règles de conflit" not in tab_labels


def test_pilotage_default_sessions_exposes_capacity_fields() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    ok, message = upsert_course_default_session(
        admin["id"],
        "APP",
        "APP VISIO P26",
        "2026-09-01",
        default_session_name="APP printemps 2026",
        default_capacity_total=20,
        default_capacity_occupied=12,
        default_capacity_available=8,
    )
    assert ok, message

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Pilotage")
    app.run(timeout=10)

    assert len(app.exception) == 0
    sessions_df = next(
        dataframe.value
        for dataframe in app.dataframe
        if "Session par défaut" in dataframe.value.columns
    )
    assert {"Capacité", "Occupées", "Disponibles", "Complet"}.issubset(sessions_df.columns)
    row = sessions_df.loc[sessions_df["Catégorie"] == "APP"].iloc[0]
    assert row["Capacité"] == "20"
    assert row["Occupées"] == "12"
    assert row["Disponibles"] == "8"
    assert row["Complet"] == "Non"
    assert "Capacité totale" in [item.label for item in app.text_input]
    assert "Places occupées" in [item.label for item in app.text_input]
    assert "Places disponibles" in [item.label for item in app.text_input]
    assert "Session complète" in [item.label for item in app.checkbox]


def test_conversation_detail_exposes_journal_tab_in_inbox() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.session_state["selected_conversation_id"] = result["conversation_id"]
    app.run(timeout=10)
    set_navigation(app, "Inbox")
    app.run(timeout=10)

    assert len(app.exception) == 0
    tab_labels = [item.label for item in app.tabs]
    joined_tabs = " / ".join(tab_labels)
    assert "Conversation" in tab_labels
    assert "Actions" in tab_labels
    assert "Notes internes" in tab_labels
    assert "Journal" in tab_labels
    assert joined_tabs.index("Notes internes") < joined_tabs.index("Journal")


def test_conversation_journal_table_wraps_description_column() -> None:
    html = conversation_journal_table_html(
        [
            {
                "occurred_at": "2026-06-23T07:12:00Z",
                "category_label": "Action humaine",
                "category": "action_humaine",
                "description": "Action attendue avec une description longue qui doit revenir à la ligne.",
                "actor_label": "Mihary",
            }
        ]
    )

    assert 'class="sc-journal-table"' in html
    assert 'class="sc-journal-description"' in html
    assert "Action attendue avec une description longue" in html
    assert "<div" not in html


def test_admin_navigation_is_reduced_to_operational_tabs() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Admin")
    app.run(timeout=10)

    assert len(app.exception) == 0
    tab_labels = [item.label for item in app.tabs]
    captions = "\n".join(item.value for item in app.caption)
    all_text = "\n".join(
        [*(item.value for item in app.markdown), *(item.value for item in app.caption), *(item.value for item in app.info)]
    )
    assert tab_labels == ["État", "Utilisateurs", "Actions admin", "Garde-fous", "Signalements", "Intégrations"]
    assert "Règles métier" not in tab_labels
    assert "Workflow" not in tab_labels
    assert "Flux" not in tab_labels
    assert "Templates" not in tab_labels
    assert "Bugs & logs" not in tab_labels
    assert "Chaque signalement conserve le contexte" in captions
    assert "Journal utilisateur" not in all_text
    assert "Derniers événements métier" not in captions


def test_admin_work_queue_is_visible_to_all_admins() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    setter = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    title = "Bug visible par tous les admins"
    ok, message = create_bug_report(
        admin["id"],
        "Tâches",
        title,
        "Ce signalement doit apparaître dans la file admin globale.",
    )
    assert ok is True, message

    for email in [
        "laura.escariz@essr.ch",
        "francois.dupuis@essr.ch",
        "tiago.jacobs@gmail.com",
    ]:
        current_admin = authenticate(email, "ChangeMe!2026")
        app = AppTest.from_file("sales_cockpit/ui/app.py")
        app.session_state["user"] = current_admin
        app.run(timeout=10)

        assert len(app.exception) == 0
        assert any(title in item for item in dataframe_titles(app))

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = setter
    app.run(timeout=10)

    assert len(app.exception) == 0
    assert not any(title in item for item in dataframe_titles(app))

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.session_state["work_queue_assignee_user_id"] = admin["id"]
    app.session_state["work_queue_assignee_selected_id"] = setter["id"]
    app.run(timeout=10)

    assert len(app.exception) == 0
    assert not any(title in item for item in dataframe_titles(app))


def test_admin_work_queue_visibility_follows_selected_responsible_filter() -> None:
    seed_initial_data()
    users = {user["email"]: user for user in list_users()}
    admin = users["francois.dupuis@essr.ch"]
    setter = users["service.etudiants@essr.ch"]
    setter2 = users["setter2@essr.ch"]
    closer = users["yasmine@essr.ch"]
    admin_filters = [
        {"id": "all", "role": "all"},
        users["laura.escariz@essr.ch"],
        users["francois.dupuis@essr.ch"],
        users["tiago.jacobs@gmail.com"],
    ]

    assert all(admin_work_queue_visible_for_filter(admin, item) for item in admin_filters)
    assert not admin_work_queue_visible_for_filter(admin, setter)
    assert not admin_work_queue_visible_for_filter(admin, setter2)
    assert not admin_work_queue_visible_for_filter(admin, closer)
    assert not admin_work_queue_visible_for_filter(setter, {"id": "all", "role": "all"})
    assert not admin_work_queue_visible_for_filter(setter, users["laura.escariz@essr.ch"])


def test_non_admin_work_queue_hides_admin_assigned_standard_tasks() -> None:
    seed_initial_data()
    setter = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    tasks = list_tasks("all")
    assert any(task.get("assigned_to_role") == "admin" for task in tasks)
    assert any("Relire la logique de transitions" in task.get("title", "") for task in tasks)

    setter_tasks = visible_work_queue_tasks_for_user(setter, tasks)
    admin_tasks = visible_work_queue_tasks_for_user(admin, tasks)

    assert not any(task.get("assigned_to_role") == "admin" for task in setter_tasks)
    assert any(task.get("assigned_to_role") == "admin" for task in admin_tasks)


def test_pilotage_business_logic_shows_useful_references_without_transfer_rules() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Pilotage")
    app.run(timeout=10)

    assert len(app.exception) == 0
    all_text = "\n".join(
        [
            *(item.value for item in app.markdown),
            *(item.value for item in app.caption),
        ]
    )
    assert "Référentiels métier utiles" in all_text
    assert "Qualifications" in all_text
    assert "Contact" in all_text
    assert "Motifs de clôture" in all_text
    assert "Attribution" in all_text
    assert "Horaires" in all_text
    assert "Tous les cas à valider" in all_text
    assert "Table technique de transition" in all_text
    assert "Horaires entreprise" in all_text
    assert "Absences et backups" not in all_text
    assert "APP, FSM, AS et les autres cours une fois configurés" not in all_text


def test_models_page_remains_template_request_workspace() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Il manque un modèle.")
    ok, message = create_template_request(
        result["conversation_id"],
        admin["id"],
        "Modèle de test manquant.",
        context="Test UI Modèles.",
    )
    assert ok, message

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.run(timeout=10)
    set_navigation(app, "Modèles")
    app.run(timeout=10)

    assert len(app.exception) == 0
    button_labels = [item.label for item in app.button]
    selectbox_labels = [item.label for item in app.selectbox]
    assert "Synchroniser Twilio" in button_labels
    assert "Demande à lier" in selectbox_labels


def test_statuses_are_edited_from_header_bubbles_without_status_tab() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    app.session_state["selected_conversation_id"] = result["conversation_id"]
    app.run(timeout=10)
    set_navigation(app, "Inbox")
    app.run(timeout=10)

    assert len(app.exception) == 0
    selectbox_labels = [item.label for item in app.selectbox]
    text_area_labels = [item.label for item in app.text_area]
    markup = "\n".join(item.value for item in app.markdown)
    tab_labels = [item.label for item in app.tabs]

    assert "Statuts" not in tab_labels
    assert "✎" not in markup
    assert "Qualification" in selectbox_labels
    assert "Contact" in selectbox_labels
    assert "Note facultative" not in text_area_labels
    assert all("parcours" not in label.lower() for label in selectbox_labels)
    assert "Forçage admin du parcours" not in markup


def test_close_conversation_reason_choices_are_simplified() -> None:
    assert "duplicate" not in CLOSURE_RESOLUTION_REASON_VALUES
    assert "sequence_completed_no_reply" not in CLOSURE_RESOLUTION_REASON_VALUES
    assert "handled_elsewhere" in CLOSURE_RESOLUTION_REASON_VALUES
    assert labelize("handled_elsewhere") == "Doublon / Traité ailleurs"


def test_advanced_actions_are_not_exposed() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = user
    app.session_state["selected_action_id"] = action["id"]
    app.run(timeout=10)

    assert len(app.exception) == 0
    markdown = "\n".join(item.value for item in app.markdown)
    button_labels = [item.label for item in app.button]
    assert "Actions avancées" not in markdown
    assert "Message fait hors cockpit" not in markdown
    assert "Créer une action manuelle" not in markdown
    assert "Passer au closer hors flux normal" not in markdown
    assert "Planifier une relance exceptionnelle" not in markdown
    assert "Créer l'action" not in button_labels
    assert "Passer au closer" not in button_labels


def test_actions_tab_keeps_history_out_and_uses_internal_note_labels() -> None:
    source = Path("sales_cockpit/ui/app.py").read_text(encoding="utf-8")

    assert "render_action_history(actions)" not in source
    assert "Ajouter la note interne" in source
    assert "Résumé ou transcript interne" in source
    assert "Ajouter la note privée" not in source
    assert "Résumé ou transcript privé" not in source


def test_call_not_reached_hides_note_fields() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel.")
    ok, message = assign_standard_next_action(
        result["conversation_id"],
        user["id"],
        "setting_call",
        user["id"],
        datetime.now(timezone.utc).isoformat(),
        "RDV test.",
    )
    assert ok, message
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "setting_call"

    app = render_selected_action(action["id"])
    assert len(app.exception) == 0
    assert "Note d'appel obligatoire" in [item.label for item in app.text_area]

    reached = next(item for item in app.radio if item.label == "Avez-vous pu joindre le prospect ?")
    reached.set_value("no")
    app.run(timeout=10)

    assert len(app.exception) == 0
    assert "Note d'appel obligatoire" not in [item.label for item in app.text_area]
    assert "Enregistrer le résultat" in [item.label for item in app.button]


def test_disabled_call_documentation_keeps_fields_visible() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je suis disponible pour un appel demain.")
    ok, message = assign_standard_next_action(
        result["conversation_id"],
        user["id"],
        "setting_call",
        user["id"],
        (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "RDV futur test.",
    )
    assert ok, message
    action = get_next_action_for_lead(result["lead_id"])

    app = render_selected_action(action["id"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    reached = next(item for item in app.radio if item.label == "Avez-vous pu joindre le prospect ?")
    outcome = next(item for item in app.selectbox if item.label == "Résultat de l'appel")
    note = next(item for item in app.text_area if item.label == "Note d'appel obligatoire")

    assert "Grisé :" not in markup
    assert reached.disabled is True
    assert outcome.disabled is True
    assert note.disabled is True


def test_disabled_sections_without_active_action_keep_controls_visible() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])

    app = render_selected_action(action["id"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    captions = [item.value for item in app.caption]
    button_labels = [item.label for item in app.button]
    checkbox_labels = [item.label for item in app.checkbox]
    reached = next(item for item in app.radio if item.label == "Avez-vous pu joindre le prospect ?")
    outcome = next(item for item in app.selectbox if item.label == "Résultat de l'appel")
    call_note = next(item for item in app.text_area if item.label == "Note d'appel obligatoire")
    disabled_buttons = {
        item.label: item.disabled
        for item in app.button
        if item.label in {"Enregistrer le résultat"}
    }

    assert "Grisé :" not in markup
    assert any("Aucun appel actif à documenter" in text for text in captions)
    assert "Ignorer l'étape de flux actuelle" not in markup
    assert "Ignorer cette étape" not in button_labels
    assert "Je confirme que cette étape ne doit pas être faite." not in checkbox_labels
    assert reached.disabled is True
    assert outcome.disabled is True
    assert call_note.disabled is True
    assert disabled_buttons["Enregistrer le résultat"] is True


def test_skippable_flow_step_uses_red_delete_control_in_next_action_box() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Bonjour.")
    ok, message = send_freeform_message(result["conversation_id"], user["id"], "Je reviens vers vous.")
    assert ok is True, message
    followup = get_next_action_for_lead(result["lead_id"])
    assert followup["type"] == "follow_up"

    app = render_selected_action(followup["id"], followup["assigned_to_email"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    button_labels = [item.label for item in app.button]
    warning_texts = [item.value for item in app.warning]
    info_texts = [item.value for item in app.info]
    checkbox_labels = [item.label for item in app.checkbox]
    text_area_labels = [item.label for item in app.text_area]

    assert "Ignorer l'étape de flux actuelle" not in markup
    assert "Ignorer cette étape" in button_labels
    assert any("Attention danger" in text for text in warning_texts)
    assert any("prochaine action sera" in text for text in info_texts)
    assert "Je confirme que cette étape de flux doit être ignorée." in checkbox_labels
    assert "Note obligatoire" in text_area_labels


def test_action_tab_hides_standard_block_label_and_adds_now_shortcut_for_calls() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")
    action = get_next_action_for_lead(result["lead_id"])

    app = render_selected_action(action["id"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    checkbox_keys = [item.key for item in app.checkbox]
    assert "Bloc standard" not in markup
    assert any("schedule_setting_call_now" in key for key in checkbox_keys)
    assert any("schedule_closing_call_now" in key for key in checkbox_keys)


def test_manual_reprise_documentation_has_no_duplicate_info_box() -> None:
    seed_initial_data()
    user = authenticate("service.etudiants@essr.ch", "ChangeMe!2026")
    result = record_inbound_message(unique_phone(), "Je veux des informations.")
    ok, message = assign_standard_next_action(
        result["conversation_id"],
        user["id"],
        "manual_reprise_setter",
        user["id"],
        datetime.now(timezone.utc).isoformat(),
        "Reprise test.",
    )
    assert ok, message
    action = get_next_action_for_lead(result["lead_id"])
    assert action["type"] == "manual_reprise_setter"

    app = render_selected_action(action["id"])

    assert len(app.exception) == 0
    markup = "\n".join(item.value for item in app.markdown)
    info_texts = [item.value for item in app.info]
    assert "Documenter une reprise manuelle" in markup
    assert "Note obligatoire" in [item.label for item in app.text_area]
    assert all("Reprise manuelle setter : relisez" not in text for text in info_texts)


def test_pilotage_sequence_step_editor_persists_selected_step_values() -> None:
    seed_initial_data()
    admin = authenticate("francois.dupuis@essr.ch", "ChangeMe!2026")
    steps = list_sequence_steps("lead_no_reply", active_only=False)
    first_step = steps[0]
    target = steps[1]

    app = AppTest.from_file("sales_cockpit/ui/app.py")
    app.session_state["user"] = admin
    set_navigation(app, "Pilotage")
    app.run(timeout=10)

    step_select = next(item for item in app.selectbox if item.label == "Étape à modifier")
    step_select.set_value(target["id"])
    app.run(timeout=10)

    event_editor = next(
        item
        for item in app.text_area
        if item.label == "Événement" and item.value == target["meaning"]
    )
    event_editor.set_value("Regression test event name for selected step.")
    next(item for item in app.number_input if item.label == "Délai").set_value(5)
    next(item for item in app.selectbox if item.label == "Unité").set_value("days")
    next(item for item in app.button if item.label == "Enregistrer l'étape").click()
    app.run(timeout=10)

    assert len(app.exception) == 0
    updated_steps = list_sequence_steps("lead_no_reply", active_only=False)
    unchanged_first = next(item for item in updated_steps if item["id"] == first_step["id"])
    updated_target = next(item for item in updated_steps if item["id"] == target["id"])
    assert unchanged_first["meaning"] == first_step["meaning"]
    assert updated_target["meaning"] == "Regression test event name for selected step."
    assert updated_target["offset_amount"] == 5
    assert updated_target["offset_unit"] == "days"


def test_pilotage_flow_view_template_column_uses_twilio_template_names() -> None:
    step = {
        "sequence_code": "setter_no_next_step",
        "step_index": 1,
        "action_type": "follow_up",
    }
    base_mapping = {
        "sequence_code": "setter_no_next_step",
        "sequence_step_index": 1,
        "course_category": "APP",
        "template_status": "approved",
        "twilio_content_sid": "HX_REAL_TEMPLATE",
    }

    shared = [
        {
            **base_mapping,
            "lead_type": "all",
            "template_name": "app_relance_commune",
        }
    ]
    split = [
        {
            **base_mapping,
            "lead_type": "lead",
            "template_name": "app_relance_lead",
        },
        {
            **base_mapping,
            "lead_type": "presubscription",
            "template_name": "app_relance_preinscription",
        },
    ]

    assert simulated_template_label(shared, step, "APP") == "app_relance_commune"
    assert (
        simulated_template_label(split, step, "APP")
        == "Lead : app_relance_lead · Préinscription : app_relance_preinscription"
    )
    assert simulated_template_label([], step, "APP") == ""
    assert simulated_template_label(shared, {**step, "action_type": "setting_call"}, "APP") == ""
