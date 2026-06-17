# Sales Cockpit Agent Instructions

## Working Language

- Speak to François in French and use informal `tu`.
- Keep code identifiers, module names, API names, and technical docs in English.
- The Streamlit UI is for ESSR sales users, so visible UI labels should be in French.

## First Files to Read

At the start of any new Codex session in this repo, read these files before editing:

1. `README.md`
2. `IMPLEMENTATION_STATUS.md`
3. `docs/NEXT_SESSION.md`
4. `docs/BUILD_SPEC.md`
5. `PRODUCT.md`
6. `DESIGN.md`

The original longer PRD currently also exists at:

`C:\Users\FD\Desktop\MarketForge\marketforge-dev\docs\PRD_SALES_COCKPIT.md`

Do not assume that external path exists after GitHub/DigitalOcean migration. Keep this repo self-contained when adding important decisions.

## Product Boundaries

Sales Cockpit is a lightweight internal ESSR sales tool. It is not SchoolDrive and must not become a full CRM.

Core source-of-truth decisions:

- SchoolDrive is the source of truth for leads.
- Notion is read-only historical context.
- Twilio is the WhatsApp provider.
- Front.io remains untouched until an explicit migration/cutover plan exists.
- V1 is mock-first, then Twilio sandbox, then staging.

## Safety Rules

- Do not touch production Twilio, Front.io, SchoolDrive, or Notion flows without explicit approval.
- Do not commit secrets.
- Keep `.env`, database files, logs, and local storage out of Git.
- SchoolDrive and Notion are read-only in V1.
- WhatsApp Web scraping and unofficial WhatsApp integrations are out of scope.

## Tech Stack

- Python
- Streamlit UI
- FastAPI backend
- SQLite WAL
- pytest
- Mock Twilio first

## Current UX Model

There are two different concepts. Do not merge them:

- Conversation status: user-controlled operational state, `open` or `resolved`.
- WhatsApp window state: technical 24-hour API window, `open` or `closed`. This drives whether free-form messages are allowed.
- Next action: operational work item stored in the `tasks` table but displayed as `prochaine action` / `À faire`, not as an abstract task list.

Inbox tabs are work queues:

- `À traiter`: a setter/closer must act now.
- `À relancer`: a follow-up action is due now or overdue.
- `En attente`: no immediate action, usually a future follow-up.
- `Résolues`: conversation manually marked as resolved.

Operational rule:

- New inbound WhatsApp messages reopen the conversation and create/update a `reply` next action assigned to the setter.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- Resolving a conversation completes open actions for that lead.
- `Non pertinent` and `Ne plus contacter` are separate statuses. Both stop follow-ups; `Ne plus contacter` is a strict do-not-contact policy.
- Course-date reminders always win over lead-relative reminders. If both conflict, cancel the lead-relative reminder.
- Minimum delay between outbound WhatsApp follow-ups is 24h.
- Business rules are centralized in `sales_cockpit/business_rules.py` and displayed in Admin.

WhatsApp window is shown separately as a badge under the contact name:

- `Fenêtre ouverte`: free-form message allowed.
- `Fenêtre fermée`: approved template required.

If a new inbound WhatsApp message arrives on a resolved conversation, it should reopen automatically.

## UI Quality Rules

- Keep the UI dense, calm, and operational.
- Avoid landing-page patterns.
- Avoid decorative visuals.
- Do not use English labels in user-facing dropdowns unless there is no reasonable French equivalent.
- Keep error states explicit.
- Any disabled or blocked WhatsApp action must explain why.

## How to Work

- Prefer small, verifiable increments.
- Run tests after functional changes: `.\.venv\Scripts\python.exe -m pytest`
- Use Streamlit smoke tests when UI changes are significant.
- Keep `IMPLEMENTATION_STATUS.md` and `docs/NEXT_SESSION.md` updated after meaningful changes.
- Use `apply_patch` for edits.
