from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import requests

from sales_cockpit.config import get_settings


CONTENT_API_BASE_URL = "https://content.twilio.com/v1"
TEXT_CONTENT_TYPE = "twilio/text"
READABLE_CONTENT_TYPES = (
    "twilio/text",
    "twilio/call-to-action",
    "twilio/quick-reply",
    "twilio/list-picker",
    "twilio/media",
)


class TwilioContentError(Exception):
    pass


@dataclass(frozen=True)
class TwilioContentTemplate:
    content_sid: str
    name: str
    language: str
    category: str
    body: str
    status: str
    rejection_reason: str | None = None
    content_type: str | None = None
    variables: dict[str, str] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


def list_twilio_templates() -> list[TwilioContentTemplate]:
    templates = []
    for item in _paginated_get(f"{CONTENT_API_BASE_URL}/ContentAndApprovals"):
        templates.append(_normalize_content_template(item))
    return templates


def create_twilio_text_template(
    *,
    name: str,
    body: str,
    language: str = "fr",
    variables: dict[str, str] | None = None,
) -> TwilioContentTemplate:
    payload = {
        "friendly_name": name,
        "language": language,
        "variables": variables or {},
        "types": {
            TEXT_CONTENT_TYPE: {
                "body": body,
            }
        },
    }
    created = _request("POST", f"{CONTENT_API_BASE_URL}/Content", json=payload)
    return _normalize_content_template(created)


def submit_twilio_template_for_whatsapp_approval(
    *,
    content_sid: str,
    approval_name: str,
    category: str,
) -> dict[str, Any]:
    payload = {
        "name": _approval_name(approval_name),
        "category": _approval_category(category),
    }
    return _request(
        "POST",
        f"{CONTENT_API_BASE_URL}/Content/{content_sid}/ApprovalRequests/whatsapp",
        json=payload,
    )


def _paginated_get(url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_url: str | None = f"{url}?PageSize=500"
    while next_url:
        payload = _request("GET", next_url)
        items.extend(payload.get("contents") or [])
        meta = payload.get("meta") or {}
        next_url = meta.get("next_page_url")
    return items


def _request(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    settings = get_settings()
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise TwilioContentError(
            "Configure SALES_COCKPIT_TWILIO_ACCOUNT_SID et SALES_COCKPIT_TWILIO_AUTH_TOKEN."
        )
    try:
        response = requests.request(
            method,
            url,
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
            timeout=30,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise TwilioContentError(f"Twilio Content API inaccessible : {exc}") from exc
    if response.status_code >= 400:
        detail = response.text
        try:
            payload = response.json()
            detail = payload.get("message") or payload.get("detail") or detail
        except ValueError:
            pass
        raise TwilioContentError(f"Twilio Content API a refusé la demande : {detail}")
    try:
        return response.json()
    except ValueError as exc:
        raise TwilioContentError("Réponse Twilio Content API invalide.") from exc


def _normalize_content_template(item: dict[str, Any]) -> TwilioContentTemplate:
    approval = item.get("approval_requests") or item.get("approval_content") or {}
    variables = {
        str(key): str(value)
        for key, value in (item.get("variables") or {}).items()
    }
    content_type, body = _extract_body(item.get("types") or {})
    approval_status = str(approval.get("status") or "").strip().lower()
    return TwilioContentTemplate(
        content_sid=str(item.get("sid") or ""),
        name=str(item.get("friendly_name") or item.get("friendlyName") or ""),
        language=str(item.get("language") or "fr"),
        category=str(approval.get("category") or _infer_category(item) or "utility").lower(),
        body=body,
        status=_map_approval_status(approval_status),
        rejection_reason=str(approval.get("rejection_reason") or "").strip() or None,
        content_type=content_type,
        variables=variables,
        payload=item,
    )


def _extract_body(types: dict[str, Any]) -> tuple[str | None, str]:
    for content_type in READABLE_CONTENT_TYPES:
        config = types.get(content_type)
        if isinstance(config, dict):
            body = (
                config.get("body")
                or config.get("text")
                or config.get("caption")
                or config.get("title")
            )
            if body:
                return content_type, str(body)
    if types:
        first_type, first_config = next(iter(types.items()))
        if isinstance(first_config, dict):
            body = first_config.get("body") or first_config.get("text") or first_config.get("caption")
            if body:
                return first_type, str(body)
        return first_type, f"[Modèle Twilio {first_type}]"
    return None, "[Modèle Twilio sans contenu lisible]"


def _map_approval_status(status: str) -> str:
    if status in {"approved"}:
        return "approved"
    if status in {"received", "pending"}:
        return "pending"
    if status in {"rejected"}:
        return "rejected"
    return "draft"


def _infer_category(item: dict[str, Any]) -> str:
    name = str(item.get("friendly_name") or "").lower()
    if "marketing" in name:
        return "marketing"
    return "utility"


def _approval_category(category: str) -> str:
    value = (category or "utility").strip().upper()
    if value not in {"UTILITY", "MARKETING", "AUTHENTICATION"}:
        return "UTILITY"
    return value


def _approval_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    value = re.sub(r"_+", "_", value)
    if not value:
        value = "sales_cockpit_template"
    return value[:512]
