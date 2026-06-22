# Adversarial Review

Review date: 2026-06-22.

Status: findings preserved, not implemented yet. This document records the adversarial system review requested before production WhatsApp cutover. It must be read before deciding that Sales Cockpit is ready for live WhatsApp routing.

Validation run during the review:

- local Git worktree was clean;
- local automated tests passed: `133 passed`;
- `compileall` passed;
- no code was changed during the review.

## Summary

The core model `Parcours / Flux / Action` remains the right architecture for V1.

Sales Cockpit is close to a solid V1, but the review found several production risks that are not caught by the current test suite. They are mostly operational risks: duplicate outbound sends, incomplete cutover gates, state transitions around terminal statuses, and performance/visibility issues at higher volume.

Do not treat these findings as implemented fixes. They are a backlog of hardening work to plan and execute before or immediately around the production WhatsApp cutover.

## P0 Before WhatsApp Cutover

### 1. SchoolDrive Cleanup Script Can Target Production

File references:

- `scripts/cleanup_schooldrive_staging.py`
- `deploy/env/prod.env.example`

Risk:

The cleanup script blocks `SALES_COCKPIT_ENVIRONMENT=production`, but production examples use `prod`. With `--execute`, the script could theoretically delete SchoolDrive-ingested rows in a production database.

Required fix:

- block both `prod` and `production`;
- require a staging-only database path or explicit staging marker;
- add a test proving `env=prod + --execute` refuses to run.

### 2. Outbound WhatsApp Sends Are Not Idempotent

File references:

- `sales_cockpit/store.py`, `send_freeform_message`
- `sales_cockpit/store.py`, `send_template_message`

Risk:

The code inserts a local `pending_send` message, calls Twilio, then updates the message and closes the action. A double-click, retry, or concurrent API call can send two real WhatsApp messages before the action is closed.

Required fix:

- claim the task/action atomically before calling Twilio;
- reject a send when a send attempt is already pending for that action;
- add an idempotency key tied to `task_id` / message attempt;
- add concurrency tests for double-submit.

### 3. Terminal Statuses Can Be Reopened Too Easily

File references:

- `sales_cockpit/store.py`, `set_conversation_status`
- `sales_cockpit/store.py`, `_upsert_reply_action_for_inbound`

Risk:

Manual reactivation can create a commercial action even if the lead is `do_not_contact`, `signed`, or `not_relevant`. Inbound messages on signed or non-relevant prospects can also create a `reply` without a dedicated terminal-status review.

Required fix:

- for `do_not_contact`, force `contact_review`;
- for `signed` and `not_relevant`, force a human review or explicit status reset before commercial work;
- never create ordinary `reply` / `follow_up` actions on terminal statuses without an explicit unlock.

### 4. Workflow Completion Can Mutate Before Failing

File references:

- `sales_cockpit/store.py`, `complete_action_with_workflow`

Risk:

Some paths close the current action before verifying that the next workflow step can be created. If a required sequence step or assignee is missing, the function can return an error after the action is already marked done.

Required fix:

- compute and validate the full transition plan before mutating;
- or use explicit transaction rollback for every business failure;
- add tests for missing sequence step / missing assignee / invalid outcome.

### 5. Strict Production Check Is Not Strict Enough

File references:

- `scripts/pre_cutover_check.py`
- `sales_cockpit/store.py`, template recommendation lookup

Risk:

`--strict-prod` currently misses several production-readiness conditions:

- it calls `seed_initial_data()`, so it is not read-only;
- it validates template mappings by sequence, step, and category, but not by `lead_type`;
- it does not prove that the real SchoolDrive path emitted an `AR sent` snapshot and created a Setter II follow-up;
- it does not validate the seed password strength;
- it does not validate backup integrity beyond existence, size, and age.

Required fix:

