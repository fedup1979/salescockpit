# Sales Cockpit Build Spec

## Purpose

Sales Cockpit replaces Front.io for ESSR WhatsApp sales operations while keeping SchoolDrive as the lead source of truth.

The app must help setters and closers manage:

- WhatsApp conversations.
- WhatsApp 24-hour window constraints.
- WhatsApp templates.
- Lead qualification.
- Call tasks.
- Manual private WhatsApp notes.
- Complete transcript storage for future AI setter learning.

## Initial Users

- Laura: admin.
- François: admin.
- Tiago: admin.
- Mihary: setter, email `service.etudiants@essr.ch`.
- Yasmine: closer.

Seed password for local mock mode: `ChangeMe!2026`.

## V1 Architecture

- `sales_cockpit/ui/app.py`: Streamlit UI.
- `sales_cockpit/api/main.py`: FastAPI API and webhook-ready endpoints.
- `sales_cockpit/db.py`: SQLite schema and seed data.
- `sales_cockpit/store.py`: app data access and business operations.
- `sales_cockpit/services/whatsapp_rules.py`: WhatsApp 24-hour window logic.
- `sales_cockpit/services/mock_twilio.py`: mock message sending.
- `sales_cockpit/services/schooldrive.py`: placeholder read-only connector.
- `sales_cockpit/services/notion.py`: placeholder read-only connector.

## Core Concepts

### Conversation Status

Operational state set by the user:

- `open`: conversation is active / to handle.
- `resolved`: conversation is considered handled.

This drives inbox tabs:

- `Ouvertes`
- `Résolues`

Users can:

- mark an open conversation as resolved;
- reopen a resolved conversation.

Inbound WhatsApp messages should automatically reopen resolved conversations.

### WhatsApp Window State

Technical state calculated from the last inbound WhatsApp message:

- `open`: last inbound message is less than 24 hours old; free-form messages are allowed.
- `closed`: no inbound message or last inbound message older than 24 hours; approved template required.

This must be enforced in both UI and backend.

## Current UI

### Inbox

Left panel:

- Search.
- Sales-stage filter.
- Tabs: `Ouvertes` and `Résolues`.
- Conversation rows with prospect name, course, responsible person, task count, and last message.
- `Ouvrir` button per row.

Right panel:

- Prospect name.
- Button to mark as resolved or reopen.
- `Ouvrir SchoolDrive` link.
- WhatsApp window badge.
- Metrics for lead status, sales stage, temperature, conversation status.
- Tabs: `Conversation`, `Qualification`, `Tâches`, `Note privée`.

### Conversation Tab

- Message thread.
- Prospect messages aligned left.
- ESSR/team messages aligned right.
- Private notes yellow and aligned right.
- Reply tools directly under the message thread.
- If WhatsApp window is open: free-form composer is enabled.
- If WhatsApp window is closed: free-form composer is blocked and template send remains available.
- Template section has list first, search second, placeholders, resolved preview, then send button.

### Qualification Tab

Fields:

- Sales stage.
- Temperature.
- Lead status.

Dropdown labels are displayed in French. Internal values remain in English.

### Tasks Tab

- Existing tasks.
- Completion with outcome.
- New call task creation.

### Private Note Tab

- Manual note for private/informal WhatsApp conversation.
- Flag to include/exclude note from future AI learning.

## Current Data Model Highlights

SQLite tables include:

- `users`
- `leads`
- `conversations`
- `messages`
- `attachments`
- `whatsapp_templates`
- `template_placeholders`
- `tasks`
- `lead_events`
- `ai_labels`
- `external_refs`
- `integration_sync_runs`

SQLite requirements:

- WAL mode.
- Foreign keys enabled.
- Busy timeout configured.
- Timestamps stored in UTC.

## Mock Data

The seed creates:

- 5 initial users.
- 23 demo conversations.
- At least 10 conversations with WhatsApp window open.
- At least 10 conversations with WhatsApp window closed.
- A few conversations marked as resolved.
- Approved and pending WhatsApp templates.
- Call tasks.

Seed data is idempotent and should not duplicate existing demo leads.

## Test Commands

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run Streamlit:

```powershell
.\scripts\run_streamlit.ps1
```

Run FastAPI:

```powershell
.\scripts\run_api.ps1
```

Health check:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
```

## Next Implementation Areas

1. Continue UX refinement with François.
2. Add real read-only SchoolDrive connector.
3. Add real read-only Notion enrichment.
4. Add Twilio sandbox integration.
5. Add file attachment persistence.
6. Prepare GitHub remote.
7. Prepare DigitalOcean staging.
8. Define SQLite and attachment backup strategy.

