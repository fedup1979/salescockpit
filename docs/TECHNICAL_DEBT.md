# Technical Debt And V2 Notes

This document tracks deliberate V1 shortcuts that must not be forgotten during staging and production cutover.

## Workflow Invariants Hardening

The V1 workflow now relies on this invariant: an open commercial conversation must have one active next action, except for tightly controlled internal transitions. The nominal UI path is aligned, but several safeguards should be hardened before external automation or V2 workflow expansion.

V2 debt:

- make critical store transitions atomic: validate the next step, assignee, outcome, and sequence availability before marking the current task `done`;
- validate `action_outcome` strictly by action type so an unsupported outcome cannot close an action without creating the expected next state;
- add a stronger guard against multiple active main actions, while preserving the intentional `reply` plus planned call exception;
- decide explicitly whether `manual_reprise` plus planned call is an allowed exception or a data anomaly;
- make `pre_cutover_check.py` strictly read-only, or document why it is allowed to call `seed_initial_data()`;
- evaluate a global hook for outbound messages sent without an active `reply` or `follow_up`;
- update any remaining legacy copy that says a user should choose the next commercial action from `Conversation`;
- replace legacy "post-call undecided follow-up" wording with "manual reprise" everywhere it still appears.

## Refactoring Before Official V2

V1 intentionally concentrated a lot of behavior in a small number of files to move fast during the cutover window. This is acceptable for the V1 launch, but it must not become the long-term architecture.

Before starting the official V2 feature track, extract:

- `workflow_engine`: parcours/flux/action transitions, call cycles, no-show logic, course-start arbitration, safeguards;
- `schooldrive_ingest`: webhook idempotency, snapshot freshness, payload normalization, SchoolDrive business signals;
- `twilio_templates`: Content API sync, template requests, approval/unblock logic, mapping validation;
- `twilio_messaging`: outbox send path, status callbacks, delivery-state transitions, live-mode guards;
- `admin_actions`: bug reports, template requests, default-session reviews, integration incidents;
- `pilotage`: read models and writes for Laura's tuning page.

Current large files to split first: `sales_cockpit/store.py`, `sales_cockpit/ui/app.py`, `sales_cockpit/db.py`.

Do this as a cleanup phase before adding IA automation, PBX/softphone, A/B testing, or richer SchoolDrive write-back. The goal is to keep the V1 cutover stable while making V2 safer to extend.

## Conversation Journal Analytics

### V1 Implemented Guardrail

The conversation journal is a deterministic projection over the existing canonical tables (`messages`, `tasks`, `lead_events`, SchoolDrive webhook records, and Front buffer records). It avoids creating a second source of truth and deliberately hides WhatsApp message bodies while keeping internal notes visible.

### V2 Debt

Before using the journal for heavy AI analytics or cross-conversation reporting:

- audit historical conversations for missing `lead_events` and decide whether a backfill is worth the operational risk;
- extract the journal projection out of `store.py` if it starts gaining more categorization rules;
- consider a read-optimized materialized journal table only if projection queries become too slow or analytics require global scans;
- add event-quality metrics so missing actor, effect, or sequence metadata is visible before training/evaluation.

## Identity Resolution

### V1 Implemented Guardrail

Inbound WhatsApp matching is intentionally conservative:

- one exact phone match in Sales Cockpit: attach the message to that lead;
- zero exact matches: create a temporary `Inconnu(e)` lead marked `À identifier`;
- multiple exact matches: create a temporary `Inconnu(e)` lead marked `À identifier` and store the candidate leads for manual review.

Users can temporarily fill:

- first name;
- last name;
- course category;
- course/session;
- identification note.

The temporary data is operational only. It does not replace SchoolDrive as source of truth.

### V2 Debt

Sales Cockpit still needs a real identity-resolution workflow:

- search/replay SchoolDrive by phone, name, and email;
- merge a temporary Sales Cockpit lead into the correct SchoolDrive-backed lead;
- preserve and move the WhatsApp thread, messages, actions, events, notes, and Front history during merge;
- expose candidate selection in the UI for ambiguous matches;
- periodically retry matching temporary leads against newly created SchoolDrive records;
- decide whether Front unmatched conversations can create temporary identity records or stay in the Front buffer until matched.

### Cutover Risk

Do not auto-attach an inbound WhatsApp to a candidate when more than one lead shares the same phone number. Wrong identity attachment is more dangerous than a temporary `À identifier` record.

## Sequence Recalculation

### V1 Implemented Guardrail

Admins can tune active course categories, flux steps, and template mappings in Sales Cockpit. These changes deliberately affect only future flux actions created after the save.

Existing open tasks keep their original due date, step index, assignee, and recommended template. This avoids silently changing work already visible in a user's queue.

Flux steps are now stored as absolute offsets from the flow trigger (`offset_direction`, `offset_amount`, `offset_unit`). Recalculation must therefore use the original sequence anchor stored on tasks as `metadata_json.sequence_anchor_at`; it must not chain from the previous task's completion time.

### V2 Debt

Add a controlled recalculation workflow:

