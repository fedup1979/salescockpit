from __future__ import annotations

from hmac import compare_digest
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from sales_cockpit import __version__
from sales_cockpit.config import get_settings
from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import (
    create_template,
    get_conversation,
    ingest_schooldrive_snapshot,
    list_conversations,
    list_messages,
    list_templates,
    record_inbound_message,
    record_twilio_status_callback,
    send_freeform_message,
    send_template_message,
)


app = FastAPI(title="Sales Cockpit API", version=__version__)


class FreeformMessageRequest(BaseModel):
    user_id: int
    body: str = Field(min_length=1)


class TemplateMessageRequest(BaseModel):
    user_id: int
    template_id: int
    variables: dict[str, str] = Field(default_factory=dict)


class TemplateCreateRequest(BaseModel):
    user_id: int
    name: str = Field(min_length=1)
    body: str = Field(min_length=1)
    status: str = "draft"
    language: str = "fr"
    category: str = "utility"
    placeholders: dict[str, str] = Field(default_factory=dict)


class InboundWebhookRequest(BaseModel):
    from_phone: str
    body: str
    lead_id: int | None = None


class SchoolDrivePerson(BaseModel):
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None


class SchoolDriveCourse(BaseModel):
    category: str | None = None
    course_name: str | None = None
    session_name: str | None = None
    start_date: str | None = None


class SchoolDriveAutoresponder(BaseModel):
    message_id: str
    autoresponder_id: int | None = None
    template: str | None = None
    short_name: str | None = None
    whatsapp_template_id: str | None = None
    whatsapp_template_variables_mapping: dict[str, Any] | None = None
    whatsapp_send_body: str | None = None
    status: str
    sent_at: str | None = None


class SchoolDrivePayloadData(BaseModel):
    schooldrive_id: str
    lead_type: str
    url: str | None = None
    aggregated_updated_at: str
    is_archived: bool = False
    archived_at: str | None = None
    archive_reason: str | None = None
    person: SchoolDrivePerson
    course: SchoolDriveCourse
    status: str | None = None
    whatsapp_autoresponders: list[SchoolDriveAutoresponder] = Field(default_factory=list)


class SchoolDriveWebhookEnvelope(BaseModel):
    schema_version: str
    event_id: str
    occurred_at: str
    environment: str
    data: SchoolDrivePayloadData


@app.on_event("startup")
def startup() -> None:
    seed_initial_data()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "version": __version__, "mode": settings.twilio_mode}


