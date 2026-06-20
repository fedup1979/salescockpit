# Current Project State

Last updated: 2026-06-20 20:05 Europe/Zurich.

This is the first document to read when resuming Sales Cockpit.

## Executive Summary

Sales Cockpit is deployed and running in staging on DigitalOcean. Production is deployed cold and remains in Twilio `mock` mode.

## Production Readiness Snapshot

- Latest checkpoint before hardening audit: `a02f10c`.
- Latest deployed staging UI/API check before this audit: OK on commit `a1917d8`.
- Latest local automated validation after this audit: `116 passed`, `compileall` OK, `git diff --check` OK, BOM scan clean.
- Latest staging pre-cutover check before this audit: OK.
- Staging Twilio mode: `mock`, no real WhatsApp send from Sales Cockpit.
- Production Twilio mode: `mock`, prepared cold only.
- SchoolDrive webhook ingestion: implemented and passing synthetic/replay checks.
- Current SchoolDrive live gate: validate one fresh website form through AR `sent` snapshot and Tanjona +72h follow-up.
- Front: read-only buffer foundation exists; Front is not a blocker for the Laura workflow review.
- Go/no-go: good for Laura business review in staging; not yet GO for operational WhatsApp cutover.
- Hardening completed locally after the checkpoint: app API token guard, mock webhook token guard, Twilio status regression guard, Twilio SID uniqueness, production seed without demo conversations, fake attachment uploader removed, documentation aligned.

The main remaining blocker before operational production cutover is a fresh live end-to-end SchoolDrive validation after the SchoolDrive WhatsApp/projector worker is confirmed running:

```text
Website form -> SchoolDrive lead/presubscription -> automatic WhatsApp AR -> AR sent snapshot -> Sales Cockpit thread + Tanjona follow-up
```

Sales Cockpit has now encoded the canonical workflow model:

- `Parcours`: human/commercial state of the prospect.
- `Flux`: configurable follow-up scenario and templates.
- `Action`: concrete operational work item in the queue.

Important new runtime rule: a prospect message during an already planned setting/closing call creates an urgent `reply` action for Mihary but does not cancel the planned call. Course-start relances do not interrupt planned calls.

## Repositories And Environments

- Local repo: `C:\Users\FD\Desktop\SalesCockpit`
- GitHub: `https://github.com/fedup1979/salescockpit`
- Server: `root@139.59.158.77`
- Staging UI: `http://139.59.158.77:8502`
- Staging API: `http://139.59.158.77:8602`
- Staging SchoolDrive webhook: `http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription`
- Staging Twilio inbound webhook: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/inbound`
- Staging Twilio status callback: `http://139.59.158.77:8602/webhooks/twilio/whatsapp/status`
- Production UI: `http://139.59.158.77:8501`
- Production API: `http://139.59.158.77:8601`

Staging deployment source:

```text
main branch via deploy/scripts/deploy_env.sh
```

Verify the exact server commit with:

```bash
git -C /opt/sales-cockpit/staging/app rev-parse --short HEAD
```

Production remains cold/mock until an explicit production cutover step.

Restore points are stored in:

```text
/opt/sales-cockpit/backups/staging/
```

## Current Integration Status

### Sales Cockpit

Working:

- Streamlit UI.
- FastAPI API.
- SQLite WAL.
- next-action workflow.
- conversation open/terminated state.
- WhatsApp 24h window enforcement.
- Twilio inbound and status callbacks.
- Twilio outbound code path with mock/sandbox/live support. Staging and production must stay in `mock` until explicit cutover.
- SchoolDrive snapshot ingest.
- Front read-only buffer import foundation.
- backup/restore scripts and cron.
- pre-cutover readiness check.

Latest recorded staging check:

```text
scripts/pre_cutover_check.py: OK
SchoolDrive: ready
Front: ready
Twilio: ready, mode mock
Backup: ready
Workflow: ready
open_conversations_without_action: 0
resolved_conversations_with_action_count: 0
conversations_with_multiple_main_actions: 0
```

### Twilio

Twilio Content API synchronization exists and is read-only by default:

```text
SALES_COCKPIT_TWILIO_CONTENT_READ_ONLY=true
```

This is intentional for the real ESSR Twilio account. Template synchronization may read Content API templates and upsert them locally, but Sales Cockpit blocks remote template creation and WhatsApp approval submission unless this flag is explicitly set to `false`.

