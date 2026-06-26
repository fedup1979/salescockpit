# Next Session Handoff

## Current State

Read `docs/CURRENT_STATE.md` first. It contains the current production-readiness state, the exact SchoolDrive AR-sent blocker, and the next operational decisions.

Also read `docs/ADVERSARIAL_REVIEW.md` before making cutover decisions. It records the latest adversarial review findings; several listed corrections have since been implemented locally, but they still need staging/prod deployment and validation.

Sales Cockpit is a runnable staging prototype.

Local URLs:

- Streamlit UI: `http://localhost:8501`
- FastAPI health: `http://127.0.0.1:8000/health`

DigitalOcean staging:

- PROD UI: `http://139.59.158.77:8501`
- PROD API health: `http://139.59.158.77:8601/health`
- Staging UI: `http://139.59.158.77:8502`
- SchoolDrive staging webhook: `http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription`
- Twilio staging inbound webhook: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/inbound`
- Twilio staging status callback: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/status`
- Host: `salescockpit-prod-01`
- Services: `sales-cockpit-ui@prod.service`, `sales-cockpit-api@prod.service`, `sales-cockpit-ui@staging.service`, `sales-cockpit-api@staging.service`

PROD is prepared cold on `8501` / `8601` with its own database and `SALES_COCKPIT_TWILIO_MODE=mock`. It is not connected to production SchoolDrive, production Front import, or real ESSR WhatsApp traffic. The V1 pre-cutover hardening was deployed to staging only.

The app has been iteratively reviewed by François and is currently in a good staging prototype state.

## Current Operational Gate

Sales Cockpit is ready for the SchoolDrive payloads it receives. Tiago later reported that the SchoolDrive projector was published and filtered to skip leads/subscriptions created before `2026-03-01`, but the live website-form path still needs one clean validation after the SchoolDrive WhatsApp/projector worker is confirmed running.

François has sent Tiago the schema `1.1` confirmation email. We are waiting for Tiago's response/publication on staging; continue internal QA while waiting.

Validate this exact path before claiming operational production readiness:

```text
Website form
-> SchoolDrive creates Lead or Presubscription
-> SchoolDrive sends automatic WhatsApp AR
-> AR reaches sent
-> SchoolDrive emits a newer webhook snapshot
-> Sales Cockpit updates the thread
-> Setter II follow-up is created at sent_at + 72h
-> pre_cutover_check stays green
```

Historical note: `lead:124126` previously proved that Cockpit handled a queued snapshot correctly but did not receive a newer AR-sent snapshot. That old diagnostic is no longer the main blocker if the newly published projector now emits fresh AR-sent snapshots.

## Important Recent Decisions

