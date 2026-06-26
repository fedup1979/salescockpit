# Sales Cockpit - Technical Debt V1

This document tracks the V1 debt that matters for staging, production cutover, and the first V2 planning pass.

## Maintenant

These items should be handled before or during the real cutover window because they affect operational correctness.

### SchoolDrive Signals

- Confirm that SchoolDrive emits a fresh webhook when a WhatsApp autoresponder status changes to `sent`.
- Validate Tiago's schema `1.1` on fresh staging records from the real website path.
- Confirm the fresh website payload includes `course.course_id`, `course.course_short_name`, `course.seats_total`, `course.seats_occupied`, `course.seats_available`, `course.is_full`, `signed`, `do_not_contact.blocked`, and `related_subscriptions[]` when applicable.
- Confirm operationally that a course crossing full/not-full causes SchoolDrive to re-emit affected leads/presubscriptions.
- Confirm operationally that the top-level `signed` boolean appears for one signed presubscription and one lead-originated signature.

### Real Site Validation

- Run the final manual protocol with restored fake prospects.
- Finish with one real lead created from the website.
- Finish with one real presubscription created from the website.
- Verify SchoolDrive links, autoresponder visibility, action creation, duplicate protection, capacity handling, and enrolment handling.

### Twilio Cutover Readiness

- Synchronize real ESSR Twilio templates in read-only mode.
- Ensure every mapped follow-up step uses a real approved Content SID (`HX...`, not `HX_MOCK_*`).
- Keep real Twilio writes and sends disabled until explicit cutover.
- Confirm HTTPS inbound and status callback URLs before live mode.

### Workflow Invariants

- Preserve the V1 invariant: an open commercial conversation must have one clear active next action, except the controlled urgent-response plus planned-call case.
- Validate that completing a response action, relance, setting call, or closing call creates the expected next state.
- Keep active-conversation-without-next-action checks visible before cutover.
- Remove or update any remaining legacy copy that suggests choosing the next commercial action from the conversation thread.

### Pre-Cutover Check

- `pre_cutover_check.py --strict-prod` is read-only and does not seed.
- Current rule: non-strict local/staging checks may seed baseline data for readiness.
- Ensure strict production checks fail on demo seed data, missing secrets, non-HTTPS callbacks, stale backups, blocked actions, pending template requests, or missing template mappings.

## Plus Tard

These items are acceptable V1 limitations but should shape the V2 backlog.

### Workflow Engine Hardening

- Make critical store transitions atomic: validate next step, assignee, outcome, and sequence availability before marking the current task `done`.
- Validate action outcomes strictly by action type.
- Add a stronger guard against multiple active main actions while preserving the urgent-response plus planned-call exception.
- Decide explicitly whether manual reprise plus planned call is an allowed exception or a data anomaly.
- Add parity tests proving that API workflow endpoints enforce the same rules as the Streamlit UI and store path.

### Refactoring Before Official V2

Extract the largest behavior areas before adding IA automation, PBX/softphone, A/B testing, or richer SchoolDrive write-back:

- `workflow_engine`: parcours, flux, actions, call cycles, no-show logic, course-start arbitration, safeguards;
- `schooldrive_ingest`: webhook idempotency, snapshot freshness, payload normalization, SchoolDrive business signals;
- `twilio_templates`: Content API sync, template requests, approval/unblock logic, mapping validation;
- `twilio_messaging`: outbox send path, status callbacks, delivery-state transitions, live-mode guards;
- `admin_actions`: bug reports, template requests, default-session reviews, integration incidents;
- `pilotage`: read models and writes for Laura's tuning page.

Current large files to split first: `sales_cockpit/store.py`, `sales_cockpit/ui/app.py`, `sales_cockpit/db.py`.

### Conversation Journal Analytics

The V1 journal is a deterministic projection over canonical tables (`messages`, `tasks`, `lead_events`, SchoolDrive webhook records, and Front buffer records). Before using it for heavy analytics:

- audit historical conversations for missing `lead_events`;
- decide whether backfill is worth the operational risk;
- extract the projection out of `store.py` if categorization grows;
- consider a materialized journal only if projection queries become too slow;
- add event-quality metrics for missing actor, effect, or sequence metadata.

### Identity Resolution

Inbound WhatsApp matching remains intentionally conservative in V1:

- one exact phone match: attach to that lead;
- zero exact matches: create `Inconnu(e)` marked `À identifier`;
- multiple exact matches: create `Inconnu(e)` marked `À identifier` and store candidates.

V2 needs a real identity-resolution workflow:

