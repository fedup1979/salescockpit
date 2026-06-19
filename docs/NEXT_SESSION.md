# Next Session Handoff

## Current State

Sales Cockpit is a runnable staging prototype.

Local URLs:

- Streamlit UI: `http://localhost:8501`
- FastAPI health: `http://127.0.0.1:8000/health`

DigitalOcean staging:

- Staging UI: `http://139.59.158.77:8502`
- SchoolDrive staging webhook: `http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription`
- Twilio staging inbound webhook: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/inbound`
- Twilio staging status callback: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/status`
- Host: `salescockpit-prod-01`
- Services: `sales-cockpit-ui@staging.service`, `sales-cockpit-api@staging.service`

The app has been iteratively reviewed by François and is currently in a good staging prototype state.

## Important Recent Decisions

- The action is now explicitly validated as the central operational unit of the system.
- A conversation with `open` status must always have one open next action.
- The exhaustive validated business logic is now in `docs/BUSINESS_LOGIC.md`.
- The implementation gap analysis is now in `docs/GAP_ANALYSIS.md`.
- The validated workflow model is documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`; read it before changing `Tâches`, actions, follow-ups, calls, templates, qualification, or automation.
- Admin now includes a `Workflow` tab showing main action types, support actions, action statuses, and the transition table.
- The main V1 action chain is `reply`, `follow_up`, `setting_call`, `closing_call`.
- Qualification, manual notes, and template creation are support actions/proofs by default, not main workflow actions.
- `setting_call` is the preferred internal term. The UI should say `Appel`, for example `Appel setting` and `Appel closing`, not `Entretien`.
- Persisted action statuses should be `planned`, `open`, `in_progress`, `done`, `cancelled`, `blocked`; `due` should be calculated from `due_at`, not stored as a status.
- The transition table is partially implemented in the local mock system: resolution/reopen guards, contact review, template requests, outbound message chaining, and call outcome chaining are now active.
- Inbox tabs are not WhatsApp API window tabs.
- Inbox and `Tâches` tabs are operational work queues:
  - `À traiter`
  - `En suspens`
  - `Terminées`
  - `Toutes`
- `follow_up` is an action type, shown as `Envoyer relance`, not a separate top-level Inbox queue.
- WhatsApp API window state remains a separate badge:
  - `Fenêtre ouverte`
  - `Fenêtre fermée`
- Users close a conversation with `Clore la conversation`; internally this stores `resolved` with a controlled reason.
- Users reactivate a conversation with `Réactiver`; internally this stores `open` and requires creating the next action.
- Closing or reactivating a conversation now requires a note. The note is inserted into the conversation thread as a yellow internal note.
- A terminated conversation must not allow WhatsApp sends, manual follow-up scheduling, manual action creation, or handoff to closer. The only normal way back is `Réactiver`, with note and next action.
- New inbound messages reopen resolved conversations automatically.
- New inbound messages create or update a setter `reply` next action.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- Resolving a conversation completes open actions for that lead.
- The old technical `tasks` table remains, but the UI should call these `actions` or `prochaines actions`.
- Business rules are centralized in `sales_cockpit/business_rules.py` and shown in Admin.
- `Température` is no longer shown in the UI. Keep the DB field for compatibility, but do not reintroduce it as a visible qualification field unless François explicitly asks.
- `sales_stage` is displayed as `Parcours` only in compact status chips. It must not appear as an editable field in `Statuts`.
- `Parcours` is operationally dangerous because it can force the next action. In V1 it is not user-editable; if a case is missing, add a real workflow path instead of restoring manual forçage.
- Updating qualification/contact status without changing `Parcours` must not replace the current next action. If `Parcours` is forced to `appointment_booked`, it creates a `setting_call`. If qualification changes to `will_sign` without that force, it creates a Tanjona follow-up.
- Private notes are always included in the future learning base; there is no checkbox in the UI.
- The global `Tâches` view filters by individual responsible people, not only by role.
- `Non pertinent` and `Ne plus contacter` are separate. `Non pertinent` is commercial qualification. `Ne plus contacter` is a separate contact status.
- If a `Ne plus contacter` prospect writes again, create a `contact_review` action for Setter 1. Do not create automatic follow-ups.
- While a prospect is `Ne plus contacter`, all WhatsApp sends are blocked, including free-form messages and templates. The user must complete the contact review and lift the status before replying.
- Missing templates create `template_requests` linked to the blocked follow-up action.
- Follow-up sequences and sequence steps are stored structurally in SQLite and displayed in Admin.
- Outbound WhatsApp messages close the active `reply` or `follow_up` action and create the next follow-up when applicable.
- `reply` and `follow_up` should not be manually marked as sent in the main Actions flow. The normal proof is the outbound WhatsApp message from the Conversation composer.
- The Conversation composer can capture the send-time outcome for a `reply`: no appointment, setting appointment booked, closing appointment booked, non pertinent, or ne plus contacter.
- The `reply` outcome labels must explain the next action clearly. If the prospect accepts an appointment, the user should choose `RDV setting fixé : créer un appel` or `RDV closing fixé : créer un appel` before sending the WhatsApp reply.
- The Actions tab is contextual: WhatsApp actions explain where to send, call actions collect result + mandatory note, blocked relances show template-request state, and the standard planner can create `reply`, `follow_up`, `setting_call`, or `closing_call`.
- `Actions avancées` should stay minimal. In V1 it only contains `Message fait hors cockpit`. Do not reintroduce generic manual action creation, manual handoff to closer, manual data correction, or conversation reopen there.
- Setting and closing calls can be completed with business outcomes that create the next action.
- Only admins can create, synchronize, or submit WhatsApp templates to Twilio.
- Non-admin users can search templates and create template requests only.
- Twilio templates are synchronized from the Twilio Content API through `sales_cockpit/services/twilio_content.py`.
- In `sandbox` or `live` mode, approved templates are sendable only if they have a real Twilio `twilio_content_sid`; `HX_MOCK` demo templates are excluded from the send list.
- Delivery statuses are shown in conversation messages with WhatsApp-style checks: sent, delivered, read, failed, or queued/sending.
- Front must remain read-only until an explicit import/cutover decision. The current Front work is only a read-only API client plus documentation for historical import.
- Lead-relative reminders follow `+72h, +72h, +72h, +7j, +7j, +30j, stop`.
- Course-date reminders win over lead-relative reminders. The losing lead-relative reminder is cancelled.
- Minimum outbound WhatsApp follow-up delay is 24h.
- Tanjona is currently seeded as `setter2@essr.ch`.
- The UI normalizes old `Setter 2` display names to `Tanjona` to handle stale local sessions or older seeded databases.
- Dropdown labels should be displayed in French while internal values remain English.
- Private notes remain yellow and align right like team messages.
- Action notes, call notes, closure notes, and reactivation notes also appear as yellow internal notes in the conversation thread. The Conversation tab has a checkbox to show or hide internal notes.
- Reply tools live below the conversation thread.
- SchoolDrive link appears next to the prospect name, opening in a new tab.
- SchoolDrive lead types use SD terms internally: `lead` and `presubscription`.
- Inbox conversation cards show `Lead` or `Préinscription` above the prospect name.
- For `lead`, the course line shows the SD course category short title, e.g. `APP`; for `presubscription`, it shows the SD course short name, e.g. `APP GE P26`.
- Checkpoint tag before the `Tâches` layout experiment: `checkpoint-before-a-faire-layout-2026-06-18-0829`.
- Navigation now opens on `Tâches`, then `Inbox`, `Modèles`, `Admin`.
- `Tâches` is being tested with the same split-screen pattern as Inbox: action/person list on the left, selected prospect detail on the right.
- In `Tâches`, every user defaults to their own assigned actions, including admins. They can still switch to another user or `Tous`, and that choice persists while navigating between pages.
- Mock seed creates at least one open task per active user so every responsible-person queue can be inspected.
- Inbound unanswered prospects show a restrained hot signal in Inbox and `Tâches`, sort above ordinary due actions, and the mock seed includes `Léa Martin` as a waiting-reply example.
- Inbox and `Tâches` auto-refresh every 10 seconds while visible.
- The right-side detail tabs use the same order in `Tâches` and Inbox: `Conversation`, `Actions`, `Statuts`, `Notes privées`.
- Inbox and `Tâches` use `Toutes` for the all-items tab.
- Left split-screen cards use `Voir`, not `Ouvrir`.
- The `Prochaine action` card shows only the action type, due date/time, and responsible-person badge.
- Unknown WhatsApp prospects must display as `Inconnu(e)`, never `WhatsApp Unknown`.
- WhatsApp window text is explicit: `Ferme le ... à ...`, `Fermée le ... à ...`, or `Jamais ouverte` when no client reply has ever opened the window.
- Streamlit developer toolbar options are hidden with `client.toolbarMode = "viewer"` in `.streamlit/config.toml` to avoid exposing the `Clear caches` command in the UI.
- Demo data is versioned with `DEMO_SEED_VERSION` in `sales_cockpit/db.py`. The seed refreshes only `SD-DEMO-*` leads when the demo scenario version changes.
- Current coherent demo scenarios are `SD-DEMO-4001` through `SD-DEMO-4019`; see `docs/TEST_PLAN.md`.
- Before a clean manual validation pass, run `.\.venv\Scripts\python.exe scripts\reset_demo.py` to reset those demo scenarios.
- Manual validation checklist is in `docs/TEST_PLAN.md`.
- Navigation now includes `Mode d'emploi`; non-admin users no longer see the `Admin` page.
- Sidebar includes a `Bug` button. It opens a large dialog, creates a row in `bug_reports`, and logs the event in `user_activity_log`.
- Business events inserted via `lead_events` are mirrored into `user_activity_log`, so Admin can inspect recent usage and cross-check bug reports with workflow events.
- Admin now has a `Bugs & logs` tab showing bug reports and recent activity.
- Admin > Utilisateurs sorts users by ID, so Laura appears first in the seeded local data.
- Admin shows page access by role. Admin sees everything; Setter 1, Tanjona and Closer see all user pages except Admin.
- Human and business hours have provisional V1 values in Admin > Règles métier > Horaires et bascules. They still need Laura validation.
- The `Mode d'emploi` page is now prose, not expanders. Do not reintroduce accordion-heavy help unless François asks.
- Obsolete legacy demo blocks and the old `_render_next_action_box_legacy` function were removed.