Staging previously used the DEV WhatsApp sender:

```text
+41445054269
```

The DEV WhatsApp account has since been blocked by Meta, so do not rely on it for production validation. Production must stay in `mock` mode until explicit cutover.

Real ESSR templates should be synchronized from the real ESSR Twilio account in read-only mode. Do not change Twilio webhooks and do not send real WhatsApp messages from staging or production before the explicit "turn the key" decision.

### Template Mapping

Implemented and deployed in commit `f8e8a0b`.

- `sequence_template_mappings` links a follow-up sequence step to a real `whatsapp_templates` row.
- Mapping dimensions: `sequence_code`, `sequence_step_index`, `lead_type`, `course_category`.
- `all` is supported for lead type and course category.
- Pilotage > Flux par scénario lets admins assign approved Twilio templates while looking at the full message body.
- Admin > Flux still displays the technical mapping table.
- Only real Twilio templates approved by WhatsApp can be mapped. Draft, pending, rejected, local demo, and `HX_MOCK_*` templates are rejected.
- During a `follow_up` action, the Conversation tab displays the recommended template when a mapping matches the prospect.

This lets Laura map real Twilio templates to events such as "APP relance 3" without changing the core workflow.

Initial ESSR premapping was applied on staging and prod on 2026-06-20:

- script: `scripts/premap_sequence_templates.py`;
- scope: `FSM`, `APP`, `AS`;
- count: 75 mappings total, 25 per category;
- dimensions: `lead_type = all`, category-specific `course_category`;
- safety: only approved real Twilio templates with real `HX...` Content SIDs are accepted;
- note stored on mappings: `Pré-mapping IA à valider avec Laura.`;
- purpose: give Laura a strong starting point for fine-tuning, not lock the commercial decision.

Backups created immediately before the write:

- staging: `/opt/sales-cockpit/backups/staging/sales_cockpit_staging_20260620T133220Z.db.gz`;
- prod: `/opt/sales-cockpit/backups/prod/sales_cockpit_prod_20260620T133220Z.db.gz`.

Verification after premapping:

- staging: `APP=25`, `AS=25`, `FSM=25`, missing required follow-up mappings `0`;
- prod: `APP=25`, `AS=25`, `FSM=25`, missing required follow-up mappings `0`;
- staging `pre_cutover_check`: OK;
- prod API/UI/Twilio/Backup/Workflow checks: OK; prod readiness still warns that no SchoolDrive webhook has been received, which is expected until SchoolDrive prod is connected.

### Pilotage Page

Implemented in commit `6c48293`, then expanded in commit `f8e8a0b`.

`Pilotage` is an admin-only commercial tuning page for Laura. It keeps the existing technical Admin page intact, but exposes the workflow in a more human-readable way:

- overview of normal flows;
- active course categories handled by structured flows;
- default course sessions by category;
- editable sequence steps: action type, absolute offset from the flow trigger, meaning, active/inactive;
- scenario timelines by lead type, course category and sequence;
- full template message body, Twilio SID and template status for each step;
- approved template assignment by flow, step, lead type and course category;
- natural-language conflict rules;
- simple simulator for lead-relative and course-start timelines.

Default course sessions live in `course_default_sessions`. They are used as a planning layer when a SchoolDrive Lead has only a course category, for example `APP`, but no specific session or `start_date`. SchoolDrive data remains authoritative: if SchoolDrive provides a real session/start date, it wins over the default session.

Structured course categories live in `course_categories`. V1 seeds `FSM`, `APP`, and `AS`. If SchoolDrive sends a lead or presubscription with a sent WhatsApp for an unsupported category, Sales Cockpit still stores and displays the conversation, but it does not create the automated Tanjona relance flux. Instead it creates a human review action for Setter I/Mihary with trigger `unconfigured_course_category`.

V1 behavior: changing sequence steps or template mappings affects only newly created future sequences. Existing open tasks are not recalculated. V2 debt: add a controlled recalculation button.

Flux timing is expressed from the flow trigger, not from the previous step. Example: a lead no-reply flux can be `T+3j`, `T+6j`, `T+9j`, where `T` is the first automatic WhatsApp sent by SchoolDrive. Course-start reminders use the same model with `T-14j`, `T-7j`, etc., where `T` is the course start date.