- search/replay SchoolDrive by phone, name, and email;
- merge a temporary lead into the correct SchoolDrive-backed lead;
- preserve and move WhatsApp thread, messages, actions, events, notes and Front history during merge;
- expose candidate selection in the UI;
- periodically retry matching temporary leads against new SchoolDrive records;
- decide whether unmatched Front conversations create temporary identities or stay in the Front buffer.

Wrong identity attachment is more dangerous than a temporary `À identifier` record.

### Sequence Recalculation

V1 Pilotage changes affect only future tasks created after save. V2 should add controlled recalculation:

- preview affected open or future tasks;
- show old versus new due date, step, template and assignee;
- let an admin apply changes by flux, category or lead;
- write an audit log entry for every recalculated task;
- never recalculate completed, cancelled, archived, signed, non pertinent, or do-not-contact conversations.

Flux steps are stored as absolute offsets from the flow trigger. Recalculation must use `metadata_json.sequence_anchor_at`, not the previous task completion time.

### Unsupported Course Categories

If SchoolDrive sends a lead or presubscription for an inactive category, V1 stores the conversation and SchoolDrive WhatsApp messages, then creates a Setter I review task instead of starting Setter II automation.

V2 should add a guided admin workflow:

- choose or create the category;
- configure the default session;
- define templates for required flow steps;
- run a simulator before activation;
- optionally reprocess waiting review tasks.

### Course-Start Follow-Up Engine

V1 can create course-start follow-ups from `course.start_date` or active default session date. It does not interrupt planned setting/closing calls, and it can replace lead/presubscription follow-ups within 24h.

V2 should add:

- periodic sweep for upcoming course-start reminders even without fresh SchoolDrive events;
- preview/recalculation after default-session or flux changes;
- conflict explanation before applying changes;
- audit logs for cancelled or replaced tasks;
- proactive detection of default sessions that have passed.

### Capacity Freshness

V1 trusts the latest SchoolDrive webhook fields for capacity. Before automating course-start sends, add one of these safeguards:

- validate that SchoolDrive re-emits affected lead/presubscription snapshots when a course crosses the full/not-full boundary;
- or Sales Cockpit performs a live SchoolDrive capacity lookup immediately before send.

Without this, a course could become full after scheduling but before Setter II sends the message.

### Admin Work Queues

Template requests and bug reports use `admin_actions`, not standard commercial tasks. Extend this layer if admin workload needs:

- assignment to a specific admin;
- due dates and priorities;
- filters by kind, status and source page;
- Twilio approval polling incidents;
- integration incidents;
- richer audit trail for reopen/reassign/close.

Keep the distinction between prospect next actions and internal support work.

### Appointment Reminders

Setting and closing appointments are visible as future call-documentation actions in V1. V2 can add optional WhatsApp reminders:

- J-1 reminder when the appointment is more than 24h away;
- H-1 reminder when the appointment is more than 1h away;
- no reminder if the appointment is too soon;
- cancellation when moved, cancelled or replaced;
- template mapping by course, role and appointment type.

These reminders must never override the appointment itself.

## Abandonné V1

These ideas were considered and deliberately left out of V1.

- PBX/softphone integration.
- Agenda/calendar synchronization; V1 only exposes optional calendar hyperlinks.
- Notion enrichment or write-back.
- IA setter automation and automatic relance sending.
- Playwright automation as a mandatory validation layer; V1 uses a written manual protocol plus Streamlit AppTest coverage.
- Multilingual UI and message orchestration.
- Flux recalculation for existing open tasks after Pilotage edits.
- Advanced identity resolution and merge workflow.
- Live SchoolDrive capacity lookup before each send.
- Multiple-enrolment automation beyond preserving and reviewing incoming signals.
- A/B testing of templates, timings, or conversation flows.
- Performance/pagination work beyond current list guards and indexes.
- Automated handling of unknown Twilio callbacks beyond storing/reporting current known statuses.
- External workflow API/UI parity as a release gate beyond the hardened send/action paths covered now.
- Draft/publish/rollback for Pilotage. Revisit only if Laura's tuning cadence creates real operational risk.
- Automatic absence transfers between collaborators. Another collaborator can manually open the absent person's queue.
- Automatic conversion of Front active conversations at large scale before a reviewed pilot batch proves the conversion rules.
- Live SchoolDrive write-back beyond the validated webhook/status signals.
- Heavy AI analytics on the conversation journal before event quality is audited.
- External IA agents or automation tools calling workflow-changing APIs before API/UI parity tests exist.