- Latest local hardening validation: `214 passed` with `.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp\schooldrive-review-conflict-full`, plus `compileall` OK after the SchoolDrive schema `1.1` update and human-review/follow-up conflict fix.
- Latest staging deployment: commit `3c7070e`, deployed from `main`. API/UI OK and `scripts/pre_cutover_check.py --api-base http://127.0.0.1:8602 --ui-url http://127.0.0.1:8502 --allow-cold-prod` OK.
- Latest staging template mapping check after deployment: `81` mappings total, `78` active, `78` active mappings linked to approved real Twilio templates; active split `APP=26`, `AS=26`, `FSM=26`. Existing real Twilio mappings were preserved.
- Active SchoolDrive human reviews caused by `unconfigured_course_category`, `schooldrive_course_full`, or `schooldrive_related_subscription_signed` now block automatic follow-ups until review resolution; startup normalization cancels pre-existing conflicting follow-ups.
- Status / qualification / reactivation saves were hardened: terminal qualifications and contact statuses now keep `Parcours`, conversation status, and next action aligned. `init_db()` also normalizes existing impossible terminal combinations, such as signed leads not shown as `won`, `Ne plus contacter` leads not shown as `blacklist`, and sequence-completed conversations not shown as `lost`.
- Use `--basetemp=.pytest-tmp\run` on Windows if Pytest fails after successful test execution because it cannot clean `pytest-current` in `%TEMP%`.
- Workflow reconciliation after the latest review: a terminal qualification or `Ne plus contacter` can no longer silently coexist with ordinary commercial sends/actions; inbound on those states creates a human review; manually lifting `Ne plus contacter` closes the stale review and recreates `reply` only if the last inbound is unanswered; template requests/admin actions linked to obsolete follow-ups are cancelled.
- The action is now explicitly validated as the central operational unit of the system.
- Canonical model: `Parcours` = commercial state, `Flux` = configurable follow-up scenario, `Action` = operational work item.
- A conversation with `open` status must normally have one open next action.
- Exception: if a prospect writes while a setting/closing call is already planned, the conversation can temporarily have both an urgent `reply` and the planned call. The reply must not cancel the call.
- The exhaustive validated business logic is now in `docs/BUSINESS_LOGIC.md`.
- The implementation gap analysis is now in `docs/GAP_ANALYSIS.md`.
- The validated workflow model is documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`; read it before changing `Tâches`, actions, follow-ups, calls, templates, qualification, or automation.
- `Pilotage > Logique métier` shows the business validation matrix, useful reference tables, operating rules, and the technical transition table.
- The main V1 action chain is `reply`, `follow_up`, `setting_call`, `closing_call`.
- `setting_call` and `closing_call` are now the future action to call the prospect and document the call at the appointment time. In UI copy, prefer `Appeler et documenter appel setting` and `Appeler et documenter appel closing`.
- Template requests create `admin_actions`. Admin users now see open admin actions from the `Tâches` page as well as `Admin > Actions admin`.
- A template request can be linked manually to a synced Twilio template from `Modèles`; approving a linked, real approved Twilio template unblocks the related Setter II follow-up.
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
- `sales_stage` is displayed as `Parcours` only in compact status chips. It must not be editable from the UI.
- `Parcours` is operationally dangerous because it can force the next action. In V1 it is not user-editable; if a case is missing, add a real workflow path instead of restoring manual forçage.
- Updating qualification/contact status without changing `Parcours` must not replace the current next action. If `Parcours` is forced to `appointment_booked`, it creates a `setting_call`. If qualification changes to `will_sign` without that force, it creates a Setter II follow-up.
- Notes internes are always included in the future learning base; there is no checkbox in the UI.
- The global `Tâches` view filters by individual responsible people, not only by role.
- `Non pertinent` and `Ne plus contacter` are separate. `Non pertinent` is commercial qualification. `Ne plus contacter` is a separate contact status.
- If a `Ne plus contacter` prospect writes again, create a `contact_review` action for Setter I. Do not create automatic follow-ups.
- While a prospect is `Ne plus contacter`, all WhatsApp sends are blocked, including free-form messages and templates. The user must complete the contact review and lift the status before replying.
- Missing templates create `template_requests` linked to the blocked follow-up action.
- Follow-up sequences and sequence steps are stored structurally in SQLite and displayed in Admin.
- Pilotage lets admins edit flux step delay/meaning/template-required/active state without code. Do not delete steps; deactivate them.
- Sequence step timing is now absolute from the flow trigger. Use `offset_direction`, `offset_amount`, and `offset_unit`; do not treat `delay` as a relative delay from the previous step.
- For lead-relative fluxes, `T` is the event that opened the flux, for example first SchoolDrive WhatsApp sent, reply sent with no appointment, call ended undecided, or closing marked will sign.
- For course-start flows, `T` is the course start date, so steps are usually before the trigger.
- Relance WhatsApp steps are `action_type='follow_up'` and must have a recommended approved real Twilio template for each operational category.
- Manual reprise steps are explicit action types: `manual_reprise_setter` for Setter I and `manual_reprise_closer` for the closer. They require a note and continue the flux if a next active step exists.
- `post_setting_undecided` is now a Setter I manual reprise by default. `post_closing_undecided` is now a closer manual reprise by default.
- If a prospect is `will_sign`, a simple reply without appointment must keep the follow-up context in `closer_will_sign`; it must not fall back to `setter_no_next_step`.
- A sequence step can be skipped with mandatory note. Skipping means only "do not do this step"; the system advances to the next active step or resolves the sequence if none exists.
- Pilotage lets admins assign approved real Twilio templates by flow, step, lead type and course category.
- Pilotage > Logique métier includes a full business validation matrix from `PILOTAGE_VALIDATION_CASES` in `sales_cockpit/business_rules.py`: starting state, event, system response, user action, action resolution, and next action. Keep this matrix aligned with `WORKFLOW_TRANSITIONS` whenever workflow logic changes.
- Template mappings must only use real Twilio templates approved by WhatsApp. Draft, pending, rejected, local demo, and `HX_MOCK_*` templates are deliberately ignored/rejected for operational recommendations.
- Initial template premapping exists in `scripts/premap_sequence_templates.py`. It maps the approved ESSR Twilio templates to every required `follow_up` step for `FSM`, `APP`, and `AS` using `lead_type = all`. It was applied to staging and prod on 2026-06-20 with 75 mappings total, 25 per category. Treat it as an AI-generated first pass to validate with Laura, not as final commercial truth.
- `scripts/premap_sequence_templates.py --dry-run` is safe and should be used before reapplying. The script is idempotent and uses the existing `upsert_sequence_template_mapping` guardrails, so it only accepts active `follow_up` steps and approved real Twilio templates.
- Structured course categories live in `course_categories`. V1 seeds `FSM`, `APP`, and `AS`. Unsupported SchoolDrive categories are stored, displayed, and routed to a Setter I review task instead of receiving an automated Setter II relance flux.
- V1 step/template changes affect only newly created future sequences. Existing open tasks are not recalculated.
- Outbound WhatsApp messages close the active `reply` or `follow_up` action and create the next follow-up when applicable.
- If a `reply` is sent while a setting/closing call is already planned, the reply closes and the planned call remains the next action.
- `reply` and `follow_up` should not be manually marked as sent in the main Actions flow. The normal proof is the outbound WhatsApp message from the Conversation composer.
- The Conversation composer must not capture the next commercial action for a `reply`. It sends messages, approved templates, and template requests only.
- If the prospect accepts an appointment after a reply, the user sends the WhatsApp message first, then creates the setting or closing call from the stable Actions block.
- The Actions tab is now stable: status banner and fixed standard block. Action/event history lives in `Journal`. `reply` and `follow_up` explain that the work is done from `Conversation`; the standard block can schedule/modify calls, request/document manual reprises, document due calls, and skip eligible flow steps.
- V1 no longer exposes `Actions avancées`. `reply` and `follow_up` must be resolved through the Conversation composer so there is a real outbound-message proof. Do not reintroduce generic manual action creation, off-cockpit message completion, manual handoff to closer, manual data correction, or conversation reopen there.
- Setting and closing calls can be completed with business outcomes that create the next action.
- No-show retries are counted per appointment cycle through `tasks.call_cycle_id` and `tasks.call_attempt_index`. A new setting/closing appointment starts a new cycle, so old no-shows do not make the system skip to the wrong retry.
- Business-rule seed data is versioned in `app_metadata.business_rules_version`. When the version changes, canonical sequence steps are migrated and legacy active `post_call_undecided` steps are deactivated.
- Template requests can be unblocked by Twilio sync if a real approved template is linked or if the exact template name/SID appears in the request reason/context.
- Outbound WhatsApp sends now create a pending local message before calling Twilio; if Twilio fails, the message remains in the thread with `twilio_status='send_error'`.
- Follow-up quotas apply to relances, not to urgent human replies. The global kill switch and `do_not_contact` still block all sends.
- SchoolDrive signals now handled: signed, do-not-contact/opt-outs, course/session full, stale default session date.
- Course/session-full handling depends on the latest SchoolDrive webhook. There is not yet a live pre-send capacity check before course-start follow-ups; this is tracked in `docs/TECHNICAL_DEBT.md`.
- `scripts/pre_cutover_check.py --strict-prod` is the mandatory final gate before routing real production WhatsApp traffic to Sales Cockpit.
- Only admins can create, synchronize, or submit WhatsApp templates to Twilio.
- Non-admin users can search templates and create template requests only.
- Twilio templates are synchronized from the Twilio Content API through `sales_cockpit/services/twilio_content.py`.
- In `sandbox` or `live` mode, approved templates are sendable only if they have a real Twilio `twilio_content_sid`; `HX_MOCK` demo templates are excluded from the send list.
- The Modèles page labels real Content API templates as `Twilio`; demo templates remain separate.
- ESSR production WhatsApp sender migration is documented in `docs/TWILIO_SENDER_MIGRATION.md`; do not assume buying a new Twilio number validates the ESSR sender.
- Delivery statuses are shown in conversation messages with WhatsApp-style checks: sent, delivered, read, failed, or queued/sending.
- Front must remain read-only until an explicit import/cutover decision. The current Front work is a read-only API client, dry-run script, retry handling, and documentation for historical import.
- Inbound WhatsApp identity matching is conservative by design:
  - one phone match attaches automatically;
  - zero phone match creates a temporary `À identifier` record;
  - multiple phone matches create a temporary `À identifier` record with candidate leads stored for review.
- Qualification and contact status are edited from the icon next to the compact status chips. The note is optional.
- V2 debt for identity resolution and merging temporary records is documented in `docs/TECHNICAL_DEBT.md`.
- Front dry-run pagination now respects the requested `limit` before following next-page cursors. This was fixed after a supposedly tiny `limit=1` dry-run kept running too long.
- Front historical import now has a safe pilot foundation:
  - `front_conversations` and `front_messages` buffer tables;
  - phone extraction and exact phone matching;
  - `scripts/front_import_pilot.py`;
  - migration classification into `active`, `resolved`, or `manual_review`;
  - filtered Admin > Intégrations review by match status, migration status, and recommended action;
  - read-only cutover planning via `scripts/front_cutover_plan.py`;
  - buffer rematching via `scripts/front_rematch_buffer.py` after SchoolDrive backfill;
  - dry-run-first conversion via `scripts/front_convert_matched.py` for matched active Front rows;
  - optional `--attach-history` to copy matched messages into the thread as `front_history`, disabled by default;
  - Admin > Intégrations displays buffered Front records.
- SchoolDrive payload replay tool exists: `scripts/schooldrive_replay_payloads.py`.
- SchoolDrive synthetic smoke test exists: `scripts/schooldrive_smoke.py`. It can validate staging without real Tiago payloads and checks created/updated/ignored/duplicate/archive behavior.
- Real SchoolDrive MCP replay into staging validated the timestamp convention on 2026-06-19: naive MCP timestamps are UTC, not Europe/Zurich local time. Keep current UTC values and do not subtract two hours.
- Pre-cutover CLI check exists: `scripts/pre_cutover_check.py`.
- Twilio template audit CLI exists: `scripts/twilio_template_audit.py`.
- Production cutover runbook exists: `docs/CUTOVER_RUNBOOK.md`.
- Lead-relative reminders are absolute from the flow trigger: `T+72h, T+144h, T+216h, T+16j, T+23j, T+53j, stop`.
- Course-date reminders win over lead-relative reminders when they conflict, but must not interrupt a planned setting/closing call.
- Minimum outbound WhatsApp follow-up delay is 24h.
- Tanjona is currently seeded as `setter2@essr.ch`.
- The UI normalizes old `Setter 2` display names to `Tanjona` to handle stale local sessions or older seeded databases.
- Dropdown labels should be displayed in French while internal values remain English.
- Notes internes remain yellow and align right like team messages.
- Action notes, call notes, closure notes, and reactivation notes also appear as yellow internal notes in the conversation thread. The Conversation tab has a checkbox to show or hide internal notes.
- Reply tools live below the conversation thread.
- SchoolDrive link appears next to the prospect name, opening in a new tab.
- SchoolDrive lead types use SD terms internally: `lead` and `presubscription`.
- SchoolDrive `schooldrive_id` prefixes are now `lead:<id>` and `subscription:<id>` for real webhook payloads. Older `presub:<id>` is still tolerated only in the fallback URL helper.
- SchoolDrive WhatsApp autoresponders accept real fields from Tiago's payload: `short_name`, `whatsapp_template_id`, `whatsapp_template_variables_mapping`, and `whatsapp_send_body`.
- If `whatsapp_send_body` is present on a sent SchoolDrive autoresponder, the conversation thread displays that exact body, not a generic placeholder.
- Inbox conversation cards show `Lead` or `Préinscription` above the prospect name.
- For `lead`, the course line shows the SD course category short title, e.g. `APP`; for `presubscription`, it shows the SD course short name, e.g. `APP GE P26`.
- Checkpoint tag before the `Tâches` layout experiment: `checkpoint-before-a-faire-layout-2026-06-18-0829`.
- Navigation now opens on `Tâches`, then `Inbox`, `Modèles`, `Admin`.
- `Tâches` is being tested with the same split-screen pattern as Inbox: action/person list on the left, selected prospect detail on the right.
- In `Tâches`, every user defaults to their own assigned actions, including admins. They can still switch to another user or `Tous`, and that choice persists while navigating between pages.
- Mock seed creates at least one open task per active user so every responsible-person queue can be inspected.
- Inbound unanswered prospects show a restrained hot signal in Inbox and `Tâches`, sort above ordinary due actions, and the mock seed includes `Léa Martin` as a waiting-reply example.
- Inbox and `Tâches` auto-refresh every 10 seconds while visible.
- The right-side detail tabs use the same order in `Tâches` and Inbox: `Conversation`, `Actions`, `Notes internes`.
- Inbox and `Tâches` use `Toutes` for the all-items tab.
- Left split-screen cards use `Voir`, not `Ouvrir`.
- The `Prochaine action` card shows only the action type, due date/time, and responsible-person badge.
- Unknown WhatsApp prospects must display as `Inconnu(e)`, never `WhatsApp Unknown`.
- WhatsApp window text is explicit: `Ferme le ... à ...`, `Fermée le ... à ...`, or `Jamais ouverte` when no client reply has ever opened the window.
- Streamlit developer toolbar options are hidden with `client.toolbarMode = "viewer"` in `.streamlit/config.toml` to avoid exposing the `Clear caches` command in the UI.
- Demo data is versioned with `DEMO_SEED_VERSION` in `sales_cockpit/db.py`. The seed refreshes only `SD-DEMO-*` leads when the demo scenario version changes.
- Current coherent demo scenarios are `SD-DEMO-4001` through `SD-DEMO-4025`; see `docs/TEST_PLAN.md`.
- Before a clean manual validation pass, run `.\.venv\Scripts\python.exe scripts\reset_demo.py` to reset those demo scenarios.
- Manual validation checklist is in `docs/TEST_PLAN.md`.
- Navigation now includes `Mode d'emploi`; non-admin users no longer see the `Admin` page.
- Sidebar includes a `Bug` button. It opens a large dialog, creates a row in `bug_reports`, and logs the event in `user_activity_log`.
- Business events inserted via `lead_events` are mirrored into `user_activity_log` for backend audit/debug, but the admin activity log is no longer shown in the UI.
- Admin now has a `Signalements` tab showing bug reports. The old admin activity log is no longer shown.
- Admin now opens with an `État` tab showing readiness for SchoolDrive, Front, Twilio, backups, and workflow consistency.
- Admin > Utilisateurs sorts users by ID, so Laura appears first in the seeded local data.
- Admin shows page access by role. Admin sees everything; Setter I, Setter II and Closer see all user pages except Admin.
- Human and business hours are shown in `Pilotage > Logique métier`. Automatic absence transfers are intentionally out of V1 scope.
- The `Mode d'emploi` page is now prose, not expanders. Do not reintroduce accordion-heavy help unless François asks.
- In `Mode d'emploi` and `Pilotage`, use function labels (`Setter I`, `Setter II`, `Closer`, `Admin`) rather than person names. Person names are still appropriate when showing the actual assignee on a task or in user management.
- Template requests and bug reports create `admin_actions`, not standard prospect tasks. Do not create fake commercial tasks for them. Keep admin support work in `Admin > Actions admin`.
- Obsolete legacy demo blocks and the old `_render_next_action_box_legacy` function were removed.

