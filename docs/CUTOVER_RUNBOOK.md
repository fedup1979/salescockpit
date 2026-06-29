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
- Laura validates the final operational workflow with restored fake prospects, then with one real website lead and one real website presubscription.
- HTTPS is in place before the real WhatsApp webhook switch.

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
- `product` without `course` is treated as Roadmap/product-only and routed to human review, not the normal follow-up flow.

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
   - then with one real lead created from the website;
   - then with one real presubscription created from the website.

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
3. Run one last Front buffer import.
4. Review `active` Front conversations.
5. For each active matched Front conversation, decide the next operational handling in Sales Cockpit from the business context:
   - customer waiting for an answer: create a response action for the appropriate Setter I;
   - team waiting for the prospect: create or keep the appropriate structured relance for Setter II;
   - appointment already agreed: create the corresponding setting or closing call action;
   - unclear status: create a manual review with a note.

Controlled conversion from matched Front buffer rows exists via `scripts/front_convert_matched.py`, dry-run by default, with guards around existing open actions. It has not yet been validated for a large cutover. Until a reviewed conversion batch passes, create or assign these actions manually in Sales Cockpit.

## T0: Attach History

After review, attach matched Front messages as history:

```bash
python scripts/front_import_pilot.py --limit 10 --include-messages --messages-limit 100 --write --attach-history
```

Increase limits only after verifying the first batch.

Attached Front messages use:

```text
channel = front_history
```

They are historical context, not proof of a new Sales Cockpit action.

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

1. Point Twilio webhooks back to Front/Twilio's previous production routing.
2. Tell the sales team to resume Front.
3. Restore the latest pre-cutover backup if data pollution occurred:

```bash
sudo CONFIRM_RESTORE=1 bash /opt/sales-cockpit/prod/app/deploy/scripts/restore_sqlite.sh prod /path/to/backup.db.gz
```

4. Keep the failed Sales Cockpit logs for analysis before retrying.

## Open Items Before Real PROD Cutover

- HTTPS domain for production.
- Production environment variables and secrets.
- Real SchoolDrive AR-sent event trigger validation.
- Fresh staging validation of Tiago's schema `2.1` through the real website lead and presubscription paths, before the one-time full resync.
- Real ESSR Twilio template synchronization in read-only mode.
- Laura mapping of course/event/relance steps to real Twilio templates.
- Final Twilio production sender verification.
- Front full-history import batch sizing.
- UI filter for `front_history`.
- Reviewed conversion pilot for active Front buffer rows.
- Laura validation on restored fake prospects.
- Real website lead validation.
- Real website presubscription validation.
