from uuid import uuid4

from streamlit.testing.v1 import AppTest

from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import authenticate, get_next_action_for_lead, record_inbound_message


def unique_phone() -> str:
    return "+4179" + uuid4().hex[:7]


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

    assert any("Le client attend une réponse" in text for text in info_texts)
    assert any("Choisis la suite après envoi" in text for text in caption_texts)
    assert "Envoyer le message libre" in button_labels
    assert "Terminer l'action" not in button_labels
