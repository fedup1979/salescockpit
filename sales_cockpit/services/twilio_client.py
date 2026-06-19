from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sales_cockpit.config import get_settings


@dataclass(frozen=True)
class TwilioSendResult:
    sid: str
    status: str
    provider: str


class TwilioConfigurationError(Exception):
    pass


class TwilioMessageError(Exception):
    pass


class MockWhatsAppClient:
    def send_freeform(self, to_phone: str, body: str) -> TwilioSendResult:
        return TwilioSendResult(
            sid=f"SM_MOCK_{uuid4().hex[:24]}",
            status="sent",
            provider="mock_twilio",
        )

    def send_template(
        self, to_phone: str, content_sid: str, variables: dict[str, str]
    ) -> TwilioSendResult:
        return TwilioSendResult(
            sid=f"SM_MOCK_{uuid4().hex[:24]}",
            status="sent",
            provider="mock_twilio",
        )


class TwilioWhatsAppClient:
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        whatsapp_sender: str | None = None,
        messaging_service_sid: str | None = None,
        allowed_recipients: str | None = None,
        status_callback_url: str | None = None,
    ) -> None:
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.whatsapp_sender = whatsapp_sender
        self.messaging_service_sid = messaging_service_sid
        self.allowed_recipients = _parse_allowed_recipients(allowed_recipients)
        self.status_callback_url = status_callback_url

    def _client(self):
        try:
            from twilio.rest import Client
        except ImportError as exc:
            raise TwilioConfigurationError(
                "Le paquet twilio n'est pas installé dans cet environnement."
            ) from exc
        return Client(self.account_sid, self.auth_token)

    def _base_params(self, to_phone: str) -> dict[str, str]:
        if not to_phone:
            raise TwilioConfigurationError("Numéro WhatsApp destinataire manquant.")
        normalized_to = _normalize_whatsapp_phone(to_phone)
        if self.allowed_recipients and normalized_to not in self.allowed_recipients:
            raise TwilioConfigurationError(
                "Envoi Twilio bloqué : ce numéro n'est pas dans la liste de test autorisée."
            )
        params: dict[str, str] = {"to": _whatsapp_address(to_phone)}
        if self.messaging_service_sid:
            params["messaging_service_sid"] = self.messaging_service_sid
        elif self.whatsapp_sender:
            params["from_"] = _whatsapp_address(self.whatsapp_sender)
        else:
            raise TwilioConfigurationError(
                "Configure SALES_COCKPIT_TWILIO_WHATSAPP_SENDER ou "
                "SALES_COCKPIT_TWILIO_MESSAGING_SERVICE_SID."
            )
        if self.status_callback_url:
            params["status_callback"] = self.status_callback_url
        return params

    def send_freeform(self, to_phone: str, body: str) -> TwilioSendResult:
        params = self._base_params(to_phone)
        params["body"] = body
        try:
            message = self._client().messages.create(**params)
        except Exception as exc:
            raise TwilioMessageError(str(exc)) from exc
        return TwilioSendResult(
            sid=message.sid,
            status=getattr(message, "status", None) or "queued",
            provider="twilio",
        )

    def send_template(
        self, to_phone: str, content_sid: str, variables: dict[str, str]
    ) -> TwilioSendResult:
        if not content_sid or content_sid == "HX_MOCK":
            raise TwilioConfigurationError("Content SID Twilio manquant pour ce modèle.")
        params = self._base_params(to_phone)
        params["content_sid"] = content_sid
        params["content_variables"] = json.dumps(variables or {}, ensure_ascii=False)
        try:
            message = self._client().messages.create(**params)
        except Exception as exc:
            raise TwilioMessageError(str(exc)) from exc
        return TwilioSendResult(
            sid=message.sid,
            status=getattr(message, "status", None) or "queued",
            provider="twilio",
        )


def get_whatsapp_client() -> MockWhatsAppClient | TwilioWhatsAppClient:
    settings = get_settings()
    mode = (settings.twilio_mode or "mock").lower()
    if mode == "mock":
        return MockWhatsAppClient()
    if mode not in {"sandbox", "live"}:
        raise TwilioConfigurationError(f"Mode Twilio invalide: {settings.twilio_mode}.")
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise TwilioConfigurationError(
            "Configure SALES_COCKPIT_TWILIO_ACCOUNT_SID et SALES_COCKPIT_TWILIO_AUTH_TOKEN."
        )
    return TwilioWhatsAppClient(
        account_sid=settings.twilio_account_sid,
        auth_token=settings.twilio_auth_token,
        whatsapp_sender=settings.twilio_whatsapp_sender,
        messaging_service_sid=settings.twilio_messaging_service_sid,
        allowed_recipients=settings.twilio_allowed_recipients,
        status_callback_url=settings.twilio_status_callback_url,
    )


def _whatsapp_address(phone: str) -> str:
    value = phone.strip()
    return value if value.startswith("whatsapp:") else f"whatsapp:{value}"


def _normalize_whatsapp_phone(phone: str) -> str:
    value = phone.strip()
    if value.startswith("whatsapp:"):
        value = value.removeprefix("whatsapp:")
    return "".join(value.split())


def _parse_allowed_recipients(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        normalized
        for item in value.split(",")
        if (normalized := _normalize_whatsapp_phone(item))
    }
