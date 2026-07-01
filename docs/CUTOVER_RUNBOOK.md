# Sales Cockpit Cutover Runbook

This runbook describes the controlled migration from Front.io to Sales Cockpit.

## Principles

- SchoolDrive remains the source of truth for people, leads, presubscriptions, courses/classes, enrolments and SchoolDrive URLs.
- Front is historical input. It should not create leads by itself.
- Front messages are imported first into buffer tables, then optionally attached as `front_history`.
- The real ESSR Twilio account is read-only until explicit cutover. Template synchronization may read templates, but Sales Cockpit must not create, submit, delete, or send through the real account during staging validation.
- No production Twilio webhook is switched before SchoolDrive backfill, Front pilot import, backup, manual validation, and real website lead/presubscription tests are complete.
- Every active Sales Cockpit conversation must have one clear next action.

## Environments

- PROD UI: `http://139.59.158.77:8501`
- STAGING UI: `http://139.59.158.77:8502`
- DEV UI: `http://139.59.158.77:8503`
- STAGING API: `http://139.59.158.77:8602`

Production should use HTTPS before final cutover.

## Preconditions

- SchoolDrive production webhook URL and token are configured.
- SchoolDrive can backfill all active leads and presubscriptions.
- SchoolDrive emits a fresh webhook when a WhatsApp autoresponder status changes to `sent`; this must be validated with a real AR status-change event, not only with synthetic replay.
- SchoolDrive schema `2.1` semantics have been confirmed with Tiago: there is no separate session entity; `course.id` is the stable course/session identifier; capacity lives in every snapshot; `course.is_full` is the canonical full-course stop signal; capacity is three-state and `seats_total = null` means no seat limit/no course; `signed` is the canonical signature/enrolment signal; `do_not_contact.blocked` is the hard commercial stop; `do_not_contact.reasons[]` contains objects keyed by `type`; `related_subscriptions[]` carries other subscriptions for the same person with nested `course`; each webhook is an upsert keyed by `schooldrive_id` and ordered by `aggregated_updated_at`.
- Staging has been cleaned after any historical event replay and rebuilt with records created on or after 2026-03-01.
- Twilio WhatsApp sender for the production business is verified and approved.
- Twilio templates from the real ESSR account are synchronized locally with `SALES_COCKPIT_TWILIO_CONTENT_READ_ONLY=true`.
- Every mapped follow-up step has an approved real Twilio Content SID (`HX...`, not `HX_MOCK_*`).
- `SALES_COCKPIT_API_TOKEN` is configured for staging/prod.
- `SALES_COCKPIT_MOCK_WEBHOOK_TOKEN` is configured if JSON mock webhooks are used outside local tests.
- Production runs with `SALES_COCKPIT_SEED_DEMO_DATA=false`.
- Production Twilio mode remains `mock` until the final switch, then must be `live` with HTTPS inbound and status callback URLs.
- Front API read-only token is valid.
- Backup and restore scripts have been tested.
- Laura validates the final operational workflow with restored fake prospects, then with one real website lead and one real website presubscription. In a full test battery requested by François, the two real ESSR website submissions are mandatory and must use the indicated URLs and test emails; those test submissions are automatically deleted by the system afterward.
- HTTPS is in place before the real WhatsApp webhook switch.

## Audited Baseline Before PROD Preparation

Latest audit: 2026-06-30 18:14 Europe/Zurich.

- Staging is deployed on `ae9b832`.
- Production is still deployed on `786f89c`, cold/mock, with an older DB schema.
- Production backup already created for this preparation pass: `/opt/sales-cockpit/backups/prod/sales_cockpit_prod_20260630T161112Z.db.gz` plus `.sha256`.
- Production cold check on the current prod code passed with `--allow-cold-prod`.
- Production data is still empty: no SchoolDrive leads/events/autoresponders, no Front conversations/messages, no active tasks, no demo leads.
- Staging template mappings are the validated source of truth: `78` active mappings, `APP=26`, `AS=26`, `FSM=26`, all linked to approved real Twilio Content SIDs.
- Production still has the older `75` active mappings, `APP=25`, `AS=25`, `FSM=25`.
- Running the latest `--strict-prod` against the current prod DB is expected to fail before migration because prod lacks the latest capacity columns.

Mapping freeze rule:

- Do not run `scripts/premap_sequence_templates.py` during cutover.
- Do not create, submit, delete, or edit Twilio templates during cutover.
- Do not change staging mappings; staging is the source of truth validated by François/Laura.
- Do not hand-edit production mappings in Pilotage during cutover.
- If production mappings are not aligned, copy the validated local mapping rows from staging to prod by `whatsapp_templates.twilio_content_sid`, never by local template `id`.

