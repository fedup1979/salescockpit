# Front.io Historical Import

## Goal

Front remains active until Sales Cockpit is validated. The Front import is read-only and exists only to recover historical WhatsApp conversations when the team is ready to migrate.

Imported Front messages should be treated as transition history, not as V1 SchoolDrive workflow input. Sales Cockpit V1 actions continue to come from SchoolDrive webhooks, Twilio webhooks, and explicit user actions in the cockpit.

## Recommended Approach

1. Use Front's Core API to search or list conversations.
2. For each Front conversation, fetch its messages in chronological order.
3. Group conversations by normalized WhatsApp phone number; if no phone is available, keep one group per Front conversation.
4. Import each group as a synthetic Sales Cockpit transition thread with `source = front_transition`.
5. Store the raw Front records in `front_conversations` and `front_messages`, with the batch `import_run_id`.
6. Attach imported messages to the transition thread as `front_history`.
7. Keep every imported transition thread outside V1 flows (`APP/FSM/AS` sequences are not triggered by the import).

## Migration Classification

The Front buffer stores a migration recommendation for every Front conversation:

| Front status / signal | Buffer `migration_status` | Recommended action |
|---|---:|---|
| `assigned`, `unassigned`, `open`, `waiting`, `pending` + latest inbound customer message | `active` | `reply` |
| `assigned`, `unassigned`, `open`, `waiting`, `pending` + latest outbound team message | `active` | `follow_up` |
| `archived`, `resolved`, `closed`, `deleted`, `spam` | `resolved` | none |
| unknown status or no exploitable message | `manual_review` | none |

This legacy buffer classification is intentionally conservative. It does not create Sales Cockpit actions by itself. The current cutover approach does not convert matched Front rows into V1 actions automatically.

The legacy matched-conversion behavior was:

- `active` + `reply`: Sales Cockpit conversation active, next action `Répondre au message`, usually assigned to Mihary.
- `active` + `follow_up`: Sales Cockpit conversation active, next action `Envoyer relance` or manual review, usually assigned to Tanjona.
- `resolved`: Sales Cockpit history visible, conversation terminated, no next action.
- `manual_review`: no automatic migration; admin review required.

## Transition Import Behavior

The current cutover behavior is deliberately simpler:

- all imported Front threads get `source = front_transition` and `lead_type = front_transition`;
- active Front groups create one `front_transition_review` task, assigned to Setter I;
- archived/resolved Front groups are imported as resolved history only, with no task;
- several Front conversations with the same phone are merged into one Sales Cockpit transition conversation;
- no imported Front conversation is matched to a SchoolDrive V1 flow;
- no `reply` or V1 `follow_up` is created by the import;
- a setter can respond from the Conversation tab or close the transition with a required note;
- a setter can schedule `front_transition_follow_up`, assigned to Setter II, with no `sequence_code`;
- if a prospect replies on an open transition thread, Sales Cockpit creates or updates `front_transition_review`, not a V1 `reply`;
- every run can be purged by `import_run_id` before the final cutover import.

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
- Staging pilot has stored 2 Front conversations and 2 Front messages in the buffer tables, with 0 attached operational messages. Both samples were unmatched because SchoolDrive staging data did not yet contain those phone numbers.
- Front import pilot foundation:
  - phone extraction from Front WhatsApp subjects/handles;
  - exact phone matching against Sales Cockpit leads/conversations;
  - conservative migration classification into `active`, `resolved`, or `manual_review`;
  - idempotent buffer storage in `front_conversations` and `front_messages`;
  - optional explicit attachment to the Sales Cockpit thread as `front_history`;
  - Admin > Intégrations shows the buffered Front records.
- `scripts/front_import_pilot.py`, which previews or stores a small controlled sample.
- `scripts/front_cutover_plan.py`, which reads the buffer and produces a conservative read-only cutover plan.
- `scripts/front_rematch_buffer.py`, which recomputes buffered Front matches after a later SchoolDrive backfill.
- `scripts/front_convert_matched.py`, which can convert only `matched` + `active` buffer rows into Sales Cockpit actions. It is dry-run by default and skips existing open actions unless explicitly told to replace them.
- `scripts/front_transition_import.py`, which imports Front conversations as manual transition threads outside V1 flows. It is dry-run by default.
- `scripts/front_transition_purge.py`, which purges one transition import run by `import_run_id`.

Latest staging pilot:

- 13 Front conversations buffered.
- 159 Front messages buffered.
- After the latest SchoolDrive MCP backfill and rematch: 11 conversations are `unmatched`, 1 is `ambiguous`, and 1 is `matched`.
- The matched row is `cnv_1mz0vz4w`, phone `+33669502201`, linked to `subscription:131887` / Lea Bucco.
- 11 matched Front messages were attached as `front_history`.
- Conversion dry-run skipped the matched row because that lead already has an open `follow_up` action.

Not implemented yet:

- UI filter to show/hide attached Front history inside a conversation.
- Phone/email/manual matching review workflow for ambiguous or unmatched Front conversations.

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

## Cutover Plan Command

Build a read-only plan from the Front buffer:

```bash
python scripts/front_cutover_plan.py --limit 500
```

Full JSON output:

```bash
python scripts/front_cutover_plan.py --limit 500 --json
```

The plan is deliberately conservative:

- `ready_to_convert`: matched active Front conversation with a clear recommended action (`reply` or `follow_up`);
- `history_only`: matched resolved Front conversation, import as history only;
- `manual_review`: unmatched, ambiguous, or unclear Front conversation.

This command does not create actions and does not attach messages. It is safe to run before Tiago's SchoolDrive backfill, but most records will remain `manual_review` until SchoolDrive has populated the matching phone numbers.

## Rematch And Conversion Commands

After a SchoolDrive backfill, recompute Front matches without calling Front again:

```bash
python scripts/front_rematch_buffer.py --limit 500
```

Preview conversion of matched active Front rows into Sales Cockpit actions:

```bash
python scripts/front_convert_matched.py --limit 500
```

Execute conversion only after reviewing the dry-run output:

```bash
python scripts/front_convert_matched.py --limit 500 --execute
```

By default, conversion skips leads that already have an open next action. Use `--replace-existing` only during a controlled cutover if replacing those actions is intentional.

## Transition Import Commands

Preview a transition import without writing:

```bash
python scripts/front_transition_import.py --limit 10 --messages-limit 500 --json
```

Write a controlled batch:

```bash
python scripts/front_transition_import.py --limit 10 --messages-limit 500 --import-run-id front-transition-dryrun-01 --write --json
```

For larger batches, increase the limit only after the previous batch has been reviewed:

```bash
python scripts/front_transition_import.py --limit 200 --messages-limit 500 --allow-large --import-run-id front-transition-dryrun-01 --write --json
```

Preview deletion of one run:

```bash
python scripts/front_transition_purge.py --import-run-id front-transition-dryrun-01 --json
```

Purge one run:

```bash
python scripts/front_transition_purge.py --import-run-id front-transition-dryrun-01 --yes --json
```

The intended rehearsal is:

1. keep Twilio in `mock`;
2. import Front transition data with a dry-run `import_run_id`;
3. test review, reply, manual follow-up, inbound reopen, and closure;
4. purge the dry-run import;
5. freeze Front;
6. reimport with the final `import_run_id`;
7. only then switch Twilio routing.
