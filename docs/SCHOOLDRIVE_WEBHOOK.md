# SchoolDrive Webhook

## Endpoint

```text
POST /webhooks/schooldrive/lead-or-presubscription
Authorization: Bearer <environment-token>
```

Staging URL:

```text
http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription
```

Production should use HTTPS before cutover.

## Implemented Contract

- Snapshot envelope with `schema_version`, `event_id`, `occurred_at`, `environment`, and `data`.
- Stable business key: `data.schooldrive_id`, for example `lead:137797` or `subscription:131885`.
- `data.status` is stored as `schooldrive_status`; it does not overwrite Sales Cockpit qualification.
- `data.url` is stored as `schooldrive_url` and used by the UI SchoolDrive link.

## Idempotency And Ordering

- Duplicate `event_id` returns `200` with `status: duplicate`.
- Accepted snapshots upsert `leads` by `schooldrive_lead_id`.
- A snapshot is accepted only if it is newer than the stored snapshot for the same `schooldrive_id`.
- Ordering key: `data.aggregated_updated_at`, then `occurred_at`, then `event_id`.
- Older snapshots are logged in `schooldrive_webhook_events` as `ignored / stale_snapshot`.

## WhatsApp Autoresponders

Accepted snapshots replace the stored SchoolDrive autoresponder list for the lead or presubscription.

Sales Cockpit accepts both the first draft field name `template` and the real SchoolDrive field name `short_name`. When SchoolDrive sends `whatsapp_send_body`, Sales Cockpit displays that exact rendered body in the conversation thread. The full WhatsApp autoresponder object, including `whatsapp_template_id` and `whatsapp_template_variables_mapping`, is preserved in `payload_json`.

Autoresponders are also materialized as outbound conversation messages with:

```text
channel = schooldrive_autoresponder
```

This makes the SchoolDrive WhatsApp history visible in the conversation thread without merging it with Cockpit-sent messages.

## Action Rule

If the accepted snapshot contains a sent autoresponder with `sent_at`, and no active action exists, the cockpit creates:

```text
type = follow_up
assigned_to = Tanjona
due_at = latest sent_at + 72h
sequence_code = lead_no_reply
sequence_step_index = 1
```

If no sent autoresponder exists yet, the cockpit waits for the next SchoolDrive snapshot instead of inventing a date.

If `is_archived` is true, the cockpit resolves the conversation, closes open actions, and adds an internal note.

## Replay Tool

Use `scripts/schooldrive_replay_payloads.py` to replay Tiago's JSON payloads against local, staging, or production.

Preview files without posting:

```bash
python scripts/schooldrive_replay_payloads.py payloads/schooldrive --dry-run --expected-environment staging
```

Replay against staging:

```bash
python scripts/schooldrive_replay_payloads.py payloads/schooldrive \
  --url http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription \
  --expected-environment staging \
  --stop-on-error
```

The script reads either individual `.json` files or a directory of `.json` files. A file may contain one JSON object or a JSON array of payload objects.

The summary reports:

- total payload count;
- successful vs failed POSTs;
- response status counts such as `created`, `updated`, `duplicate`, or `ignored`;
- per-payload `event_id`, `schooldrive_id`, `aggregated_updated_at`, HTTP status, and webhook response.

Do not replay production payloads into staging unless `environment` is explicitly set to `staging` or the `--expected-environment` guard is deliberately removed for a controlled test.
