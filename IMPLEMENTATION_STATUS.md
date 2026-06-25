# Sales Cockpit Implementation Status

## Current Status

V1 staging build is runnable. Staging is deployed from the `main` branch; verify the exact server commit with `git -C /opt/sales-cockpit/staging/app rev-parse --short HEAD`. Production is deployed cold and remains in Twilio `mock` mode.

The current production gate is a fresh live SchoolDrive validation after the worker/projector is confirmed running: website form -> SchoolDrive lead/presubscription -> automatic WhatsApp AR -> AR sent snapshot -> Sales Cockpit thread + Tanjona follow-up.

Latest recorded staging deployment check:

- API health: OK.
- UI health: OK.
- `scripts/pre_cutover_check.py`: OK.
- Twilio mode on staging: `mock`.
- Workflow consistency: no active conversation without action, no resolved conversation with active action, no conflicting main actions.
- API security readiness checks app API tokens and mock webhook tokens outside local tests.
- Latest local hardening validation: `204 passed`, `compileall` OK. On Windows, run pytest with `--basetemp=.pytest-tmp\run` if `%TEMP%\pytest-current` cleanup raises a permission error after successful execution.
- Staging and cold production are both deployed on `db6f03b`; staging pre-cutover is OK, and production cold pre-cutover is OK with Twilio still in `mock` mode.

The canonical workflow model is now:

- `Parcours`: commercial state.
- `Flux`: configurable follow-up scenario and templates.
- `Action`: operational work item in the queue.

## Completed

