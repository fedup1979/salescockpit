# Sales Cockpit Cutover Runbook

This runbook describes the controlled migration from Front.io to Sales Cockpit.

## Principles

- SchoolDrive remains the source of truth for people, leads, presubscriptions, courses, and SchoolDrive URLs.
- Front is historical input. It should not create leads by itself.
- Front messages are imported first into buffer tables, then optionally attached as `front_history`.
- No production Twilio webhook is switched before SchoolDrive backfill, Front pilot import, backup, and manual validation are complete.
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
- Twilio WhatsApp sender for the production business is verified and approved.
- Twilio inbound webhook and status callback have been tested on staging.
- Front API read-only token is valid.
- Backup and restore scripts have been tested.
- Laura validates the final operational workflow with real or near-real staging examples.

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
   - archived SchoolDrive records are terminated;
   - Tanjona +72h follow-ups exist only when expected.

6. Run the automated pre-cutover check on the droplet:

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
5. For each active matched Front conversation, decide the next Sales Cockpit action:
   - latest customer message waiting: `reply`, usually Mihary;
   - latest team message waiting for prospect: `follow_up`, usually Tanjona;
   - unclear status: manual review.

Automatic conversion from Front buffer rows to Sales Cockpit actions is not implemented yet. Until it is implemented and tested, create or assign these actions manually in Sales Cockpit.

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

1. Point Twilio WhatsApp inbound webhook to the production API endpoint.
2. Point Twilio status callback to the production API endpoint.
3. Send one inbound test message.
4. Send one outbound approved template test if the WhatsApp window is closed.
5. Verify delivery status checks appear in Sales Cockpit.

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
- Final Twilio production sender verification.
- Front full-history import batch sizing.
- UI filter for `front_history`.
- Automatic conversion of active Front buffer rows into Sales Cockpit next actions.
- Laura validation on a real scenario set.
