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

- Snapshot envelope with `schema_version`, optional `event_id`, optional `occurred_at`, `environment`, and `data`. If `event_id` is absent, Sales Cockpit synthesizes a stable event id from `data.schooldrive_id`, `data.aggregated_updated_at`, and the effective `occurred_at`.
- Stable business key: `data.schooldrive_id`, for example `lead:137797` or `subscription:131885`.
- Schema `2.1` is supported. It is treated as an additive full snapshot contract. Each webhook is the latest full snapshot of one record, not a delta.
- Sales Cockpit upserts by `data.schooldrive_id` and accepts a snapshot only when `data.aggregated_updated_at` is newer than the stored version.
- `data.status` is stored as `schooldrive_status`; it does not overwrite Sales Cockpit qualification.
- `data.url` is stored as `schooldrive_url` and used by the UI SchoolDrive link.
- There is no separate SchoolDrive `session` entity for V1. The course is the session/class. Sales Cockpit uses `course.id` or legacy `course.course_id` as the stable course/session identifier and `course.short_name` or legacy `course.course_short_name` as the display identity when present.
- `data.course` accepts the original flat shape, the legacy schema `1.1` shape, and the schema `2.1` nested SchoolDrive shape.
- New nested course shape:
  - `course.id` or legacy `course.course_id` is stored as `course_id`;
  - `course.category_short_title` or `course.category.short_name` is stored as `course_category_short_title`;
  - `course.short_name` or legacy `course.course_short_name` is preferred as `course_title`, with fallbacks to `course.course_name`, `course.session_name`, `course.name`, `course.category.name`, then the category short name;
  - `course.start_date` may be either an ISO date (`YYYY-MM-DD`) or a full ISO UTC timestamp.
- Course capacity is read from `course.seats_total`, `course.seats_occupied`, `course.seats_available`, and `course.is_full`.
- Capacity is three-state: `seats_total = null` means there is no seat limit or no course yet. Sales Cockpit does not infer "full" from `seats_available` unless `seats_total` is present.
- `course.is_full = true` stops automatic follow-ups and keeps the capacity signal visible, without automatic admin review or alternate-session proposal.
- `data.signed = true` is the canonical signed/enrolled signal and stops follow-ups by marking the current Sales Cockpit lead as signed.
- `data.do_not_contact.blocked = true` is a hard commercial stop and sets the contact status to `do_not_contact`. `data.do_not_contact.reasons[]` may contain objects keyed by `type`; Sales Cockpit summarizes the reason type and opt-out group in the internal note while preserving the full raw payload.
- `data.related_subscriptions[]` is preserved in the raw payload. If a non-archived related subscription is already signed for the same category, Sales Cockpit stops competing same-category follow-ups without creating automatic admin review. Archived related subscriptions are ignored. The nested `related_subscriptions[].course` shape is supported.
- If `data.course` is absent and `data.product.roadmap_descriptive_id` is present, Sales Cockpit stores the roadmap identifier as an operational product title without starting a course-specific flux or automatic admin review.

## Timestamp Convention

Sales Cockpit expects all SchoolDrive webhook timestamps as ISO 8601 UTC.

Decision from the real SchoolDrive MCP replay on 2026-06-19: `KEEP_CURRENT_UTC`.

The SchoolDrive MCP currently returns timestamp fields that are already UTC, even when the raw value is naive text without a timezone suffix. Do not interpret current MCP naive timestamps as Europe/Zurich local time and do not subtract two hours.

Evidence from the live replay: the most recent MCP autoresponder `created_at` tracked real UTC within normal queue latency and was about two hours behind Europe/Zurich wall time. Applying a Zurich-to-UTC conversion to those MCP values would antedate records and can cause replays to be rejected as stale.

Producer rule:

- If a timestamp is timezone-aware (`Z` or an explicit offset), normalize it to UTC.
- If a timestamp comes from the current SchoolDrive MCP as naive text, treat it as UTC and add `Z`.
- Do not apply Europe/Zurich conversion to MCP values unless a future producer explicitly documents that a specific field is local time.

Tiago's earlier static example values that were two hours earlier than the MCP replay are treated as a producer/spec mismatch, not as the Cockpit replay convention.

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