## Confirmation To Tiago

Send this confirmation before Tiago publishes schema `2.1`:

```text
Hi Tiago,

Thanks, this schema 2.1 shape works for Sales Cockpit V1.

We confirm both points:

- We will consume capacity directly from the existing lead/presubscription snapshot, using `course.is_full` as the canonical stop signal. We will treat capacity as three-state: `seats_total = null` means no seat limit or no course, not "seats available". No separate capacity event is needed.
- We will treat each webhook as a full snapshot upsert keyed by `data.schooldrive_id`, with `data.aggregated_updated_at` as the version/order key. Older snapshots will be ignored.

We will also adopt the SchoolDrive mental model you described:

- no separate session entity; `course.id` is the stable session/class/course identifier and `course.short_name` is the display identity;
- top-level `signed` is the canonical enrolment signal;
- `do_not_contact.blocked = true` is a hard stop on commercial sends, and `do_not_contact.reasons[]` is an array of objects keyed by `type`;
- `related_subscriptions[]` with nested `course` will be used to prevent duplicate or competing follow-up flows;
- `product` without `course` is treated as Roadmap/product-only: store and display it, but start no normal follow-up flow and no automatic admin review.

You can publish schema `2.1` to staging.
```

## T-2 Or Earlier: Prepare

1. Deploy latest code to staging.
2. Run automated tests locally:

```bash
python -m pytest
python -m compileall sales_cockpit scripts tests
```

3. Ask SchoolDrive to send or replay real staging payloads.
4. Replay payloads if files are provided:

```bash
python scripts/schooldrive_replay_payloads.py payloads/schooldrive \
  --url http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription \
  --expected-environment staging \
  --stop-on-error
```

5. Verify in staging:
   - leads and presubscriptions exist;
   - SchoolDrive links open correctly;
   - sent autoresponders appear in the thread;
   - queued autoresponders do not create follow-ups;
   - a real AR changing to `sent` produces a new webhook and creates the Setter II +72h follow-up;
   - archived SchoolDrive records are terminated;
   - Setter II +72h follow-ups exist only when expected;
   - Pilotage > Flux par scénario can map a real Twilio template to each follow-up step and the Conversation tab shows the recommended template for a matching relance.

6. Run the manual V1 protocol in `docs/TEST_PLAN.md`:
   - first with restored fake prospects;
   - then with one real lead created from the indicated ESSR website URL and test email;
   - then with one real presubscription created from the indicated ESSR website URL and test email.

7. Run the automated pre-cutover check on the droplet:

```bash
cd /opt/sales-cockpit/staging/app
set -a
source /opt/sales-cockpit/staging/.env
set +a
.venv/bin/python scripts/pre_cutover_check.py \
  --api-base http://127.0.0.1:8602 \
  --ui-url http://127.0.0.1:8502
```

The check must pass before a cutover rehearsal. For cold PROD preparation only, `--allow-cold-prod` can be used to avoid failing simply because SchoolDrive and Front have not been connected yet.

Immediately before switching real WhatsApp routing, run the strict production check against public HTTPS endpoints:

```bash
cd /opt/sales-cockpit/prod/app
set -a
source /opt/sales-cockpit/prod/.env
set +a
.venv/bin/python scripts/pre_cutover_check.py \
  --strict-prod \
  --api-base https://<prod-api-domain> \
  --ui-url https://<prod-ui-domain>
```

`--strict-prod` is intentionally unforgiving. It must fail if production is not in `prod/production`, if demo seed data is enabled, if API/SchoolDrive/Twilio secrets are missing or placeholder-like, if Twilio is not live, if callbacks are not HTTPS, if the latest backup is missing/stale, if blocked actions or pending template requests remain, or if required follow-up template mappings are missing.

## T-1: Prepare PROD Cold

This prepares production code and local data while keeping Twilio in `mock`. It is not the WhatsApp cutover.

1. Create a fresh production backup and keep the path/checksum:

```bash
sudo bash /opt/sales-cockpit/prod/app/deploy/scripts/backup_sqlite.sh prod
```

2. Deploy the target code to production. This also runs `scripts/init_db.py`, which applies the latest idempotent schema migrations:

```bash
REPO_URL=git@github.com:fedup1979/salescockpit.git BRANCH=main \
  bash /opt/sales-cockpit/prod/app/deploy/scripts/deploy_env.sh prod
```

3. Verify production is on the expected commit and services are active:

