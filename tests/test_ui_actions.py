from datetime import date, datetime, timedelta, time, timezone
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import (
    authenticate,
    assign_standard_next_action,
    get_next_action_for_lead,
    list_sequence_steps,
    list_conversations,
    record_inbound_message,
    set_conversation_status,
)
from sales_cockpit.ui.app import (
    format_action_datetime,
    format_dt,
    format_due,
    local_due_at,
    message_display_timestamp,
)


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:7]


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
        "mobile_navigation",
        "_last_desktop_navigation",
        "_last_mobile_navigation",
    ]:
        app.session_state[key] = page


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


def test_status_tab_no_longer_exposes_parcours_selector() -> None:
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
    markup = "\n".join(item.value for item in app.markdown)
    assert "Qualification (probabilité que le client s'inscrive)" in selectbox_labels
    assert "Statut de contact (le prospect refuse-t-il qu'on lui écrive ?)" in selectbox_labels
    assert all("parcours" not in label.lower() for label in selectbox_labels)
    assert "Forçage admin du parcours" not in markup


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
    reached = next(item for item in app.radio if item.label == "Avez-vous pu joindre le prospect ?")
    outcome = next(item for item in app.selectbox if item.label == "Résultat de l'appel")
    call_note = next(item for item in app.text_area if item.label == "Note d'appel obligatoire")
    skip_note = next(item for item in app.text_area if item.label == "Mini note obligatoire")
    skip_confirm = next(
        item for item in app.checkbox
        if item.label == "Je confirme que cette étape ne doit pas être faite."
    )
    disabled_buttons = {
        item.label: item.disabled
        for item in app.button
        if item.label in {"Enregistrer le résultat", "Ignorer cette étape"}
    }

    assert "Grisé :" not in markup
    assert any("Aucun appel actif à documenter" in text for text in captions)
    assert any("pas une étape de flux ignorable" in text for text in captions)
    assert reached.disabled is True
    assert outcome.disabled is True
    assert call_note.disabled is True
    assert skip_note.disabled is True
    assert skip_confirm.disabled is True
    assert disabled_buttons["Enregistrer le résultat"] is True
    assert disabled_buttons["Ignorer cette étape"] is True


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