## Current Validation

Latest known validation:

- `pytest`: 65 tests passing.
- `compileall`: passed for `sales_cockpit`, `scripts`, and `tests`.
- SchoolDrive staging API probe passed with a synthetic create + archive payload.
- Twilio staging template sync passed and imported 5 DEV templates, all currently `draft`.
- `scripts/reset_demo.py`: verified on a temporary SQLite database and creates 19 `SD-DEMO-*` leads.
- Streamlit AppTest smoke covers reply-action guidance and absence of the generic `Terminer l'action` button in the main Actions flow.
- Pytest uses an isolated temporary SQLite database via `tests/conftest.py`; it should not create test leads in the local app database.
- Streamlit smoke tests passed during the session.
- Streamlit and FastAPI were restarted after a stale import issue.

If a future session sees an import error for a recently added function, restart Streamlit. Streamlit can keep old modules in memory.

## Stale Process Note

During development, a stale Streamlit process caused:

`ImportError: cannot import name 'set_conversation_status' from 'sales_cockpit.store'`

The function existed in the file and imported correctly in a fresh Python process. Restarting Streamlit fixed it.

Useful commands:

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(8000,8501) }
```

Stop a process:

```powershell
Stop-Process -Id <PID> -Force
```

## Known Gaps

- SchoolDrive snapshot webhook exists; real staging payload validation is still pending.
- SchoolDrive URL format is provided by Tiago's webhook contract and should be checked during the first staging replay.
- Notion connector is placeholder only.
- Twilio is mock by default locally. Staging is configured in sandbox mode and real inbound/outbound WhatsApp has been tested.
- Twilio Content API synchronization exists. Real template approval and closed-window template sending still need an end-to-end staging validation with an approved Twilio template.
- Front import is not connected. The read-only client exists, but persistence, UI filtering, and a pilot import command still need to be built after we have a Front token and inbox IDs.
- Attachments UI exists but persistence/send is not implemented.
- Auth is local password-based only.
- GitHub remote exists: `https://github.com/fedup1979/salescockpit`.
- DigitalOcean staging exists on `http://139.59.158.77:8502`.
- Deployment scaffold exists in `deploy/` and `docs/DEPLOYMENT.md`.
- The droplet has a read-only GitHub deploy key for pull-based deploys.
- SchoolDrive webhook implementation exists. Read `docs/SCHOOLDRIVE_WEBHOOK.md` before changing it.
- No backup strategy implemented yet.

## Recommended Next Work

1. Run the focused manual scenario validation in `docs/TEST_PLAN.md`, starting with `scripts/reset_demo.py`.
2. Fix any UX or workflow failures discovered by the scenario pass.
3. After scenario behavior is validated, do a moderate refactor of the largest files without changing behavior.
4. Send Tiago the SchoolDrive staging webhook URL and token.
5. Validate real SchoolDrive staging payloads and backfill replay.
6. Implement Notion historical enrichment.
7. Validate Twilio template synchronization, creation, approval status, and closed-window sending on staging.
8. Build and test a small Front historical import pilot after Front credentials are available.

## Files Most Likely to Change Next

- `sales_cockpit/ui/app.py`
- `sales_cockpit/ui/styles.py`
- `sales_cockpit/store.py`
- `sales_cockpit/db.py`
- `sales_cockpit/services/schooldrive.py`
- `sales_cockpit/services/notion.py`
- `sales_cockpit/services/twilio_client.py`
- `sales_cockpit/services/twilio_content.py`
- `sales_cockpit/services/front_client.py`
- `docs/TWILIO_SANDBOX.md`
- `docs/FRONT_IMPORT.md`
- `tests/test_store.py`