```bash
git -C /opt/sales-cockpit/prod/app rev-parse --short HEAD
systemctl is-active sales-cockpit-ui@prod.service
systemctl is-active sales-cockpit-api@prod.service
```

4. Keep production Twilio safe:

```bash
grep -E 'SALES_COCKPIT_ENVIRONMENT|SALES_COCKPIT_TWILIO_MODE|SALES_COCKPIT_TWILIO_CONTENT_READ_ONLY|SALES_COCKPIT_SEED_DEMO_DATA' \
  /opt/sales-cockpit/prod/.env
```

Expected cold-prep posture: `SALES_COCKPIT_ENVIRONMENT=prod`, `SALES_COCKPIT_TWILIO_MODE=mock`, `SALES_COCKPIT_TWILIO_CONTENT_READ_ONLY=true`, `SALES_COCKPIT_SEED_DEMO_DATA=false`.

5. Run the cold production check:

```bash
cd /opt/sales-cockpit/prod/app
set -a
source /opt/sales-cockpit/prod/.env
set +a
.venv/bin/python scripts/pre_cutover_check.py \
  --api-base http://127.0.0.1:8601 \
  --ui-url http://127.0.0.1:8501 \
  --allow-cold-prod
```

6. Align production mappings from the validated staging mappings. This is local DB mapping data only; it does not call Twilio and does not edit `whatsapp_templates`.

Dry run first:

```bash
cd /opt/sales-cockpit/prod/app
.venv/bin/python scripts/sync_sequence_template_mappings.py \
  --source-db /opt/sales-cockpit/staging/data/sales_cockpit.db \
  --target-db /opt/sales-cockpit/prod/data/sales_cockpit.db \
  --expected-active-count 78 \
  --expected-split APP=26 \
  --expected-split AS=26 \
  --expected-split FSM=26
```

If the dry run reports missing Twilio SIDs in prod, stop. First resynchronize Twilio Content into prod in read-only mode; do not insert templates by hand.

Apply only after the dry run is understood:

```bash
cd /opt/sales-cockpit/prod/app
.venv/bin/python scripts/sync_sequence_template_mappings.py \
  --source-db /opt/sales-cockpit/staging/data/sales_cockpit.db \
  --target-db /opt/sales-cockpit/prod/data/sales_cockpit.db \
  --expected-active-count 78 \
  --expected-split APP=26 \
  --expected-split AS=26 \
  --expected-split FSM=26 \
  --apply
```

Do not pass `--deactivate-extra` during normal cutover unless a reviewed diff proves prod has obsolete active mappings that must be mirrored away.

7. Validate production mapping counts:

```bash
sqlite3 /opt/sales-cockpit/prod/data/sales_cockpit.db "
SELECT COUNT(*) AS active_real
FROM sequence_template_mappings stm
JOIN whatsapp_templates wt ON wt.id = stm.template_id
WHERE stm.active = 1
  AND wt.status = 'approved'
  AND wt.twilio_content_sid LIKE 'HX%'
  AND wt.twilio_content_sid NOT LIKE 'HX_MOCK_%';

SELECT stm.course_category, COUNT(*)
FROM sequence_template_mappings stm
JOIN whatsapp_templates wt ON wt.id = stm.template_id
WHERE stm.active = 1
  AND wt.status = 'approved'
  AND wt.twilio_content_sid LIKE 'HX%'
  AND wt.twilio_content_sid NOT LIKE 'HX_MOCK_%'
GROUP BY stm.course_category
ORDER BY stm.course_category;

PRAGMA foreign_key_check;
"
```

Expected result: `78` active real mappings, `APP=26`, `AS=26`, `FSM=26`, and no foreign-key issue.

Pilotage alignment as of 2026-07-01 11:00:

- Production Pilotage was mirrored from staging and verified identical for `whatsapp_templates`, `sequences`, `sequence_steps`, `course_categories`, `course_default_sessions`, and `sequence_template_mappings`.
- `lead_no_reply` step 3 AS uses `as_3_echeance_offre_450_francs` / `HX5e48dc8cbc78d0f20ee2d3391b447182`, `approved`, `T+18j`, `follow_up`.
- `relance_temoignage_as_3` / `HXbf6f0daf2b5fcb5b1ac94eb21beeadc7` is on `setter_no_next_step` step 3, which is `manual_reprise_setter` with `requires_template=0`; it is not a strict live send blocker after alignment.

## T-1: Front Buffer Import

1. Preview a tiny Front sample:

```bash
python scripts/front_import_pilot.py --limit 1 --include-messages --messages-limit 1
```