- Product context.
- Design context.
- Project-level `AGENTS.md` for future Codex sessions.
- Self-contained build spec in `docs/BUILD_SPEC.md`.
- Handoff notes in `docs/NEXT_SESSION.md`.
- Local project structure.
- PRD reference exists in `C:\Users\FD\Desktop\MarketForge\marketforge-dev\docs\PRD_SALES_COCKPIT.md`.
- SQLite WAL persistence.
- Streamlit internal cockpit UI.
- FastAPI webhook-ready backend.
- Initial seeded users.
- Mock leads, conversations, messages, templates, and tasks.
- WhatsApp 24-hour window rule enforcement.
- Streamlit smoke test for login and inbox.
- French display labels for dropdowns.
- Operational conversation status separate from WhatsApp window state.
- Close or reactivate conversations in the UI while keeping internal `open` / `resolved` values.
- Inbound messages reopen resolved conversations.
- Work queue labels: `À traiter`, `En suspens`, `Terminées`, `Toutes`; follow-ups due now are included in `À traiter`.
- Next-action model on top of the existing `tasks` table.
- Inbound WhatsApp messages create/update a setter `reply` action.
- Follow-up scheduling and setter-to-closer handoff from the conversation detail.
- Global `Tâches` page with responsible-person and action filters.
- Formal business rules module in `sales_cockpit/business_rules.py`.
- Admin view for roles, qualifications, operating rules, follow-up sequences, lead types, and demo templates.
- Seeded Tanjona user: `setter2@essr.ch`.
- Demo WhatsApp templates for initial offer, 72h/7d/30d follow-ups, setting, will-sign, course-date, and out-of-hours.
- Stop statuses `Non pertinent`, `Ne plus contacter`, and `A signé` complete open actions and resolve conversations.
- Status / qualification / reactivation saves keep `Parcours`, contact status, conversation status, and next action coherent. Startup normalization repairs existing terminal inconsistencies in Sales Cockpit data.
- UI simplification: `Température` hidden, `sales_stage` displayed as `Parcours`, internal notes always included for future learning.
- Global `Tâches` filters responsibility by individual people, defaults to the connected user's own queue, and persists a manual responsible-person choice during navigation.
- SchoolDrive lead source types use `lead` and `presubscription`; inbox cards display `Lead` / `Préinscription` and use course category vs course short name accordingly.
- Experimental UX pass: `Tâches` is first in navigation and uses a split-screen action/person list with the selected prospect detail on the right.
- Mock seed ensures at least one open task for each active user for visual queue checks.
- Inbound unanswered prospects are highlighted with a restrained hot signal and sorted above ordinary due actions.
- `Tâches` and Inbox auto-refresh every 10 seconds while visible.
- Action workflow decisions documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`: action as operational unit, main vs support actions, statuses, proofs, outcomes, triggers, and transition table.
- Workflow concepts clarified and documented: `Parcours` is the commercial state, `Flux` is the configurable follow-up sequence, and `Action` is the concrete operational work item.
- Admin `Workflow` tab displays main action types, support actions, action statuses, and the transition table.
- Exhaustive business logic documented in `docs/BUSINESS_LOGIC.md`.
- Gap analysis documented in `docs/GAP_ANALYSIS.md`.
- Commercial qualification and contact status are separated in the data model.
- Manual resolution now requires a controlled reason, with note required for sensitive reasons.
- Manual reopening now requires creating the next action.
- Inbound message from a `Ne plus contacter` prospect creates a `contact_review` action for Setter 1.
- Follow-up sequences and sequence steps are stored structurally in SQLite and visible in Admin.
- Missing templates create `template_requests` linked to the blocked action.
- Outbound WhatsApp messages close the active `reply` or `follow_up` action and create the next follow-up when applicable.
- WhatsApp `reply` actions can now choose the business outcome at send time, so the sent message is the proof and the selected outcome creates the next action.
- The Actions tab is contextual by action type: WhatsApp actions guide users to the Conversation composer, calls use result + mandatory note, contact reviews show explicit do-not-contact decisions, and V1 no longer exposes generic advanced action completion.
- Setting/closing calls can be completed with business outcomes that create the next action.
- Setting/closing call actions now represent the future work of documenting the call at appointment time.
- Planned setting/closing calls are visible in the conversation detail.
- If a prospect writes while a setting/closing call is already planned, Sales Cockpit creates an urgent `reply` action without cancelling the planned call.
- If that reply is sent without changing the appointment, the planned call becomes the visible next action again and no Tanjona follow-up is created.
- Course-start relance creation now uses SchoolDrive `course.start_date` or the category default session date, can replace a conflicting lead/presubscription relance, and does not interrupt planned setting/closing calls.
- Workflow readiness now flags resolved conversations with active actions and open conversations with conflicting main actions, while allowing the intentional temporary `reply` + planned call exception.
- Added tests for resolution/reopen guards, do-not-contact inbound review, template requests, reply-to-follow-up chaining, send-time reply outcomes, call retry chaining, and Streamlit action guidance.
- Unknown WhatsApp prospects display as `Inconnu(e)` instead of `WhatsApp Unknown`.
- WhatsApp window labels now read `Ferme le ... à ...`, `Fermée le ... à ...`, or `Jamais ouverte`.
- Streamlit developer toolbar options are hidden with `client.toolbarMode = "viewer"` to avoid exposing the clear-cache command in the UI.
- Demo scenarios are versioned and rebuilt for `SD-DEMO-*` only, with coherent cases covering reply, follow-up, blocked template, setting call, closing call, do-not-contact review, terminal conversations, course-date reminders, and admin queues.
- Manual test plan added in `docs/TEST_PLAN.md`.
- Pytest now runs against an isolated temporary SQLite database, so tests do not pollute the local app database.
- Added `Mode d'emploi` page and persistent user guide in `docs/USER_GUIDE.md`.
- Replaced the `Mode d'emploi` expanders with a prose guide intended for first-time sales users.
- Added sidebar `Bug` reporting with `bug_reports` storage and `user_activity_log` entries.
- Replaced the sidebar Bug popover with a large Streamlit dialog to avoid viewport overflow.
- Business events are mirrored into `user_activity_log` for usage analysis.
- Added Admin `Bugs & logs` tab.
- Admin user table is sorted by ID. Page access by role is visible; non-admin users do not see the Admin page.
- Human and company schedule rules now include provisional V1 hours and backup rules, still to validate with Laura.
- Obsolete legacy demo scenario code and the old next-action renderer were removed.
- Added `scripts/reset_demo.py` to reset local demo scenarios before manual validation.
- Scenario-first manual validation path added to `docs/TEST_PLAN.md`.
- Added deployment scaffold for GitHub + DigitalOcean with PROD/STAGING/DEV Streamlit ports `8501` / `8502` / `8503`.
- Added systemd templates for Streamlit UI and FastAPI backend.
- Added per-environment `.env` examples and deployment notes in `docs/DEPLOYMENT.md`.
- GitHub repository created and pushed: `https://github.com/fedup1979/salescockpit`.
- DigitalOcean staging deployed on `http://139.59.158.77:8502`.
- Staging services running: `sales-cockpit-ui@staging.service` and `sales-cockpit-api@staging.service`.
- DigitalOcean PROD prepared cold on `http://139.59.158.77:8501`, with API on `8601`, isolated SQLite data, services running, and Twilio still in `mock` mode.
- Deployment script adjusted so Git pull, virtualenv setup, dependency install, and DB init run as the `salescockpit` Linux user that owns the GitHub deploy key.
- Implemented SchoolDrive snapshot webhook with bearer auth, environment guard, `event_id` idempotency, `schooldrive_id` upsert, `aggregated_updated_at` ordering, autoresponder replacement, and archival handling.
- SchoolDrive `url` is stored and used by the UI SchoolDrive link.
- Implemented Twilio sandbox-ready integration: SDK send client, inbound WhatsApp form webhook, `X-Twilio-Signature` validation, inbound idempotency by `MessageSid`, status callback storage, and legacy JSON mock compatibility.
- Twilio sandbox has been configured and tested on staging for inbound and outbound WhatsApp messages.
- Twilio delivery status is displayed in the conversation thread with WhatsApp-style checks.
- Added a Twilio real-send recipient allowlist for staging/live validation with a real DEV WhatsApp sender.
- Admin-only Twilio template synchronization is implemented through the Twilio Content API.
- Admin-only Twilio template creation and WhatsApp approval submission are implemented for text templates.
- Non-admin users can request missing templates but cannot create or synchronize Twilio templates.
- In sandbox/live mode, sendable approved templates exclude local `HX_MOCK` demo templates.
- SchoolDrive staging webhook was probed successfully with a synthetic create + archive payload.
- SchoolDrive webhook now supports Tiago's real payload shape: `subscription:<id>`, `short_name`, `whatsapp_template_id`, `whatsapp_template_variables_mapping`, and `whatsapp_send_body`.
- Modèles page now separates real Twilio DEV templates from local demo templates to avoid confusion.
- Added read-only Front API client foundation for future historical imports: conversation listing, search, and message listing.
- Added Front read-only dry-run script with rate-limit retry: `scripts/front_dry_run.py`.
- Documented Front historical import plan in `docs/FRONT_IMPORT.md`.
- Added Front historical import pilot foundation: exact phone matching, buffer tables, idempotent message storage, optional `front_history` attachment, `scripts/front_import_pilot.py`, and Admin visibility.
- Added Front migration classification: active/resolved/manual_review with recommended `reply` or `follow_up` when safe.
- Added filtered Admin review for Front buffer records and read-only Front cutover planning with `scripts/front_cutover_plan.py`.
- Added Front buffer rematch and dry-run-first matched conversion tools for post-backfill cutover preparation.
- Added SchoolDrive replay tool: `scripts/schooldrive_replay_payloads.py`.
- Added synthetic SchoolDrive smoke test: `scripts/schooldrive_smoke.py`, covering create, update, stale ignore, duplicate ignore, sent WhatsApp, queued WhatsApp, and archive handling without real personal data.
- Staging synthetic SchoolDrive smoke test passed, including DB side effects for sent WhatsApp follow-up creation, queued WhatsApp waiting state, and archive resolution.
- Real SchoolDrive MCP replay passed on staging with six real records, one duplicate response, and one stale snapshot ignored.
- Validated and documented the SchoolDrive MCP timestamp convention: current MCP naive timestamps are already UTC (`KEEP_CURRENT_UTC`), so do not subtract two hours.
- Admin readiness now separates SchoolDrive records waiting for the first sent autoresponder from true open conversations without a next action.
- Added production cutover runbook: `docs/CUTOVER_RUNBOOK.md`.
- Added Admin `État` readiness view for SchoolDrive, Front, Twilio, backups, and workflow consistency.
- Added SQLite backup and guarded restore scripts for deployed environments.
- Added automated backup cron installer: `deploy/scripts/install_backup_cron.sh`.
- Added pre-cutover CLI check: `scripts/pre_cutover_check.py`.
- Added Twilio template audit CLI: `scripts/twilio_template_audit.py`.
- Added initial ESSR template premapping CLI: `scripts/premap_sequence_templates.py`.
- Applied the initial AI-selected premapping on staging and prod: 75 approved real Twilio template mappings total, 25 each for `FSM`, `APP`, and `AS`. This is explicitly a starting point for Laura's commercial validation.
- Documented backup/restore procedure in `docs/BACKUP_RESTORE.md`.
- Staging backup and restore have been tested successfully on DigitalOcean.
- Latest staging readiness is green for SchoolDrive, Front, Twilio, Backup, and Workflow.
- Latest SchoolDrive MCP backfill has 35 accepted events, 2 ignored events, and 30 SchoolDrive-backed leads in staging.
- Latest Front pilot buffer on staging contains 13 Front conversations and 159 Front messages.
- Latest Front rematch: 11 unmatched, 1 ambiguous, 1 matched. The matched row is linked to `subscription:131887` / Lea Bucco; 11 Front messages were attached as `front_history`. Latest Front conversion dry-run skipped the matched row because an open `follow_up` action already exists.
- Latest Twilio staging sync found 10 DEV Content API templates: 4 `pending`, 6 `draft`, and 0 real approved templates.
- Test template `sc_dev_accuse_reception_fr_001` was submitted for WhatsApp approval and is currently `pending`; closed-window template validation still waits for approval.
- Staging pre-cutover check passed and automated backup cron is installed on the droplet.
- Documented Twilio WhatsApp sender migration strategy in `docs/TWILIO_SENDER_MIGRATION.md`.
- Inbound WhatsApp identity guardrail added: exact phone match attaches automatically; zero or multiple matches create a temporary `À identifier` lead with manual name/course fields.
- V2 identity-resolution debt is documented in `docs/TECHNICAL_DEBT.md`.
- Historical SchoolDrive diagnostic: `lead:124126` arrived with `armsg:1005384` as `queued`, while Claude MCP verified the same AR was already `sent` in SchoolDrive and no newer webhook reached Cockpit. Tiago later reported that the projector was published; the remaining gate is a fresh live website-form validation.
- Actions tab refactored to a stable UX model: banner first, fixed standard block, and disabled unavailable sections with reasons. Action/event history lives in `Journal`. `reply` and `follow_up` remain system actions completed from `Conversation`; manual standard commands are call scheduling/modification, manual reprise, documentation, and sequence-step skip.

