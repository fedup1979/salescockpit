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
- `sales_cockpit/api/main.py` + `sales_cockpit/store.py`: implemented SchoolDrive snapshot webhook ingestion. `sales_cockpit/services/schooldrive.py` remains only a small URL/helper placeholder for future read-only enrichment.
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

Action is the central operational unit of the system. A conversation with `open` status normally has one open main next action.

Canonical exception: if a prospect writes while a setting/closing call is already planned, Sales Cockpit creates an urgent `reply` action without cancelling the planned call. After the reply is sent, if the appointment remains unchanged, the planned call becomes the visible next action again.

The detailed action model is defined in `docs/ACTION_WORKFLOW.md`.
The exhaustive business logic is defined in `docs/BUSINESS_LOGIC.md`.
Current implementation gaps are tracked in `docs/GAP_ANALYSIS.md`.

Main V1 action types:

- `reply`: answer an inbound WhatsApp message.
- `follow_up`: follow up with the prospect, usually by WhatsApp template.
- `setting_call`: planned setting call to document at appointment time.
- `closing_call`: planned closing call to document at appointment time.

Qualification, contact status, manual notes, and template creation are support actions or proofs by default. They only become queue-visible work if they block the main action flow.

Work queue labels:

- `À traiter`: action due now or overdue, including reply, call, contact review, blocked template work, or follow-up.
- `En suspens`: future follow-up or future action.
- `Terminées`: conversation is internally `resolved`.
- `Toutes`: all items in the current view.

`follow_up` is an action type, shown as `Envoyer relance`, not a separate Inbox queue.

Operational rules:

- New inbound WhatsApp message creates or updates a `reply` action assigned to the setter.
- Inbound WhatsApp identity matching is strict: one phone match attaches automatically; zero or multiple matches create an `À identifier` temporary record.
- Setter can plan a follow-up, plan a setting call, plan a closing call, or close the conversation with a controlled reason.
- Passing to closing through the normal workflow completes the relevant current action, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- `Non pertinent` and `A signé` are commercial qualifications that stop follow-ups and resolve open conversations.
- `Ne plus contacter` is a separate contact status and strict do-not-contact policy.
- If a `Ne plus contacter` prospect writes again, create a `contact_review` action for Setter I.
- Manual resolution requires a controlled reason.
- Manual reopening requires creating the next action.
- Missing templates create `template_requests` linked to blocked follow-ups.
- Lead-relative reminder sequence is absolute from the flow trigger: `T+72h, T+144h, T+216h, T+16j, T+23j, T+53j, stop`.
- Course-date reminders win over lead-relative reminders when they conflict within 24h; the losing lead-relative action is cancelled. They do not replace an already planned setting/closing call.
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
- Tabs: `Conversation`, `Actions`, `Notes privées`.

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
- Tabs: `Conversation`, `Actions`, `Notes privées`.

### Conversation Tab

- Message thread.
- Prospect messages aligned left.
- ESSR/team messages aligned right.
- Private notes yellow and aligned right.
- Temporary or ambiguous identity records show an `À identifier` badge.
- Reply tools directly under the message thread.
- If WhatsApp window is open: free-form composer is enabled.
- If WhatsApp window is closed: free-form composer is blocked and template send remains available.
- Template section has list first, search second, placeholders, resolved preview, then send button.
- The Conversation tab never asks which next action to create after sending. It only sends free-form messages, sends approved templates, or creates a template request.
- After an outbound reply, the store creates the default waiting flow automatically. If a call or manual reprise is needed after the message, the user creates it from `Actions`.

### Status Chips

- `Parcours` is read-only.
- `Qualification` and `Contact` are always visible in the compact chips and editable from the icon beside the chips.
- The status edit note is optional.
- Dropdown labels are displayed in French. Internal values remain in English.

### Actions Tab

- Stable structure: status banner, fixed standard block, then read-only action history.
- Blue banner: normal expected work, for example reply or follow-up to send from `Conversation`, planned call, due call, or manual reprise.
- Orange banner: blocked action or status to review, for example missing WhatsApp template, `Ne plus contacter`, or terminal qualification to handle from the status chips.
- Red banner: workflow anomaly, for example open conversation without action, resolved conversation with active action, unknown action type, or legacy `other`.
- Fixed standard block is hidden when the conversation is terminated. When visible, unavailable sections remain visible and greyed with a short reason.
- Fixed sections: program/modify call, document due call, request manual reprise, document manual reprise, skip current flow step.
- `reply` and `follow_up` are system actions only. They are never programmed manually from the standard block and are completed by the outbound WhatsApp proof from `Conversation`.
- Calls and manual reprises are created from the standard Actions block, including after a message sent from `Conversation` has created the default follow-up flow.
- `contact_review` is not completed from Actions. Users review or lift statuses from the status chips; the store closes obsolete contact reviews or recreates the appropriate reply when allowed.
- `other` is backend fallback/anomaly only. The normal UI does not show an `other` completion form and `Pilotage` does not offer it as a normal new step type.
- Action history includes outcome and message proof when available.

### Private Note Tab

- Manual note for private/informal WhatsApp conversation.
- Notes are included in the future learning base by default.

### Admin

- Admin is the technical and support console: readiness, users, admin actions, outbound safeguards, signalements, and integrations.
- Commercial flow tuning lives in `Pilotage`: course categories, default sessions, flow steps, scenario templates, business logic, and useful reference tables.
- Twilio templates and template requests live in `Modèles`.
- Automatic absence transfer is out of V1 scope. Working hours may be shown as reference, but team members can manually log into a colleague's queue if needed.

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
- 19 coherent demo conversations (`SD-DEMO-4001` through `SD-DEMO-4019`).
- At least 10 conversations with WhatsApp window open.
- At least 10 conversations with WhatsApp window closed.
- A few conversations marked as resolved.
- Approved and pending WhatsApp templates.
- Demo WhatsApp templates for lead, setting, closer-will-sign, course-date, and out-of-hours sequences.
- Next actions across reply, setting call, follow-up, and closing call.

Seed data is idempotent and should not duplicate existing demo leads. Production should run with `SALES_COCKPIT_SEED_DEMO_DATA=false`, which keeps users/rules/templates but removes `SD-DEMO-*` conversations.

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

This build spec is now a reference snapshot, not the live operational runbook. Current state and next steps are in `docs/CURRENT_STATE.md` and `docs/NEXT_SESSION.md`.

Current priority areas:

1. Validate the fresh live SchoolDrive path in staging: website form, SchoolDrive snapshot, automatic WhatsApp, AR-sent snapshot, Setter II follow-up.
2. Keep Twilio production read-only/mock until explicit cutover.
3. Clean or rebuild staging data if the historical SchoolDrive replay makes validation unreadable.
4. Run focused scenario validation with Laura/François.
5. Only then decide on production cutover.