2. Store a small buffer sample:

```bash
python scripts/front_import_pilot.py --limit 5 --include-messages --messages-limit 20 --write
```

3. Review Admin > Intégrations:
   - `matched`: can be considered for history attachment;
   - `unmatched`: usually means missing SchoolDrive backfill or phone mismatch;
   - `ambiguous`: requires manual review;
   - `active`: candidate for a Sales Cockpit next action;
   - `resolved`: historical only;
   - `manual_review`: no automatic action.

4. Do not use `--attach-history` until the buffer sample is reviewed.

## T-1: Backup

Create a backup before any production cutover or large import:

```bash
sudo bash /opt/sales-cockpit/prod/app/deploy/scripts/backup_sqlite.sh prod
```

Keep the backup path and checksum in the deployment notes.

Automated daily backups should already be installed:

```bash
sudo bash /opt/sales-cockpit/staging/app/deploy/scripts/install_backup_cron.sh
```

## T0: Freeze Front

1. Tell the sales team to stop sending WhatsApp messages from Front.
2. Keep Front available read-only.
3. Run the final Front transition import with a new final `import_run_id`.
4. Review open transition conversations in Sales Cockpit.
5. For each active Front transition conversation, handle it outside V1 flows:
   - customer waiting for an answer: answer from the Conversation tab;
   - team waiting for the prospect: schedule `front_transition_follow_up` for Setter II;
   - appointment already agreed: create the corresponding setting or closing call action manually;
   - unclear status: keep or close the transition review with a note.

Use:

```bash
python scripts/front_transition_import.py --limit 200 --messages-limit 500 --allow-large --import-run-id front-transition-final-01 --write --json
```

Increase the batch size only after the previous batch has completed and the task counts look coherent.

## T0: Transition History

Front transition import attaches messages directly as history:

```text
lead source = front_transition
conversation channel = whatsapp_front_transition
message channel = front_history
open task = front_transition_review or front_transition_follow_up
```

They are historical context and manual transition work, not proof of a new V1 Sales Cockpit action.

If the rehearsal import must be removed before the final freeze:

```bash
python scripts/front_transition_purge.py --import-run-id front-transition-dryrun-01 --yes --json
```

## T0: Switch Twilio

Only after the above checks pass:

0. Confirm `--strict-prod` passes.
1. Confirm HTTPS endpoints for production.
2. Point Twilio WhatsApp inbound webhook to the production API endpoint.
3. Point Twilio status callback to the production API endpoint.
4. Send one inbound test message.
5. Send one outbound approved template test if the WhatsApp window is closed.
6. Verify delivery status checks appear in Sales Cockpit.

## T+1: Monitor

Check:

- webhook errors;
- Twilio delivery statuses;
- unmatched Front records;
- active conversations without next action;
- bug reports;
- user activity logs.

## Rollback

Rollback means returning the team to Front and restoring the Sales Cockpit database if necessary.

Detailed emergency procedure: `docs/FRONT_EMERGENCY_ROLLBACK.md`.

1. Point Twilio webhooks back to Front/Twilio's previous production routing.
2. Tell the sales team to resume Front.
3. Set production Sales Cockpit back to Twilio `mock` if it had been switched to `live`, then restart prod services.
4. Restore the latest pre-cutover backup if data pollution occurred:

```bash
sudo CONFIRM_RESTORE=1 bash /opt/sales-cockpit/prod/app/deploy/scripts/restore_sqlite.sh prod /path/to/backup.db.gz
```

5. Do not modify staging mappings or Twilio templates during rollback.
6. Keep the failed Sales Cockpit logs for analysis before retrying.

## Open Items Before Real PROD Cutover

- HTTPS domain for production.
- Production environment variables and secrets.
- Real SchoolDrive AR-sent event trigger validation.
- Fresh staging validation of Tiago's schema `2.1` through the real website lead and presubscription paths, before the one-time full resync.
- Real ESSR Twilio template synchronization in read-only mode.
- Align production to the validated staging mappings: `78` active real mappings, `APP=26`, `AS=26`, `FSM=26`, matched by Twilio Content SID.
- Re-check Pilotage equality if any staging tuning changes after 2026-07-01 11:00.
- Capture the current Front Twilio inbound webhook and status callback before changing Twilio Console, so rollback is immediate.
- Final Twilio production sender verification.
- Front full-history import batch sizing.
- UI filter for `front_history`.
- Reviewed conversion pilot for active Front buffer rows.
- Laura validation on restored fake prospects.
- Real website lead validation.
- Real website presubscription validation.