## Latest Hardening

- App-style FastAPI endpoints require `SALES_COCKPIT_API_TOKEN` outside local tests.
- JSON mock Twilio inbound webhook calls require `SALES_COCKPIT_MOCK_WEBHOOK_TOKEN` or the API token outside local tests.
- Twilio status callbacks ignore status regressions, so a late `sent` callback cannot overwrite `delivered` or `read`.
- Twilio message SIDs are normalized to uniqueness and protected by a partial unique index.
- `SALES_COCKPIT_SEED_DEMO_DATA=false` keeps the core seed but removes `SD-DEMO-*` conversations for clean production databases.
- The WhatsApp composer no longer shows a fake attachment uploader; attachments are explicitly out of V1.
- No-show call retries are scoped by rendez-vous via `call_cycle_id` and `call_attempt_index`.
- Business-rule seed data is versioned; legacy active `post_call_undecided` steps are deactivated by migration.
- Twilio template sync can approve and unblock linked template requests when a real approved template is found.
- SchoolDrive signed, do-not-contact/opt-out, course-full, and stale default-session signals are handled.
- Follow-up quotas block relance overload but do not block a normal human reply; the global kill switch still blocks every WhatsApp send.
- Outbound WhatsApp sends are claimed per active action before Twilio is called; a duplicate free-form or template submit for the same active action is rejected instead of sending twice.
- Outbound WhatsApp sends write a pending message before the Twilio call, then mark it `send_error` if Twilio fails so an explicit retry is possible.
- Business-rule seeding preserves existing approved real Twilio template mappings; tests protect the ESSR fine-tuning from being overwritten by a deploy seed.
- `scripts/pre_cutover_check.py --strict-prod` is the mandatory final production gate before routing real WhatsApp to Sales Cockpit.

