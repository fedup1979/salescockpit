# Sales Cockpit Build Spec

## Purpose

Sales Cockpit replaces Front.io for ESSR WhatsApp sales operations while keeping SchoolDrive as the lead source of truth.

The app must help setters and closers manage:

- WhatsApp conversations.
- WhatsApp 24-hour window constraints.
- WhatsApp templates.
- Lead qualification.
- Next actions across reply, setting call, follow-up, and closing call.
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
- `sales_cockpit/business_rules.py`: formal sales roles, qualification statuses, action workflow, sequences, schedule rules, and demo template catalog.
- `sales_cockpit/db.py`: SQLite schema and seed data.
- `sales_cockpit/store.py`: app data access and business operations.
- `sales_cockpit/services/whatsapp_rules.py`: WhatsApp 24-hour window logic.
- `sales_cockpit/services/twilio_client.py`: mock-by-default WhatsApp client with Twilio sandbox/live support.
- `sales_cockpit/services/schooldrive.py`: placeholder read-only connector.
- `sales_cockpit/services/notion.py`: placeholder read-only connector.
- `scripts/reset_demo.py`: resets local `SD-DEMO-*` scenarios before manual validation.
- `docs/ACTION_WORKFLOW.md`: source of truth for action workflow decisions and transition table.

## Core Concepts

### Conversation Status

Operational state set by the user:

- `open`: conversation is active / to handle.
- `resolved`: conversation is considered handled.

Users can:

- close an active conversation with `Clore la conversation`;
- reactivate a closed conversation with `Réactiver`.

Visible UI labels should avoid `résolue` / `résolution` for normal users:

- `open` is shown as `Active`;
- `resolved` is shown as `Terminée`;
- resolution reasons are shown as closure reasons where possible.

Inbound WhatsApp messages should automatically reopen resolved conversations.
Resolving a conversation completes open next actions for that lead.

### Next Action / Work Queue

The `tasks` table remains the technical persistence layer, but the UI must call these records `actions` or `prochaines actions`.

Action is the central operational unit of the system. A conversation with `open` status must always have one open next action.

The detailed action model is defined in `docs/ACTION_WORKFLOW.md`.
The exhaustive business logic is defined in `docs/BUSINESS_LOGIC.md`.
Current implementation gaps are tracked in `docs/GAP_ANALYSIS.md`.

Main V1 action types:

- `reply`: answer an inbound WhatsApp message.
- `follow_up`: follow up with the prospect, usually by WhatsApp template.
- `setting_call`: setting / qualification call.
- `closing_call`: closing call.

Qualification, contact status, manual notes, and template creation are support actions or proofs by default. They only become queue-visible work if they block the main action flow.

Work queue labels:

- `À traiter`: action due now or overdue, including reply, call, contact review, blocked template work, or follow-up.
- `En suspens`: future follow-up or future action.
- `Terminées`: conversation is internally `resolved`.
- `Toutes`: all items in the current view.

`follow_up` is an action type, shown as `Envoyer relance`, not a separate Inbox queue.

Operational rules:

- New inbound WhatsApp message creates or updates a `reply` action assigned to the setter.
- Setter can plan a follow-up, pass to closer, resolve, or create a manual action.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- `Non pertinent` and `A signé` are commercial qualifications that stop follow-ups and resolve open conversations.
- `Ne plus contacter` is a separate contact status and strict do-not-contact policy.
- If a `Ne plus contacter` prospect writes again, create a `contact_review` action for Setter 1.
- Manual resolution requires a controlled reason.
- Manual reopening requires creating the next action.
- Missing templates create `template_requests` linked to blocked follow-ups.
- Lead-relative reminder sequence is `+72h, +72h, +72h, +7j, +7j, +30j, stop`.
- Course-date reminders always win over lead-relative reminders; the losing lead-relative action is cancelled.
- Minimum outbound WhatsApp follow-up delay is 24h.

### WhatsApp Window State

Technical state calculated from the last inbound WhatsApp message:

- `open`: last inbound message is less than 24 hours old; free-form messages are allowed.
- `closed`: no inbound message or last inbound message older than 24 hours; approved template required.

This must be enforced in both UI and backend.

## Current UI

### Tâches

Default landing page after login.

Refreshes every 10 seconds while visible.

Left panel:

- Responsible-person filter.
- Operational tabs: `À traiter`, `En suspens`, `Terminées`, `Toutes`.
- Rows represent people/actions, not abstract standalone tasks.
- The responsible-person filter defaults to the connected user's own queue. Users can switch to another person or `Tous`, and the choice persists while navigating between pages.
- Mock data keeps at least one open task per active user for visual checks.
- If the latest prospect message is inbound and unanswered, the row shows a hot but restrained waiting-reply signal and sorts above ordinary due actions.

Right panel:

- Same prospect detail pattern as Inbox.
- Tabs: `Conversation`, `Actions`, `Qualification`, `Notes privées`.

### Inbox

Refreshes every 10 seconds while visible.

Left panel:

- Search.
- Tabs: `Toutes`, `À traiter`, `En suspens`, `Terminées`.
- Conversation rows with prospect name, course, responsible person, next action, due date, and last message.
- If the latest prospect message is inbound and unanswered, the row shows the same waiting-reply signal as `Tâches`.
- `Voir` button per row.

Right panel:

- Prospect name.
- Conversation-state buttons: `Clore la conversation` and `Réactiver`.
- `Ouvrir SchoolDrive` link.
- WhatsApp window badge.
- Compact chips for qualification and parcours.
- Next-action summary panel with only action type, due date/time, and responsible-person badge.
- Tabs: `Conversation`, `Actions`, `Qualification`, `Notes privées`.

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

### Actions Tab

- Current next action with type, owner, due date, status, urgency, and expected proof.
- Contextual action body by action type.
- `reply`: guides the user to send the WhatsApp message from `Conversation`; the send form captures the business outcome and creates the next action.
- `follow_up`: guides the user to send the relance from `Conversation`; closed WhatsApp windows require an approved template.
- `blocked follow_up`: shows the linked missing-template request or lets the user create one.
- `setting_call` and `closing_call`: completed from Actions with result and mandatory call note.
- `contact_review`: shows only the explicit do-not-contact review decisions.
- `Actions avancées`: exceptional manual completion, custom follow-up scheduling, out-of-flow closer handoff, manual resolution, and manual action creation.
- Action history includes outcome and message proof when available.

### Private Note Tab

- Manual note for private/informal WhatsApp conversation.
- Notes are included in the future learning base by default.

### Admin

- Users and commercial roles.
- Qualification statuses and stop rules.
- Workflow tab with main action types, support actions, action statuses, and transition table.
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
- `sequences`
- `sequence_steps`
- `template_requests`

SQLite requirements:

- WAL mode.
- Foreign keys enabled.
- Busy timeout configured.
- Timestamps stored in UTC.

## Mock Data

The seed creates:

- 6 initial users, including Tanjona at `setter2@essr.ch`.
- 23 demo conversations.
- At least 10 conversations with WhatsApp window open.
- At least 10 conversations with WhatsApp window closed.
- A few conversations marked as resolved.
- Approved and pending WhatsApp templates.
- Demo WhatsApp templates for lead, setting, closer-will-sign, course-date, and out-of-hours sequences.
- Next actions across reply, setting call, follow-up, and closing call.

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
4. Configure Twilio sandbox credentials and run a real sandbox validation.
5. Add file attachment persistence.
6. Prepare GitHub remote.
7. Prepare DigitalOcean staging.
8. Define SQLite and attachment backup strategy.
