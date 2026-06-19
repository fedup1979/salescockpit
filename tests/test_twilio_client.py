from __future__ import annotations

import pytest

from sales_cockpit.services.twilio_client import (
    TwilioConfigurationError,
    TwilioWhatsAppClient,
)


def test_twilio_client_blocks_recipient_outside_allowlist() -> None:
    client = TwilioWhatsAppClient(
        account_sid="AC_TEST",
        auth_token="token",
        whatsapp_sender="+41445054269",
        allowed_recipients="+41762845576",
    )

    with pytest.raises(TwilioConfigurationError) as exc:
        client._base_params("+41790000000")

    assert "liste de test" in str(exc.value)


def test_twilio_client_allows_recipient_with_whatsapp_prefix() -> None:
    client = TwilioWhatsAppClient(
        account_sid="AC_TEST",
        auth_token="token",
        whatsapp_sender="+41445054269",
        allowed_recipients="whatsapp:+41762845576",
    )

    params = client._base_params("+41762845576")

    assert params["to"] == "whatsapp:+41762845576"
    assert params["from_"] == "whatsapp:+41445054269"