## Next Checkpoints

1. Create a restore point, then clean/rebuild staging SchoolDrive data if the historical replay pollution makes validation unreadable.
2. Resume live SchoolDrive validation with a fresh Lead and Presubscription once the worker/projector is visibly running.
3. Verify live-payload behavior in staging: upsert, stale-event ignore, duplicate-event ignore, WhatsApp body rendering, Tanjona +72h follow-up creation, queued-message no-follow-up, archive resolution, and course-start conflict behavior.
4. Run a focused UI scenario validation with François or Laura once real SchoolDrive records are visible.
5. Run staging `pre_cutover_check` and fix any scenario failure before adding new features.
6. Keep PROD disconnected until staging scenario behavior and the production cutover checklist are validated.
7. Only after scenario validation, do a moderate refactor of the large files into UI pages/components, workflow services, seed/reset, and repositories.
8. Monitor Twilio template approval. Full closed-window validation waits for one approved real template.
9. After additional SchoolDrive backfill, run Front rematch, review conversion dry-run, then execute matched conversion only if rows are ready.
11. Keep Front read-only and avoid attaching history until matched rows are reviewed.
12. Review whether attached Front history should appear by default or behind a conversation filter.
13. Add the real V2 identity-resolution workflow: SchoolDrive recrawl/search, temporary lead merge, ambiguous candidate selection, and Front unmatched reconciliation.
14. Add Notion historical enrichment.

## Integration Policy

- Twilio production is not touched until an explicit cutover plan exists.
- Twilio stays in mock mode unless `SALES_COCKPIT_TWILIO_MODE=sandbox` or `live` is explicitly configured.
- SchoolDrive is read-only in V1.
- Notion is read-only in V1.
- Front.io remains active until Sales Cockpit is tested and approved.