- preview which open or future tasks would change;
- show old versus new due date, step, template and assignee;
- let an admin apply the recalculation only to selected fluxes, categories, or leads;
- write an audit log entry for every recalculated task;
- never recalculate completed, cancelled, archived, signed, non pertinent, or do-not-contact conversations.

Do not add draft/publish/rollback for Pilotage in V1. It was considered and rejected as overkill for the cutover. Revisit only if Laura's tuning cadence creates real operational risk.

## Unsupported Course Categories

### V1 Implemented Guardrail

If SchoolDrive sends a lead or presubscription for a category not active in `course_categories`, Sales Cockpit stores the conversation and SchoolDrive WhatsApp messages, but creates a Setter I review task instead of starting the structured Setter II follow-up flux.

### V2 Debt

Add a guided admin workflow to activate a new course category:

- choose or create the category;
- configure the default session;
- define templates for every required flow step;
- run a simulator before activation;
- optionally reprocess the waiting review tasks once the category is configured.

## Course-Start Follow-Up Engine

### V1 Implemented Guardrail

Course-start follow-ups can now be created from the SchoolDrive `course.start_date` or from the active default session date for the course category.

Runtime behavior:

- if a setting/closing call is already planned, the course-start follow-up does not interrupt it;
- if a course-start follow-up conflicts with a lead/presubscription follow-up within 24h, the course-start follow-up wins and the lead-relative follow-up is cancelled;
- if a category has no active default session and SchoolDrive provides no `start_date`, no course-start follow-up is created.

### V2 Debt

Add a global scheduling/recalculation workflow:

- periodic sweep that detects upcoming course-start reminders even when no fresh SchoolDrive event arrives;
- preview and recalculate affected future tasks after an admin changes default sessions, course-start flux steps, or template mappings;
- explain conflicts before applying changes;
- preserve planned setting/closing calls as non-interruptible actions;
- write audit logs for every cancelled/replaced task.

Also add a periodic check for default sessions that have passed, even if no new SchoolDrive event arrives that day. V1 creates an admin action when such a stale default session is encountered during ingestion; V2 should find it proactively.

### Course Capacity Freshness

V1 reacts to the latest SchoolDrive webhook fields for course/session capacity (`course_full`, `session_full`, `is_full`, `available_seats`, or equivalent normalized signals). If SchoolDrive marks a course full, Sales Cockpit stops open follow-ups and routes the case to Setter I, or annotates the planned call if one exists.

Known debt: before sending a course-start follow-up, Sales Cockpit does not yet perform a live SchoolDrive capacity check. It assumes the latest webhook is current. Before automating course-start sends, add one of these safeguards:

- SchoolDrive emits a webhook every time course/session capacity changes;
- or Sales Cockpit performs a pre-send SchoolDrive capacity lookup immediately before the message is sent.

Without this, a course could become full after a follow-up was scheduled but before Setter II sends it.

## Admin Work Queues

### V1 Implemented Guardrail

Template requests and bug reports now create explicit rows in `admin_actions`:

- template requests appear in `Modèles` and `Admin > Templates`, and create an admin action that can be completed;
- bug reports appear in `Admin > Bugs & logs`, and create an admin action that can be completed;
- both keep the source context needed for review and are visible in `Admin > Actions admin`.

They deliberately do not create a standard commercial `tasks` row. Commercial tasks are lead/conversation-based, while a bug report can be global and a template request can be a support item rather than the prospect's next commercial action. The dedicated `admin_actions` table keeps admin workload visible without blurring the workflow model.

### V2 Debt

Extend the existing admin-action layer if admin workload needs richer operations:

- assignment to a specific admin;
- due dates and priorities;
- filters by kind, status, and source page;
- Twilio approval polling incidents;
- integration incidents;
- richer audit trail for reopen/reassign/close.

Keep the current distinction between prospect next actions and internal support work.

## Appointment Reminders

### V1 Implemented Guardrail

Setting and closing appointments are visible as future call-documentation actions. When the due time arrives, the task becomes actionable and the user documents whether the prospect was reached.

If the prospect is not reached, V1 creates call retry actions at roughly +2h and +24h before switching to the appropriate no-show flux.

### V2 Debt

Add optional WhatsApp reminders before planned appointments:

- J-1 reminder when the appointment is more than 24h away;
- H-1 reminder when the appointment is more than 1h away;
- no reminder if the appointment is too soon;
- cancellation when the appointment is moved, cancelled, or replaced;
- template mapping by course, role, and appointment type.

These reminders must never override the appointment itself.

## API/UI Workflow Parity

Some API endpoints are intentionally thin V1 wrappers around the core store functions. Before exposing these endpoints to external IA agents or automation tools, verify that the API path enforces exactly the same outcome logic as the Streamlit UI:

- action outcome selection;
- next-action creation;
- template recommendation and request blocking;
- safeguards and outbox behavior;
- call reschedule/cancel/documentation flows;
- terminal statuses and SchoolDrive signals.

The rule for V2: external tools may call APIs only after each workflow-changing endpoint has a dedicated test proving parity with the UI/store path.
