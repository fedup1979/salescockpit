# Front Emergency Rollback

Last updated: 2026-07-01 11:00 Europe/Zurich.

This is the emergency procedure if the WhatsApp cutover to Sales Cockpit causes a major incident and ESSR must return to Front quickly.

## Current Safe State

- Production app commit prepared cold: `c5d1c04`.
- Production Twilio mode is still `mock`.
- Production Twilio Content is still read-only.
- No Twilio webhook has been changed by this preparation.
- Latest production backup before Pilotage alignment: `/opt/sales-cockpit/backups/prod/sales_cockpit_prod_20260701T085356Z.db.gz`.

## Information To Capture Before Turning The Key

Do this before changing any Twilio webhook:

- Current Twilio inbound webhook URL used by Front.
- Current Twilio status callback URL used by Front, if any.
- Twilio sender or Messaging Service SID used by ESSR WhatsApp production.
- Screenshot of the Twilio Console page before changing it.
- Name of the person executing the Twilio Console change.
- Confirmation that Front is still accessible and the sales team knows how to resume there.

Without the old Front webhook URLs, rollback is slower because the team must rediscover the previous Twilio routing under pressure.

## Immediate Rollback

Use this if live traffic is broken, messages stop arriving, outbound sends fail broadly, or the team cannot operate.

1. Stop Sales Cockpit from sending real WhatsApp messages.

```bash
sudo cp /opt/sales-cockpit/prod/.env /opt/sales-cockpit/prod/.env.rollback.$(date -u +%Y%m%dT%H%M%SZ)
sudo sed -i 's/^SALES_COCKPIT_TWILIO_MODE=.*/SALES_COCKPIT_TWILIO_MODE=mock/' /opt/sales-cockpit/prod/.env
sudo systemctl restart sales-cockpit-api@prod.service sales-cockpit-ui@prod.service
```

2. In Twilio Console, restore the previous Front routing:

```text
Inbound webhook: <FRONT_INBOUND_WEBHOOK_URL_CAPTURED_BEFORE_CUTOVER>
Status callback: <FRONT_STATUS_CALLBACK_URL_CAPTURED_BEFORE_CUTOVER>
```

3. Tell the sales team to resume WhatsApp work in Front.

4. Verify that Sales Cockpit is no longer live:

```bash
grep -E 'SALES_COCKPIT_TWILIO_MODE|SALES_COCKPIT_TWILIO_WEBHOOK_URL|SALES_COCKPIT_TWILIO_STATUS_CALLBACK_URL' /opt/sales-cockpit/prod/.env
curl -fsS http://127.0.0.1:8601/health
```

Expected: Twilio mode is `mock`.

5. Watch logs for errors that still arrive after the webhook rollback:

```bash
journalctl -u sales-cockpit-api@prod.service -n 200 --no-pager
journalctl -u sales-cockpit-ui@prod.service -n 100 --no-pager
```

## Restore Database If Needed

Only restore the database if Sales Cockpit created polluted operational data during the failed live window. Do not restore automatically if the only problem was Twilio routing and Front is working again.

```bash
sudo CONFIRM_RESTORE=1 bash /opt/sales-cockpit/prod/app/deploy/scripts/restore_sqlite.sh \
  prod \
  /opt/sales-cockpit/backups/prod/sales_cockpit_prod_20260701T085356Z.db.gz
```

After restore:

```bash
sudo systemctl restart sales-cockpit-api@prod.service sales-cockpit-ui@prod.service
cd /opt/sales-cockpit/prod/app
set -a
source /opt/sales-cockpit/prod/.env
set +a
.venv/bin/python scripts/pre_cutover_check.py \
  --api-base http://127.0.0.1:8601 \
  --ui-url http://127.0.0.1:8501 \
  --allow-cold-prod
```

## Do Not Do During Rollback

- Do not edit staging mappings.
- Do not create or submit Twilio templates.
- Do not retry the cutover before logs and failed messages are reviewed.
- Do not restore the DB if the incident is only external Twilio routing and no Sales Cockpit data pollution occurred.

## Current Pre-Live State

As of 2026-07-01 11:00, production Pilotage mirrors staging. `lead_no_reply` step 3 AS uses the approved template validated in staging:

```text
Template: as_3_echeance_offre_450_francs
SID: HX5e48dc8cbc78d0f20ee2d3391b447182
Flux: lead_no_reply step 3, AS, follow_up, T+18j
```

`--strict-prod` is still expected to fail until live prerequisites are configured: HTTPS URLs, SchoolDrive prod token, Twilio prod credentials, Twilio live mode, sender/service SID, and HTTPS callbacks.