## Historical AR-Sent Diagnostic And Current Live Gate

As of 2026-06-19 20:54 Europe/Zurich, the Sales Cockpit webhook contract was working, but the real SchoolDrive AR-sent producer path had not been validated.

Observed case:

```text
lead:124126
AR: armsg:1005384
Cockpit received status: queued
SchoolDrive MCP status: sent
Cockpit newer event after queued snapshot: none
```

This historical case means Sales Cockpit did not receive a fresh snapshot when that AR status changed to `sent`. Tiago later reported that the SchoolDrive projector was published, so the current gate is no longer this old record. The current gate is one fresh website-form validation proving this behavior:

```text
WhatsApp AR status changes to sent
-> SchoolDrive emits/projects a new lead/presubscription snapshot
-> payload includes status=sent and sent_at
-> Cockpit creates the Tanjona follow-up at sent_at + 72h
```

Do not treat the SchoolDrive integration as operational-production-ready until this fresh live path is validated.

## Action Rule

If the accepted snapshot contains a first sent autoresponder with `sent_at`, and no active action exists, the cockpit creates:

```text
type = follow_up
assigned_to = Tanjona
due_at = first sent_at + 72h
sequence_code = lead_no_reply
sequence_step_index = 1
```

If no sent autoresponder exists yet, the cockpit waits for the next SchoolDrive snapshot instead of inventing a date. Later sent SchoolDrive autoresponders are stored in the thread, but they must not recreate the initial no-reply follow-up once that initial follow-up has existed.

For new SchoolDrive records, the cockpit applies an operational guard before creating a lead/conversation:

- records with no usable identity are acknowledged and logged as ignored;
- records with no WhatsApp autoresponder yet are acknowledged and logged as ignored, because the operational clock starts only when the first WhatsApp is actually sent;
- records with only queued/sending/moderation-pending WhatsApp autoresponders are kept as waiting records, without action;
- records whose latest sent autoresponder is older than `SALES_COCKPIT_SCHOOLDRIVE_INGEST_MIN_SENT_AT` are acknowledged and logged as ignored when that environment variable is set;
- existing Cockpit records still accept newer SchoolDrive snapshots so their state can evolve normally.

This prevents a SchoolDrive historical backfill from creating thousands of open Cockpit conversations that have no current operational action. It also keeps the live path intact: if an initially ignored lead later receives a new snapshot with a sent WhatsApp, the cockpit can create the conversation and schedule the Tanjona follow-up at `sent_at + 72h`.

If `is_archived` is true, the cockpit resolves the conversation, closes open actions, and adds an internal note.

The waiting state is deliberate. A SchoolDrive record with no sent WhatsApp yet, or only a queued WhatsApp, does not create a Tanjona follow-up because the 72h clock starts from the sent timestamp. Admin > État reports these records separately as waiting for the first SchoolDrive WhatsApp instead of treating them as broken workflow conversations.

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

## Synthetic Smoke Test

Use `scripts/schooldrive_smoke.py` when Tiago's real payloads are not available yet, or after a deployment to verify that the webhook still behaves correctly. It generates synthetic records with unique SchoolDrive IDs and posts this sequence:

1. lead created with no WhatsApp yet;
2. same lead updated with one sent WhatsApp;
3. stale replay ignored;
4. duplicate event ignored;
5. presubscription with one sent WhatsApp;
6. presubscription with one queued WhatsApp;
7. presubscription created;
8. same presubscription archived.

Dry-run without posting:

```bash
python scripts/schooldrive_smoke.py --dry-run --environment staging
```

Run against staging from the droplet, using the token already stored in `/opt/sales-cockpit/staging/.env`:

```bash
cd /opt/sales-cockpit/staging/app
set -a
source /opt/sales-cockpit/staging/.env
set +a
.venv/bin/python scripts/schooldrive_smoke.py \
  --url http://127.0.0.1:8602/webhooks/schooldrive/lead-or-presubscription \
  --environment staging \
  --db-check
```

The expected response statuses are `created`, `updated`, `ignored`, `duplicate`, `created`, `created`, `created`, `updated`. The optional DB check verifies key side effects such as archived conversations being resolved and queued WhatsApp messages not creating an automatic follow-up.
