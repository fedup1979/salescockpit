from __future__ import annotations

from hmac import compare_digest
from typing import Any

from fastapi import FastAPI, Header, HTTPException
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
    return {"status": "ok", "version": __version__, "mode": "mock"}


@app.get("/leads")
def leads(search: str = "", stage: str = "all") -> list[dict]:
    return list_conversations(search=search, stage=stage)


@app.get("/conversations/{conversation_id}")
def conversation(conversation_id: int) -> dict:
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = list_messages(conversation_id)
    return conv


@app.post("/conversations/{conversation_id}/messages")
def send_freeform(conversation_id: int, request: FreeformMessageRequest) -> dict:
    ok, message = send_freeform_message(conversation_id, request.user_id, request.body)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@app.post("/conversations/{conversation_id}/template-messages")
def send_template(conversation_id: int, request: TemplateMessageRequest) -> dict:
    ok, message = send_template_message(
        conversation_id, request.user_id, request.template_id, request.variables
    )
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "ok", "message": message}


@app.get("/templates")
def templates(search: str = "", approved_only: bool = False) -> list[dict]:
    return list_templates(search=search, approved_only=approved_only)


@app.post("/templates")
def create_whatsapp_template(request: TemplateCreateRequest) -> dict:
    template_id = create_template(
        user_id=request.user_id,
        name=request.name,
        body=request.body,
        status=request.status,
        language=request.language,
        category=request.category,
        placeholders=request.placeholders,
    )
    return {"status": "ok", "template_id": template_id}


@app.post("/webhooks/twilio/whatsapp/inbound")
def twilio_inbound_mock(request: InboundWebhookRequest) -> dict:
    result = record_inbound_message(
        from_phone=request.from_phone,
        body=request.body,
        lead_id=request.lead_id,
    )
    return {"status": "ok", **result}


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


def _clean_bearer_token(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff")