If a step action type is `follow_up` / Relance WhatsApp, a template recommendation is operationally required. The UI shows the template selector directly on each scenario step and refuses mappings to non-approved, demo, pending, rejected, or draft templates.

### Parcours, Flux, Actions

Canonical model as of 2026-06-20:

- `Parcours` is the commercial state of the prospect: new lead, setter conversation, setting call planned, closing call planned, will sign, won, lost, etc. It is not user-editable in V1. The system changes it through workflow outcomes.
- `Flux` is a follow-up sequence: for example initial no-reply, setter exchange without next step, post-closing will-sign, or course-start reminders. Admins tune steps and templates in `Pilotage`; they do not create new business scenarios without code.
- `Action` is the operational unit shown in `Tâches`: reply, follow-up, document setting call, document closing call, contact review.

Important invariants:

- An open conversation normally has one active main next action.
- Exception: if a prospect writes while a setting/closing call is already planned, Sales Cockpit creates an urgent `reply` action but keeps the planned call active. After the user replies without changing the appointment, the planned call becomes the visible next action again.
- A planned setting/closing call means the future work is to document the call at the scheduled time. The call is visible in the conversation detail so Setter I or the closer knows an appointment already exists and can modify it in `Actions`.
- Course-start relances may replace a lead/presubscription relance when they conflict within 24h, but they must not replace an already planned setting/closing call.
- Course-start dates come first from SchoolDrive `data.course.start_date`; if a Lead only has a category, Sales Cockpit uses the active default session for that category.

### SchoolDrive

Validated:

- SchoolDrive can POST lead and presubscription snapshots to staging.
- Sales Cockpit accepts the payload, upserts the lead, creates/updates the conversation, stores SchoolDrive URLs, and materializes WhatsApp autoresponders in the thread.
- Sent autoresponder snapshots create a Tanjona follow-up at `sent_at + 72h`.
- The first sent SchoolDrive autoresponder is the anchor for the initial no-reply sequence. Later SchoolDrive autoresponders are stored in the thread but must not recreate the initial follow-up.
- Queued autoresponder snapshots do not create a follow-up.
- Archived records resolve the conversation and close actions.
- Duplicate and stale event handling works.

Important timestamp decision:

```text
KEEP_CURRENT_UTC
```

The SchoolDrive MCP currently returns naive timestamps that track UTC. Do not subtract two hours.

### Current SchoolDrive Gate

Historical note: Claude Code previously diagnosed `lead:124126` and proved that Sales Cockpit behaved correctly with a `queued` snapshot, but that SchoolDrive had not emitted a newer AR-sent snapshot for that record.

Tiago later reported that the SchoolDrive event projector was published, including a filter to skip leads/subscriptions created before `2026-03-01`. A previous staging run received a large historical replay; the latest recorded staging check after cleanup/rebuild is small again and suitable for focused validation.

Latest recorded staging state before this audit:

```text
schooldrive_events: accepted 6, ignored 1
schooldrive_leads: 4
workflow: open_conversations_without_action = 0
```

Production is still clean from SchoolDrive:

```text
schooldrive_events: 0
schooldrive_leads: 0
```

Required validation now:

```text
Fresh website form
-> SchoolDrive creates Lead or Presubscription
-> SchoolDrive sends automatic WhatsApp AR
-> AR reaches status=sent
-> SchoolDrive emits a newer webhook snapshot
-> Cockpit stores status=sent and sent_at
-> message body appears in thread
-> Tanjona follow-up is created at sent_at + 72h
-> pre_cutover_check remains OK
```

If this is not green, production may be prepared but must not become operational for the sales team.

### Live Test Pause Point

Status at 2026-06-20 10:29 Europe/Zurich:

- François submitted one real test presubscription from the website.
- Sales Cockpit staging did not receive any new SchoolDrive webhook event after the synthetic smoke events.
- Staging API logs showed no recent POST to `/webhooks/schooldrive/lead-or-presubscription`.
- SchoolDrive was expected to send an automatic WhatsApp, but it did not.
- Current working hypothesis: the SchoolDrive WhatsApp worker was off or not processing the new record.
- François was waiting for Tiago to restart/fix the SchoolDrive worker.

Resume the live test from here:

1. Confirm or observe that the SchoolDrive worker/projector is running.
2. Submit or inspect a fresh real Lead.
3. Check whether Sales Cockpit staging receives the first SchoolDrive snapshot.
4. Check whether SchoolDrive sends the automatic WhatsApp.
5. Check whether the AR-sent event reaches Sales Cockpit as a newer snapshot.
6. Confirm that the thread shows the WhatsApp body and that a Tanjona follow-up is created at `sent_at + 72h`.
7. Repeat the same path for a real presubscription if the Lead path works.

Do not change Twilio settings while resuming this test. The real ESSR Twilio account has only been read through the Content API; no Twilio webhook, sender, template, or send configuration should be changed until the explicit cutover decision.

## Production Gates

Production has two different meanings:

- **Prepared production**: clean prod DB, deployed code, SchoolDrive endpoint/token ready, Twilio templates synchronized locally in read-only mode, Front still operating.
- **Operational production**: sales team works in Sales Cockpit, WhatsApp webhooks/sending are switched away from Front.

Current rule:

```text
If AR-sent validation is not green, stop at prepared production.
Do not switch WhatsApp webhooks before HTTPS is in place.
```

## Front Status

Front is read-only and remains out of the critical path for production cutover.

Current staging buffer:

- 13 Front conversations.
- 159 Front messages.
- latest rematch: 11 unmatched, 1 ambiguous, 1 matched.
- matched row: `cnv_1mz0vz4w`, linked to `subscription:131887` / Lea Bucco.
- one known ambiguous phone case: `+41764599325`, duplicate lead/presubscription.

Do not block production cutover on full Front import. Keep Front read-only as historical fallback and migrate matched history progressively.

## Identity Review Guardrail

Implemented in commit `aae5808`.

Inbound WhatsApp matching is now conservative:

- exactly one phone match: attach automatically;
- zero phone matches: create a temporary `Inconnu(e)` record marked `À identifier`;
- multiple phone matches: create a temporary `Inconnu(e)` record marked `À identifier`, with candidate leads stored for review.

Users can fill temporary identity fields in `Statuts`:

- first name;
- last name;
- course category;
- course/session;
- identification note.

This data is operational only. SchoolDrive remains the source of truth.

V2 debt for proper identity resolution is documented in `docs/TECHNICAL_DEBT.md`.

## Immediate Next Steps

1. Keep the current small staging dataset unless a focused reset is needed for Laura's review.
2. Resume the live website-form test once SchoolDrive worker/projector activity is visible:
   - first snapshot received;
   - automatic WhatsApp sent;
   - AR-sent snapshot received;
   - autoresponder stored as `sent`;
   - Tanjona follow-up created.
3. Run staging `pre_cutover_check` again after the live website-form test.
4. If green, prepare production SchoolDrive projector config but do not activate operational traffic until explicit GO.
5. Keep Twilio production and SchoolDrive production cutover separate and controlled.

## Operating Lesson Learned

Do not say "we are waiting on Tiago" before classifying the blocker.

For each blocker, first decide:

- can Codex verify or fix it locally?
- can the existing Claude Code session verify it through MCP/server access?
- is it Sales Cockpit code?
- is it SchoolDrive producer/projector code?
- is it Twilio/Meta external state?
- is it a human permission/configuration task?

Only escalate to Tiago when the diagnosis proves that SchoolDrive-side code/configuration must change.

## Commands To Resume

Pre-cutover staging:

```bash
cd /opt/sales-cockpit/staging/app
set -a
source /opt/sales-cockpit/staging/.env
set +a
.venv/bin/python scripts/pre_cutover_check.py \
  --api-base http://127.0.0.1:8602 \
  --ui-url http://127.0.0.1:8502
```

Inspect recent SchoolDrive events:

```bash
sqlite3 /opt/sales-cockpit/staging/data/sales_cockpit.db
```

Useful SQL:

```sql
SELECT id,event_id,status,schooldrive_id,lead_id,received_at,
       json_array_length(json_extract(payload_json,'$.data.whatsapp_autoresponders')) AS wa_count,
       json_extract(payload_json,'$.data.whatsapp_autoresponders[0].message_id') AS wa_message_id,
       json_extract(payload_json,'$.data.whatsapp_autoresponders[0].status') AS wa_status,
       json_extract(payload_json,'$.data.whatsapp_autoresponders[0].sent_at') AS wa_sent_at
FROM schooldrive_webhook_events
ORDER BY id DESC
LIMIT 20;
```