## Current Validation

Latest known local validation after the V1 pre-cutover hardening:

- `pytest` with local temp directory: 205 tests passing.
- `compileall`: passed for `sales_cockpit`.
- `git diff --check`: passed.
- BOM scan: clean for tracked/project files.
- Staging deploy source: `main` branch via `deploy/scripts/deploy_env.sh`.
- Latest verified staging commit: verify on the server with `git -C /opt/sales-cockpit/staging/app rev-parse --short HEAD`.
- Latest observed cold production commit: `786f89c`; production was not redeployed in this pass.
- Staging `pre_cutover_check` passed after deployment.
- Production `pre_cutover_check --allow-cold-prod` passed after deployment; Twilio remains `mock`, seed demo is false, and SchoolDrive/Front are intentionally not connected there yet.
- Restore points live in `/opt/sales-cockpit/backups/staging/`.
- Staging API/UI health passed after deploy.
- Staging `pre_cutover_check` passed after deploy:
  - SchoolDrive ready;
  - Front ready;
  - Twilio ready in `mock` mode;
  - Backup ready;
  - Workflow ready;
  - `open_conversations_without_action = 0`;
  - `resolved_conversations_with_action_count = 0`;
  - `conversations_with_multiple_main_actions = 0`.
- New automated coverage confirms:
  - inbound during a planned setting call creates an urgent reply and preserves the planned call;
  - replying without changing the appointment returns the planned call as next action;
  - course-start relance can replace a nearby lead-relative relance;
  - course-start relance does not interrupt a planned setting call.
