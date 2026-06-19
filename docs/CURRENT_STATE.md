# Current Project State

Last updated: 2026-06-19 20:54 Europe/Zurich.

This is the first document to read when resuming Sales Cockpit.

## Executive Summary

Sales Cockpit is deployed and running in staging on DigitalOcean. The staging app is connected to a real Twilio DEV WhatsApp sender in `live` mode with a strict recipient allowlist. Production is deployed cold and remains in Twilio `mock` mode.

The main remaining blocker before production cutover is not in Sales Cockpit. It is the SchoolDrive projector trigger for WhatsApp autoresponder status changes: when an AR message changes from `queued` to `sent`, SchoolDrive must emit a new snapshot to Sales Cockpit.

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

Latest verified functional deployment before this documentation update:

```text
aae5808 Add inbound identity review guardrail
```

Staging and cold production were both verified on this commit before the documentation-only update.

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
- Twilio outbound through DEV sender, guarded by recipient allowlist.
- SchoolDrive snapshot ingest.
- Front read-only buffer import foundation.
- backup/restore scripts and cron.
- pre-cutover readiness check.

Latest known staging check:

```text
scripts/pre_cutover_check.py: OK
SchoolDrive: ready
Front: ready
Twilio: ready
Backup: ready
Workflow: ready
open_conversations_without_action: 0
```

### Twilio

Staging is live with the DEV WhatsApp sender:

```text
+41445054269
```

Outbound staging is protected by:

```text
SALES_COCKPIT_TWILIO_ALLOWED_RECIPIENTS=+41762845576
```

Production is still in `mock` mode and must remain untouched until explicit cutover.

Real Twilio templates are synchronized, but the DEV account currently has no approved real WhatsApp template. Closed-window template sending cannot be fully validated until at least one real template is approved.

### SchoolDrive

Validated:

- SchoolDrive can POST lead and presubscription snapshots to staging.
- Sales Cockpit accepts the payload, upserts the lead, creates/updates the conversation, stores SchoolDrive URLs, and materializes WhatsApp autoresponders in the thread.
- Sent autoresponder snapshots create a Tanjona follow-up at `sent_at + 72h`.
- Queued autoresponder snapshots do not create a follow-up.
- Archived records resolve the conversation and close actions.
- Duplicate and stale event handling works.

Important timestamp decision:

```text
KEEP_CURRENT_UTC
```

The SchoolDrive MCP currently returns naive timestamps that track UTC. Do not subtract two hours.

### Current SchoolDrive Blocker

Claude Code completed a pure observation diagnostic on `lead:124126`.

Observed SchoolDrive AR:

```text
lead:124126
person: Lydia Djouhri
AR: armsg:1005384
autoresponder: MKT-FSM-LN-BT-01
SchoolDrive status: sent
SchoolDrive status_updated_at: 2026-05-29 05:55:03 UTC
```

Observed Cockpit staging:

```text
latest event for lead:124126: 6e677339-8068-406c-879e-926b6a7a6824
received_at: 2026-06-19T18:47:37Z
stored AR status: queued
stored sent_at: null
newer events after that: 0
open tasks: 0
```

Verdict:

```text
Automatic AR-sent path is not validated.
```

Sales Cockpit is behaving correctly for the snapshot it received. It stored the AR as queued and did not create a follow-up. The blocker is SchoolDrive/projector side: the AR is sent in SchoolDrive, but no newer snapshot with `status=sent` and `sent_at` reached Sales Cockpit.

Required SchoolDrive-side fix:

```text
When a WhatsApp autoresponder message changes status to sent,
SchoolDrive must emit/project a new lead/presubscription snapshot to Sales Cockpit.
```

After that fix, the validation target is:

```text
AR sent in SchoolDrive
-> new webhook event reaches Cockpit
-> Cockpit stores status=sent and sent_at
-> message body appears in thread
-> Tanjona follow-up is created at sent_at + 72h
-> pre_cutover_check remains OK
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

1. Get the SchoolDrive AR-sent event trigger/projector fixed or deployed.
2. Validate the real automatic path with `lead:124126` or another fresh AR:
   - SchoolDrive AR status is `sent`;
   - Sales Cockpit receives a newer event;
   - autoresponder is stored as `sent`;
   - Tanjona follow-up is created.
3. Run staging `pre_cutover_check`.
4. If green, prepare production SchoolDrive projector config but do not activate until explicit GO.
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