- make strict production checks read-only;
- validate the full matrix: sequence step x active course category x lead type;
- add a gate for a recent real SchoolDrive `sent` autoresponder with follow-up creation;
- fail on default/weak `SALES_COCKPIT_SEED_PASSWORD`;
- validate backup restoreability, not just presence.

## P1 Important Hardening

### Phone Normalization

Inbound Twilio matching relies on strict equality against `phone_e164`, `phone_raw`, or conversation recipient phone. If SchoolDrive sends a number in a different format, Sales Cockpit can create an unnecessary temporary identity.

Fix:

- normalize all SchoolDrive and Twilio phone numbers to a shared E.164 form;
- keep raw phone separately;
- add tests for Swiss formats: `079...`, `+41...`, `0041...`, spaces and punctuation.

### Twilio Callback Race And Crash Recovery

If Twilio accepts an outbound message but the process crashes before writing the SID, the local message can stay `pending_send` without a SID. Later status callbacks become `unknown_message`.

Fix:

- include a local message identifier in the status callback URL when possible;
- store unknown callbacks for later reconciliation;
- make strict-prod fail if old `pending_send` rows remain.

### Course Full Conversation State

When SchoolDrive signals course/session full, Sales Cockpit cancels follow-ups and either annotates a planned call or creates a review action. The conversation may remain resolved in some paths.

Fix:

- when a course-full review action is created, ensure the conversation is open;
- when a call is planned, make the course-full warning visibly attached to that call;
- define what happens if the planned call is later cancelled.

### Course-Start Follow-Up Arbitration

Course-start follow-up can be skipped if a standard follow-up already exists and the dates are not within the 24h conflict window.

Fix:

- if the course-start due date is earlier than the existing standard follow-up, replace or reprioritize;
- keep planned setting/closing calls non-interruptible.

### `will_sign` Status Sync

Forcing qualification to `will_sign` may preserve an existing follow-up's sequence and due date instead of switching cleanly to `closer_will_sign`.

Fix:

- when `will_sign` is selected, explicitly move active follow-up to `closer_will_sign` step 1 unless a higher-priority call action exists.

### Template Request Lifecycle

Template requests linked to blocked follow-ups can remain open after the follow-up is cancelled by inbound, stop status, or another workflow transition.

Fix:

- cancel or mark obsolete linked template requests when their blocked follow-up is no longer relevant;
- close the matching admin action with an explicit outcome.

### Front Cutover Visibility

The strict production check does not currently block on active Front conversations that are unmatched, manually reviewed, or ready to convert.

Fix:

- decide whether Front history is a hard cutover gate or only historical fallback;
- if hard gate, store per-conversation cutover decisions and fail strict-prod while unresolved items remain.

## P1 Performance And Volume

### Tasks Page Loads Too Much

File references:

- `sales_cockpit/ui/app.py`, `render_work_queue`
- `sales_cockpit/store.py`, `list_tasks`

Risk:

The tasks page refreshes frequently, loads broad task sets, and filters in the UI. This will become slow as tasks grow.

Fix:

- add SQL-level assignee/status/queue filters;
- add pagination;
- add counts per queue from SQL;
- add covering indexes on task assignee/status/due fields.

### Inbox Pagination Happens Before Business Filtering

File references:

- `sales_cockpit/store.py`, `list_conversations`

Risk:

The SQL query applies `LIMIT/OFFSET` before Python filters for queue and responsibility. A relevant conversation can be hidden if it falls outside the first global page.

Fix:

- push work queue and responsibility filtering into SQL/CTE;
- paginate after the business filter.

### Phone Matching Query Scans

File references:

- `sales_cockpit/store.py`, `_phone_match_candidates`

Risk:

Inbound matching scans leads/conversations and can slow down as historical lead volume grows.

Fix:

- add indexes on `leads.phone_raw` and `conversations.recipient_phone_e164`;
- consider replacing the OR query with index-friendly `UNION` queries.

### Conversation Thread Is Not Paginated