- SchoolDrive staging API probe passed with a synthetic create + archive payload.
- SchoolDrive synthetic smoke passed on staging with run id `smoke-20260619T122027Z`: created, updated, stale ignored, duplicate ignored, sent WhatsApp, queued WhatsApp, archive, and DB side effects all OK.
- Real SchoolDrive MCP replay/backfill passed on staging. Current counters: 35 accepted SchoolDrive events, 2 ignored stale/duplicate-style events, and 30 SchoolDrive-backed leads in staging.
- Timestamp decision after the real MCP replay: `KEEP_CURRENT_UTC`. No cleanup, no replay, and no `-2h` conversion are required.
- Twilio staging template sync passed. Staging currently sees 10 real Twilio DEV templates: 4 `pending`, 6 `draft`, and 0 real approved templates.
- Test template `sc_dev_accuse_reception_fr_001` was created and submitted for WhatsApp approval; current status is `pending`.
- Staging is currently checked as Twilio `mock` mode after the 2026-06-20 workflow deploy. Do not assume live sending until the environment is explicitly inspected again.
- SQLite backup and restore have been tested successfully on staging with `deploy/scripts/backup_sqlite.sh` and `deploy/scripts/restore_sqlite.sh`.
- Automated backup cron is installed and cron service is active on the droplet.
- Front token is configured on staging. After fixing pagination limiting, a dry-run successfully read 1 Front conversation and 1 WhatsApp message with `writes: 0`.
- Front pilot staging result: 13 Front conversations and 159 Front messages stored in the buffer tables. After the latest SchoolDrive MCP backfill and rematch: 11 `unmatched`, 1 `ambiguous`, 1 `matched`.
- The matched Front row is `cnv_1mz0vz4w`, phone `+33669502201`, linked to `subscription:131887` / Lea Bucco. Front history attachment added 11 `front_history` messages. Conversion dry-run skipped it because a `follow_up` action already exists.
- Admin readiness on staging is green for SchoolDrive, Front, Twilio, Backup, and Workflow. The workflow count explicitly separates 1 SchoolDrive record waiting for the first sent autoresponder from true open conversations without action.
- Latest staging pre-cutover check passed with `scripts/pre_cutover_check.py --api-base http://127.0.0.1:8602 --ui-url http://127.0.0.1:8502`.
- `scripts/reset_demo.py`: verified on a temporary SQLite database and creates 25 `SD-DEMO-*` leads (`SD-DEMO-4001` through `SD-DEMO-4025`).
- Streamlit AppTest smoke covers reply-action guidance and absence of the generic `Terminer l'action` button in the main Actions flow.
- Pytest uses an isolated temporary SQLite database via `tests/conftest.py`; it should not create test leads in the local app database.
- Streamlit smoke tests passed during the session.
- Streamlit and FastAPI were restarted after a stale import issue.
- Latest backups created on the droplet:
  - staging: `/opt/sales-cockpit/backups/staging/sales_cockpit_staging_20260620T152700Z.db.gz`
  - prod: `/opt/sales-cockpit/backups/prod/sales_cockpit_prod_20260619T124345Z.db.gz`

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

