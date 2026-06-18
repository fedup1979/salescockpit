# Sales Cockpit Build Spec

## Purpose

Sales Cockpit replaces Front.io for ESSR WhatsApp sales operations while keeping SchoolDrive as the lead source of truth.

The app must help setters and closers manage:

- WhatsApp conversations.
- WhatsApp 24-hour window constraints.
- WhatsApp templates.
- Lead qualification.
- Next actions across reply, call, follow-up, and closing call.
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
- `sales_cockpit/business_rules.py`: formal sales roles, qualification statuses, sequences, schedule rules, and demo template catalog.
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

Users can:

- mark an open conversation as resolved;
- reopen a resolved conversation.

Inbound WhatsApp messages should automatically reopen resolved conversations.
Resolving a conversation completes open next actions for that lead.

### Next Action / Work Queue

The `tasks` table remains the technical persistence layer, but the UI must call these records `actions` or `prochaines actions`.

Work queues:

- `À traiter`: action due now or overdue, usually reply/call/closing call.
- `À relancer`: follow-up action due now or overdue.
- `En attente`: future follow-up or no immediate action.
- `Résolues`: conversation is resolved.

Operational rules:

- New inbound WhatsApp message creates or updates a `reply` action assigned to the setter.
- Setter can plan a follow-up, pass to closer, resolve, or create a manual action.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- `Non pertinent`, `Ne plus contacter`, and `A signé` stop commercial follow-ups and resolve open conversations.
- `Non pertinent` is a commercial qualification. `Ne plus contacter` is a strict do-not-contact policy.
- Lead-relative reminder sequence is `+72h, +72h, +72h, +7j, +7j, +30j, stop`.
- Course-date reminders always win over lead-relative reminders; the losing lead-relative action is cancelled.
- Minimum outbound WhatsApp follow-up delay is 24h.

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
- Responsibility filter: all, setter, closer.
- Tabs: `À traiter`, `À relancer`, `En attente`, `Résolues`.
- Conversation rows with prospect name, course, responsible person, next action, due date, and last message.
- `Ouvrir` button per row.

Right panel:

- Prospect name.
- Button to mark as resolved or reopen.
- `Ouvrir SchoolDrive` link.
- WhatsApp window badge.
- Metrics for qualification status, parcours, and conversation status.
- Next-action summary panel.
- Tabs: `Conversation`, `Qualification`, `À faire`, `Note privée`.

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

- Parcours.
- Qualification.

Dropdown labels are displayed in French. Internal values remain in English.

### À Faire Tab

- Current next action.
- Completion with outcome.
- Quick decisions: follow up tomorrow, follow up in three days, resolve.
- Follow-up scheduling with custom date/time.
- Setter-to-closer handoff.
- Manual action creation.
- Action history.

### Private Note Tab

- Manual note for private/informal WhatsApp conversation.
- Notes are included in the future learning base by default.

### Admin

- Users and commercial roles.
- Qualification statuses and stop rules.
- Operating rules, including WhatsApp window constraints and conflict policy.
- Schedule and absence-transfer rules, currently declarative.
- Follow-up sequences.
- SchoolDrive lead types: `lead` and `presubscription` (`Lead` / `Préinscription` in the UI).
- Demo template catalog used until Twilio template sync exists.

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

- 6 initial users, including Setter 2 at `setter2@essr.ch`.
- 23 demo conversations.
- At least 10 conversations with WhatsApp window open.
- At least 10 conversations with WhatsApp window closed.
- A few conversations marked as resolved.
- Approved and pending WhatsApp templates.
- Demo WhatsApp templates for lead, setting, closer-will-sign, course-date, and out-of-hours sequences.
- Next actions across reply, call, follow-up, and closing call.

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
