# Front.io Historical Import

## Goal

Front remains active until Sales Cockpit is validated. The Front import is read-only and exists only to recover historical WhatsApp conversations when the team is ready to migrate.

Imported Front messages should be treated as history, not as operational actions. Sales Cockpit actions continue to come from SchoolDrive webhooks, Twilio webhooks, and explicit user actions in the cockpit.

## Recommended Approach

1. Backfill SchoolDrive first so Sales Cockpit has the current lead and presubscription records.
2. Use Front's Core API to search or list conversations.
3. For each Front conversation, fetch its messages in chronological order.
4. Match the conversation to a Sales Cockpit lead using phone number first, then email, then manual review.
5. Store Front conversations and messages first in the dedicated `front_conversations` and `front_messages` buffer tables.
6. Attach imported messages to the Sales Cockpit thread only after validation, with channel `front_history`.
7. Preserve original Front IDs for idempotency before running any large import.

## API Surfaces

The current read-only client in `sales_cockpit/services/front_client.py` supports:

- `GET /conversations`
- `GET /conversations/search/{query}`
- `GET /conversations/{conversation_id}/messages`
- retry on `429 Too Many Requests` using `Retry-After` or Front's retry message when available.

Minimum Front scopes for API import:

- `conversations:read`
- `messages:read`

For bulk historical exports, Front also offers asynchronous analytics exports. That route can be useful for a large one-shot archive, but the Core API route is better for controlled lead-by-lead migration and debugging.

## Required Settings

```text
SALES_COCKPIT_FRONT_API_TOKEN=
SALES_COCKPIT_FRONT_IMPORT_QUERY=
SALES_COCKPIT_FRONT_IMPORT_INBOX_IDS=
```

`SALES_COCKPIT_FRONT_IMPORT_QUERY` can hold a default Front search query for a pilot import. `SALES_COCKPIT_FRONT_IMPORT_INBOX_IDS` can hold comma-separated inbox IDs once we know which Front inboxes contain the relevant WhatsApp conversations.

## Open Decisions

- Confirm the Front inbox IDs used by ESSR WhatsApp sales.
- Confirm whether Front stores the WhatsApp phone as `whatsapp:+...`, `+...`, or another handle format.
- Decide whether imported Front messages should appear by default in the conversation thread or behind a "historique importé" filter.
- Add durable idempotency fields before a large import, likely `front_conversation_id` on conversations and `front_message_id` on messages.
- Run a pilot on 5 to 10 conversations before importing all history.

## Current Status

Implemented:

- Read-only Front API client.
- Unit tests for pagination, search query encoding, message listing, and missing token handling.
- `scripts/front_dry_run.py`, which reads a small sample and prints JSON without writing to SQLite.
- Dry-run pagination now respects the requested `limit` before following Front's next-page cursor. This matters because Front rate limits aggressively.
- Staging dry-run has successfully read 1 Front conversation and 1 WhatsApp message with `writes: 0`.
- Front import pilot foundation:
  - phone extraction from Front WhatsApp subjects/handles;
  - exact phone matching against Sales Cockpit leads/conversations;
  - idempotent buffer storage in `front_conversations` and `front_messages`;
  - optional explicit attachment to the Sales Cockpit thread as `front_history`;
  - Admin > Intégrations shows the buffered Front records.
- `scripts/front_import_pilot.py`, which previews or stores a small controlled sample.

Not implemented yet:

- UI filter to show/hide attached Front history inside a conversation.
- Phone/email/manual matching review workflow for ambiguous or unmatched Front conversations.
- Full import command for all history.

## Dry-Run Command

Run locally or on staging with `SALES_COCKPIT_FRONT_API_TOKEN` configured:

```bash
python scripts/front_dry_run.py --limit 1
```

To fetch message samples too:

```bash
python scripts/front_dry_run.py --limit 1 --include-messages --messages-limit 5
```

To test a targeted Front search:

```bash
python scripts/front_dry_run.py --query "recipient:+41790000000" --limit 1 --include-messages
```

The dry-run has `writes: 0` by design. Do not add persistence until we have validated matching rules against real Front conversation shapes.

## Pilot Import Command

Preview matching without writing:

```bash
python scripts/front_import_pilot.py --limit 1 --include-messages --messages-limit 1
```

Store the pilot result in the Front buffer tables only:

```bash
python scripts/front_import_pilot.py --limit 1 --include-messages --messages-limit 1 --write
```

Attach matched messages to the Sales Cockpit thread as historical messages:

```bash
python scripts/front_import_pilot.py --limit 1 --include-messages --messages-limit 1 --write --attach-history
```

Do not use `--allow-large` until the small pilot has been reviewed in Admin > Intégrations.
