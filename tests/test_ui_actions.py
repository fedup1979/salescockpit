from datetime import datetime, timezone
from uuid import uuid4

from streamlit.testing.v1 import AppTest

from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import (
    authenticate,
    assign_standard_next_action,
    get_next_action_for_lead,
    list_conversations,
    record_inbound_message,
    set_conversation_status,
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
    info_texts = [item.value for item in app.info]
    button_labels = [item.label for item in app.button]
    caption_texts = [item.value for item in app.caption]
    tab_labels = [item.label for item in app.tabs]

    assert any("Le client attend une réponse" in text for text in info_texts)
    assert any("Sélectionnez la suite après envoi" in text for text in caption_texts)
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
    app.radio[0].set_value("Inbox")
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
    app.radio[0].set_value("Admin")
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
    app.radio[0].set_value("Inbox")
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
