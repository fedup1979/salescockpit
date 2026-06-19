# Sales Cockpit Implementation Status

## Current Status

V1 staging build is runnable. Twilio sandbox messaging is connected for staging.

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
- UI simplification: `Température` hidden, `sales_stage` displayed as `Parcours`, private notes always included for future learning.
- Global `Tâches` filters responsibility by individual people, defaults to the connected user's own queue, and persists a manual responsible-person choice during navigation.
- SchoolDrive lead source types use `lead` and `presubscription`; inbox cards display `Lead` / `Préinscription` and use course category vs course short name accordingly.
- Experimental UX pass: `Tâches` is first in navigation and uses a split-screen action/person list with the selected prospect detail on the right.
- Mock seed ensures at least one open task for each active user for visual queue checks.
- Inbound unanswered prospects are highlighted with a restrained hot signal and sorted above ordinary due actions.
- `Tâches` and Inbox auto-refresh every 10 seconds while visible.
- Action workflow decisions documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`: action as operational unit, main vs support actions, statuses, proofs, outcomes, triggers, and transition table.
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
- The Actions tab is contextual by action type: WhatsApp actions guide users to the Conversation composer, calls use result + mandatory note, contact reviews show explicit do-not-contact decisions, and exceptions live in Actions avancées.
- Setting/closing calls can be completed with business outcomes that create the next action.
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
- Added SchoolDrive replay tool: `scripts/schooldrive_replay_payloads.py`.
- Added synthetic SchoolDrive smoke test: `scripts/schooldrive_smoke.py`, covering create, update, stale ignore, duplicate ignore, sent WhatsApp, queued WhatsApp, and archive handling without real personal data.
- Staging synthetic SchoolDrive smoke test passed, including DB side effects for sent WhatsApp follow-up creation, queued WhatsApp waiting state, and archive resolution.
- Admin readiness now separates SchoolDrive records waiting for the first sent autoresponder from true open conversations without a next action.
- Added production cutover runbook: `docs/CUTOVER_RUNBOOK.md`.
- Added Admin `État` readiness view for SchoolDrive, Front, Twilio, backups, and workflow consistency.
- Added SQLite backup and guarded restore scripts for deployed environments.
- Added automated backup cron installer: `deploy/scripts/install_backup_cron.sh`.
- Added pre-cutover CLI check: `scripts/pre_cutover_check.py`.
- Added Twilio template audit CLI: `scripts/twilio_template_audit.py`.
- Documented backup/restore procedure in `docs/BACKUP_RESTORE.md`.
- Staging backup and restore have been tested successfully on DigitalOcean.
- Latest staging readiness is green for SchoolDrive, Front, Twilio, Backup, and Workflow.
- Latest Front pilot buffer on staging contains 5 Front conversations and 10 Front messages, with 0 attached operational messages. All are currently unmatched until SchoolDrive real data/backfill is present.
- Latest Front cutover plan on staging returns 5 manual-review rows because all buffered Front conversations are unmatched. No actions are created by this plan.
- Latest Twilio staging sync found 5 DEV Content API templates, all currently `draft`.
- Latest Twilio template audit found 0 real approved Twilio templates, so closed-window template validation still waits on the ESSR sender/WABA path.
- Staging pre-cutover check passed and automated backup cron is installed on the droplet.
- Documented Twilio WhatsApp sender migration strategy in `docs/TWILIO_SENDER_MIGRATION.md`.

## Next Checkpoints

1. Validate Tiago's real SchoolDrive staging payloads as soon as they are posted.
2. If Tiago is pending, run the synthetic SchoolDrive smoke test on staging after each relevant deployment.
3. Verify real-payload behavior in staging: upsert, stale-event ignore, duplicate-event ignore, WhatsApp body rendering, Tanjona +72h follow-up creation, queued-message no-follow-up, and archive resolution.
4. Run a focused UI scenario validation with François or Laura once real SchoolDrive records are visible.
5. Fix any scenario failures before adding new features.
6. Keep PROD disconnected until staging scenario behavior and the production cutover checklist are validated.
7. Only after scenario validation, do a moderate refactor of the large files into UI pages/components, workflow services, seed/reset, and repositories.
8. Test Twilio template synchronization and template creation from staging; full approval validation waits for the ESSR sender/WABA path.
9. Run a small Front pilot on staging: preview, then optional `--write` to buffer tables only. Keep Front read-only and low-volume.
10. Review Front migration classification results before creating any operational actions from Front.
11. Review whether attached Front history should appear by default or behind a conversation filter.
12. Add Notion historical enrichment.

## Integration Policy

- Twilio production is not touched until an explicit cutover plan exists.
- Twilio stays in mock mode unless `SALES_COCKPIT_TWILIO_MODE=sandbox` or `live` is explicitly configured.
- SchoolDrive is read-only in V1.
- Notion is read-only in V1.
- Front.io remains active until Sales Cockpit is tested and approved.