def _clean_bearer_token(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")


def require_api_access(
    authorization: str | None = Header(default=None),
    x_sales_cockpit_api_key: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    expected_token = _clean_bearer_token(settings.api_token)
    if not expected_token:
        raise HTTPException(status_code=503, detail="Sales Cockpit API token is not configured.")
    provided_token = _extract_access_token(authorization, x_sales_cockpit_api_key)
    if not provided_token:
        raise HTTPException(status_code=401, detail="Missing Sales Cockpit API token.")
    if not compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid Sales Cockpit API token.")


def _extract_access_token(
    authorization: str | None,
    api_key_header: str | None,
) -> str:
    if authorization:
        prefix = "Bearer "
        if authorization.startswith(prefix):
            return _clean_bearer_token(authorization[len(prefix) :])
    return _clean_bearer_token(api_key_header)


def _validate_mock_json_webhook_access(request: Request) -> None:
    settings = get_settings()
    environment = (settings.environment or "local").lower()
    if environment in {"local", "test"}:
        return
    expected_token = _clean_bearer_token(settings.mock_webhook_token or settings.api_token)
    if not expected_token:
        raise HTTPException(status_code=503, detail="Mock webhook token is not configured.")
    provided_token = _extract_access_token(
        request.headers.get("authorization"),
        request.headers.get("x-sales-cockpit-mock-token")
        or request.headers.get("x-sales-cockpit-api-key"),
    )
    if not provided_token:
        raise HTTPException(status_code=401, detail="Missing mock webhook token.")
    if not compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid mock webhook token.")


@app.get("/leads")
def leads(
    search: str = "",
    stage: str = "all",
    _api_access: None = Depends(require_api_access),
) -> list[dict]:
    return list_conversations(search=search, stage=stage)


@app.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: int,
    _api_access: None = Depends(require_api_access),
) -> dict:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = list_messages(conversation_id)
    return conv


@app.post("/conversations/{conversation_id}/messages")
def send_freeform(
    conversation_id: int,
    request: FreeformMessageRequest,
    _api_access: None = Depends(require_api_access),
) -> dict:
    ok, message = send_freeform_message(conversation_id, request.user_id, request.body)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@app.post("/conversations/{conversation_id}/template-messages")
def send_template(
    conversation_id: int,
    request: TemplateMessageRequest,
    _api_access: None = Depends(require_api_access),
) -> dict:
    ok, message = send_template_message(
        conversation_id, request.user_id, request.template_id, request.variables
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@app.get("/templates")
def templates(
    search: str = "",
    approved_only: bool = False,
    _api_access: None = Depends(require_api_access),
) -> list[dict]:
    return list_templates(search=search, approved_only=approved_only)


@app.post("/templates")
def create_whatsapp_template(
    request: TemplateCreateRequest,
    _api_access: None = Depends(require_api_access),
) -> dict:
    try:
        template_id = create_template(
            user_id=request.user_id,
            name=request.name,
            body=request.body,
            status=request.status,
            language=request.language,
            category=request.category,
            placeholders=request.placeholders,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "ok", "template_id": template_id}


@app.post("/webhooks/twilio/whatsapp/inbound")
async def twilio_inbound(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        _validate_mock_json_webhook_access(request)
        return await _record_mock_inbound(request)

    params = await _twilio_form_params(request)
    _validate_twilio_signature(request, params, x_twilio_signature)
    from_phone = _strip_twilio_whatsapp_prefix(params.get("From", ""))
    if not from_phone:
        raise HTTPException(status_code=400, detail="Twilio From is required.")

    result = record_inbound_message(
        from_phone=from_phone,
        body=_twilio_message_body(params),
        twilio_message_sid=(
            params.get("MessageSid") or params.get("SmsMessageSid") or params.get("SmsSid")
        ),
        twilio_status=params.get("SmsStatus") or params.get("MessageStatus") or "received",
        raw_payload=params,
    )
    return {"status": "ok", "provider": "twilio", **result}


@app.post("/webhooks/twilio/whatsapp/status")
async def twilio_status_callback(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    params = await _twilio_form_params(request)
    _validate_twilio_signature(request, params, x_twilio_signature)
    try:
        result = record_twilio_status_callback(
            message_sid=params.get("MessageSid") or params.get("SmsSid") or "",
            status=params.get("MessageStatus") or params.get("SmsStatus") or "",
            error_code=params.get("ErrorCode"),
            error_message=params.get("ErrorMessage"),
            raw_payload=params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    callback_status = result.pop("status")
    return {"status": "ok", "callback_status": callback_status, **result}


@app.post("/webhooks/schooldrive/lead-or-presubscription")
def schooldrive_lead_or_presubscription(
    request: SchoolDriveWebhookEnvelope,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    settings = get_settings()
    expected_token = _clean_bearer_token(settings.schooldrive_webhook_token)
    if not expected_token:
        raise HTTPException(status_code=503, detail="SchoolDrive webhook token is not configured.")
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    provided_token = _clean_bearer_token(authorization[len(prefix) :])
    if not compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="Invalid bearer token.")

    expected_environment = {
        "prod": "production",
        "production": "production",
        "staging": "staging",
        "dev": "staging",
        "local": "staging",
    }.get(settings.environment, settings.environment)
    if request.environment != expected_environment:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Environment mismatch: endpoint is {expected_environment}, "
                f"payload is {request.environment}."
            ),
        )

    try:
        result = ingest_schooldrive_snapshot(request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **result}


async def _record_mock_inbound(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
        inbound_request = InboundWebhookRequest.model_validate(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid mock inbound payload.") from exc
    result = record_inbound_message(
        from_phone=inbound_request.from_phone,
        body=inbound_request.body,
        lead_id=inbound_request.lead_id,
    )
    return {"status": "ok", "provider": "mock", **result}


async def _twilio_form_params(request: Request) -> dict[str, str]:
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Twilio form payload.") from exc
    return {key: str(value) for key, value in form.items()}


def _validate_twilio_signature(
    request: Request,
    params: dict[str, str],
    signature: str | None,
) -> None:
    settings = get_settings()
    if not settings.twilio_validate_signature:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=503, detail="Twilio auth token is not configured.")
    try:
        from twilio.request_validator import RequestValidator
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Twilio SDK is not installed.") from exc

    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(_twilio_validation_url(request), params, signature or ""):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature.")


def _twilio_validation_url(request: Request) -> str:
    settings = get_settings()
    override = (settings.twilio_webhook_url or "").strip().rstrip("/")
    if not override:
        return str(request.url)

    parsed = urlparse(override)
    if parsed.path and parsed.path != "/":
        return override

    url = f"{override}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    return url


def _strip_twilio_whatsapp_prefix(value: str) -> str:
    return value.replace("whatsapp:", "", 1).strip()


def _twilio_message_body(params: dict[str, str]) -> str:
    body = (params.get("Body") or "").strip()
    if body:
        return body
    try:
        media_count = int(params.get("NumMedia") or "0")
    except ValueError:
        media_count = 0
    if media_count <= 0:
        return "[Message WhatsApp sans texte]"

    media_items = []
    for index in range(media_count):
        media_type = params.get(f"MediaContentType{index}") or "media"
        media_url = params.get(f"MediaUrl{index}") or ""
        media_items.append(f"{media_type}: {media_url}" if media_url else media_type)
    return "[Media WhatsApp recu] " + " ; ".join(media_items)