- 2026-06-22 08:43 Europe/Zurich: staging was cleaned after an excessive SchoolDrive projector backfill. Backup before cleanup:
  `/opt/sales-cockpit/backups/staging/sales_cockpit_staging_before_cleanup_20260622_0820.db`
  with SHA-256 `68243dee0a2fc1949b09f24fb42a7a555ceff4967bbc16ce6b1ad37b20d58ac6`.
- SchoolDrive snapshot webhook exists; synthetic smoke, real replay, duplicate/stale handling, real payload-shape validation, and a live post-cleanup staging event have passed. The remaining gate is a fresh website-form lead plus presubscription path through AR `sent` snapshot with course/category data validated in the UI.
- Staging has `SALES_COCKPIT_SCHOOLDRIVE_INGEST_MIN_SENT_AT=2026-06-22T00:00:00Z` to prevent historical sent WhatsApp records from becoming operational conversations during final testing.
- New SchoolDrive records without usable identity, without a WhatsApp autoresponder, or with sent autoresponders older than the configured cutoff are acknowledged and logged as ignored. Queued/sending/moderation-pending records with identity are kept as waiting records.
- After cleanup, staging `pre_cutover_check` passed on commit `e388ed1`, database size was about 0.7 MB, with no foreign-key violations. A live post-cleanup presubscription `subscription:131968` was accepted with AR `armsg:1021237` (`sent`) and routed to a human review action because the SchoolDrive payload had no course category.
- The cleanup script is `scripts/cleanup_schooldrive_staging.py`. It is dry-run by default and now refuses `prod` / `production` even if the deprecated `--allow-production` flag is supplied. It exists for staging cleanup only.
- If many SchoolDrive records reappear in staging, first check whether they have `ignored_reason` values. A high ignored-event count is acceptable; high `leads.source='schooldrive_webhook'` count is not.
- SchoolDrive fixed the missing course/category payload issue and now sends a nested `course` structure, or a `product` structure for Roadmap leads. Sales Cockpit supports this locally and has tests for Nutrition subscription, FSM lead with linked subscription, FSM lead without linked subscription, and Roadmap product lead. The remaining validation is a fresh live staging event using this new shape.
- SchoolDrive URL format is provided by Tiago's webhook contract and should be checked during the first staging replay.
- Notion connector is placeholder only.
- Twilio is mock by default locally. Staging was previously tested with Sandbox and then with the DEV sender `+41445054269`, but the DEV WhatsApp account was later blocked by Meta. Do not assume staging can send live WhatsApp. Current safe posture is `mock` for staging and production until explicit cutover.
- Twilio Content API synchronization exists. Real template approval and closed-window template sending still need an end-to-end staging validation with an approved Twilio template.
- Front import is partially connected in safe pilot mode. Read-only client, dry-run, buffer persistence, exact phone matching, buffer rematch, dry-run-first matched conversion, and Admin visibility exist. Full historical import, ambiguous matching review, and conversation-level history filtering are still pending.
- WhatsApp freeform attachments are available in V1 while the WhatsApp 24-hour window is open. Files are stored in `storage/attachments`, linked through the `attachments` table, and sent to Twilio via `/media/attachments/{id}/{token_name}`. In non-mock Twilio modes, `SALES_COCKPIT_PUBLIC_API_BASE_URL` or a derivable `SALES_COCKPIT_TWILIO_WEBHOOK_URL` origin must be configured so Twilio can fetch the media.
- API endpoints for app-style reads/writes require `SALES_COCKPIT_API_TOKEN` outside local tests. JSON mock inbound webhooks also require `SALES_COCKPIT_MOCK_WEBHOOK_TOKEN` or the API token outside local tests.
- Production should use `SALES_COCKPIT_SEED_DEMO_DATA=false`; this keeps users, rules, and templates, but removes local `SD-DEMO-*` conversations.
- Auth is local password-based only.
- GitHub remote exists: `https://github.com/fedup1979/salescockpit`.
- DigitalOcean staging exists on `http://139.59.158.77:8502`.
- DigitalOcean PROD exists on `http://139.59.158.77:8501`, prepared cold with Twilio mock mode and isolated data.
- Deployment scaffold exists in `deploy/` and `docs/DEPLOYMENT.md`.
- The droplet has a read-only GitHub deploy key for pull-based deploys.
- The GitHub deploy key is on the `salescockpit` Linux user. Deployment scripts must run Git and Python app setup as `salescockpit`, then restart services as `root`.
- SchoolDrive webhook implementation exists. Read `docs/SCHOOLDRIVE_WEBHOOK.md` before changing it.
- SQLite backup/restore scripts exist. Read `docs/BACKUP_RESTORE.md` before using restore.
- Automated backup cron is installed on the droplet in `/etc/cron.d/sales-cockpit-backups`.
- Backup cron schedule, UTC:
  - staging daily at `01:17`, 14-day retention;
  - prod daily at `01:37`, 30-day retention.