File references:

- `sales_cockpit/store.py`, `list_messages`
- `sales_cockpit/ui/app.py`, `render_messages`

Risk:

Large historical conversations or Front-imported threads can slow the UI.

Fix:

- load the latest N messages by default;
- add "load older messages";
- optionally collapse Front history by default.

## P2 Cleanup And Consistency

### Runtime Seed/Migration

`seed_initial_data()` runs from UI startup, API startup, and pre-cutover check. This has been convenient for V1, but it makes runtime behavior less predictable and can introduce SQLite write contention.

Future direction:

- run migrations/seed during deploy/init;
- make app startup and strict checks avoid broad write-side effects.

### Fresh Schema And Migrated Schema Diverge

Some task foreign keys exist in the fresh schema but not in migrated databases, because SQLite cannot add foreign-key constraints through simple `ALTER TABLE`.

Future direction:

- add orphan checks to pre-cutover;
- later rebuild affected tables if strict FK parity is required.

### Action Cancellation Semantics

Many replaced or cancelled actions are marked `done` with an outcome rather than `cancelled`. This works operationally, but makes reporting less precise.

Future direction:

- distinguish `done` from `cancelled` based on cause: completed by user, cancelled by inbound, replaced by appointment, stopped by terminal status, superseded by course-start.

### Resolution Note Rule

Business rules have per-reason `requires_note`, but `set_conversation_status` currently requires a note for every manual closure.

Future direction:

- either keep the stricter V1 rule and update docs;
- or use `resolution_reason_requires_note()` consistently.

### Documentation State Is Stale In Places

Some docs still mention older deployment commits or older test counts. This can confuse a future session.

Fix later:

- create one authoritative "current deployment truth" block with local HEAD, staging deployed commit, prod deployed commit, and latest validation;
- remove old `125 tests` references;
- update stale commit references after the next deploy.

### Large Files

Current size hotspots:

- `sales_cockpit/store.py`: about 7480 lines;
- `sales_cockpit/ui/app.py`: about 4808 lines;
- `sales_cockpit/db.py`: about 2362 lines;
- `sales_cockpit/business_rules.py`: about 1551 lines.

Do not refactor these during urgent cutover unless a correction requires it. Before official V2, extract the modules already listed in `docs/TECHNICAL_DEBT.md`: `workflow_engine`, `schooldrive_ingest`, `twilio_templates`, `twilio_messaging`, `admin_actions`, and `pilotage`.

## Suggested Fix Order

1. Patch production-dangerous safeguards: cleanup script, strict-prod read-only behavior, seed password gate.
2. Patch outbound idempotency and callback recovery.
3. Patch terminal-status reopening and inbound behavior.
4. Patch workflow mutation-before-failure.
5. Patch strict-prod template matrix and real SchoolDrive AR-sent gate.
6. Patch phone normalization and phone indexes.
7. Patch course-full/course-start edge cases.
8. Patch task/inbox pagination and performance.
9. Update stale docs and deployment truth block.
10. Re-run full tests, compileall, staging deploy, staging pre-cutover, then repeat a focused adversarial review.

## Tests To Add

- cleanup script refuses `prod` and `production` with `--execute`;
- double-submit on same follow-up sends at most one Twilio message;
- template double-submit sends at most one Twilio message;
- crash or DB failure after Twilio accepted send leaves a recoverable state;
- old `pending_send` rows fail strict-prod;
- manual reactivation of `do_not_contact`, `signed`, `not_relevant`;
- inbound on `signed` and `not_relevant`;
- `course_full` on a resolved conversation opens the needed review;
- course-start due earlier than active standard follow-up;
- `will_sign` replaces active standard follow-up with `closer_will_sign`;
- strict-prod fails when a `presubscription` mapping is missing but `lead` mapping exists;
- queue/responsibility filtering after pagination cannot hide due conversations;
- phone normalization for Swiss number variants.

