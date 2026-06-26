from __future__ import annotations

from hmac import compare_digest
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from sales_cockpit import __version__
from sales_cockpit.config import get_settings
from sales_cockpit.db import seed_initial_data
from sales_cockpit.store import (
    create_template,
    get_attachment_download,
    get_conversation,
    get_next_action_for_lead,
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
    action_id: int | None = None


class TemplateMessageRequest(BaseModel):
    user_id: int
    template_id: int
    variables: dict[str, str] = Field(default_factory=dict)
    action_id: int | None = None


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
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None


class SchoolDriveCourse(BaseModel):
    model_config = ConfigDict(extra="allow")

    course_id: str | int | None = None
    course_short_name: str | None = None
    category_short_title: str | None = None
    category: str | dict[str, Any] | None = None
    course_name: str | None = None
    session_name: str | None = None
    start_date: str | None = None
    seats_total: int | None = None
    seats_occupied: int | None = None
    seats_available: int | None = None
    is_full: bool | None = None


class SchoolDriveAutoresponder(BaseModel):
    model_config = ConfigDict(extra="allow")

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
    model_config = ConfigDict(extra="allow")

    schooldrive_id: str
    lead_type: str
    url: str | None = None
    aggregated_updated_at: str
    is_archived: bool = False
    archived_at: str | None = None
    archive_reason: str | None = None
    signed: bool | dict[str, Any] | None = None
    signed_at: str | None = None
    do_not_contact: bool | dict[str, Any] | None = None
    person: SchoolDrivePerson
    course: SchoolDriveCourse = Field(default_factory=SchoolDriveCourse)
    product: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    related_subscriptions: list[dict[str, Any]] = Field(default_factory=list)
    whatsapp_autoresponders: list[SchoolDriveAutoresponder] = Field(default_factory=list)


class SchoolDriveWebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    event_id: str
    occurred_at: str
    environment: str
    data: SchoolDrivePayloadData


def _require_action_id_for_api_send(conversation_id: int, action_id: int | None) -> None:
    if action_id is not None:
        return
    conv = get_conversation(conversation_id)
    if not conv:
        return
    action = get_next_action_for_lead(conv["lead_id"])
    if action and action.get("type") in {"reply", "follow_up"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "action_id requis pour envoyer un WhatsApp sur une action active. "
                "Recharge la fiche et renvoie l'identifiant de l'action."
            ),
        )


@app.on_event("startup")
def startup() -> None:
    seed_initial_data()


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {"status": "ok", "version": __version__, "mode": settings.twilio_mode}


@app.get("/media/attachments/{attachment_id}/{token_name}")
def media_attachment(attachment_id: int, token_name: str) -> FileResponse:
    attachment = get_attachment_download(attachment_id, token_name)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(
        path=attachment["path"],
        media_type=attachment["mime_type"],
        filename=attachment["file_name"],
    )


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
    limit: int = 200,
    offset: int = 0,
    _api_access: None = Depends(require_api_access),
) -> list[dict]:
    return list_conversations(search=search, stage=stage, limit=limit, offset=offset)


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
    _require_action_id_for_api_send(conversation_id, request.action_id)
    ok, message = send_freeform_message(
        conversation_id,
        request.user_id,
        request.body,
        expected_action_id=request.action_id,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@app.post("/conversations/{conversation_id}/template-messages")
def send_template(
    conversation_id: int,
    request: TemplateMessageRequest,
    _api_access: None = Depends(require_api_access),
) -> dict:
    _require_action_id_for_api_send(conversation_id, request.action_id)
    ok, message = send_template_message(
        conversation_id,
        request.user_id,
        request.template_id,
        request.variables,
        expected_action_id=request.action_id,
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
