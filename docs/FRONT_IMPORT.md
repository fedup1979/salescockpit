# Front.io Historical Import

## Goal

Front remains active until Sales Cockpit is validated. The Front import is read-only and exists only to recover historical WhatsApp conversations when the team is ready to migrate.

Imported Front messages should be treated as history, not as operational actions. Sales Cockpit actions continue to come from SchoolDrive webhooks, Twilio webhooks, and explicit user actions in the cockpit.

## Recommended Approach

1. Backfill SchoolDrive first so Sales Cockpit has the current lead and presubscription records.
2. Use Front's Core API to search or list conversations.
3. For each Front conversation, fetch its messages in chronological order.
4. Match the conversation to a Sales Cockpit lead using phone number first, then email, then manual review.
5. Store imported messages with a dedicated historical channel, for example `front_history`.
6. Preserve original Front IDs for idempotency before running any large import.

## API Surfaces

The current read-only client in `sales_cockpit/services/front_client.py` supports:

- `GET /conversations`
- `GET /conversations/search/{query}`
- `GET /conversations/{conversation_id}/messages`

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

Not implemented yet:

- Database persistence for imported Front messages.
- UI filter for imported history.
- Production Front token configuration.
- Full import command.