## Recommended Next Work

1. Use the real SchoolDrive MCP replay results as the current staging baseline. Do not apply a timezone correction to those records.
2. When Tiago's producer sends live webhook events, validate accepted/ignored/duplicate events, sent vs queued WhatsApp messages, Setter II +72h creation, and archive resolution in staging.
3. If Tiago sends JSON files instead of POSTing directly, use `scripts/schooldrive_replay_payloads.py` with `--expected-environment staging`.
4. If Tiago is still pending after a deployment, run `scripts/schooldrive_smoke.py` from the droplet with `--db-check` to validate the webhook with synthetic data.
5. After Claude/MCP backfills more SchoolDrive leads, run `scripts/front_rematch_buffer.py --limit 500`, then review `scripts/front_convert_matched.py --limit 500` dry-run output. Do not execute conversion for rows with existing actions unless replacement is intentional.
6. Watch Twilio template approval status. Closed-window template sending cannot be validated until at least one real template is approved.
7. Run the focused manual scenario validation in `docs/TEST_PLAN.md` with Laura or François after real SchoolDrive data is visible.
8. Fix any UX or workflow failures discovered by the scenario pass.
9. After scenario behavior is validated, do a moderate refactor of the largest files without changing behavior.
10. Implement Notion historical enrichment.

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
- `docs/TWILIO_SENDER_MIGRATION.md`
- `docs/FRONT_IMPORT.md`
- `docs/BACKUP_RESTORE.md`
- `docs/CUTOVER_RUNBOOK.md`
- `docs/TECHNICAL_DEBT.md`
- `scripts/schooldrive_replay_payloads.py`
- `scripts/front_import_pilot.py`
- `tests/test_store.py`
