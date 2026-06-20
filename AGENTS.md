# Sales Cockpit Agent Instructions

## Working Language

- Speak to François in French and use informal `tu`.
- Keep code identifiers, module names, API names, and technical docs in English.
- The Streamlit UI is for ESSR sales users, so visible UI labels should be in French.

## First Files to Read

At the start of any new Codex session in this repo, read these files before editing:

1. `README.md`
2. `IMPLEMENTATION_STATUS.md`
3. `docs/CURRENT_STATE.md`
4. `docs/NEXT_SESSION.md`
5. `docs/BUILD_SPEC.md`
6. `docs/ACTION_WORKFLOW.md`
7. `docs/BUSINESS_LOGIC.md`
8. `docs/GAP_ANALYSIS.md`
9. `docs/TECHNICAL_DEBT.md`
10. `PRODUCT.md`
11. `DESIGN.md`

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

There are four different concepts. Do not merge them:

- Main navigation order starts with `Tâches`, then `Inbox`, then `Modèles`, then `Admin`.
- Conversation status: user-controlled operational state, internally `open` or `resolved`, shown to users as `Active` / `Terminée`.
- WhatsApp window state: technical 24-hour API window, `open` or `closed`. This drives whether free-form messages are allowed.
- Next action: operational work item stored in the `tasks` table but displayed as `prochaine action` / `Tâches`, not as an abstract task list.
- Action is the central operational unit of the system. A conversation with `open` status must have one main non-terminal action, except when an urgent inbound `reply` temporarily interrupts an already planned call.
- `Parcours`: commercial state (`leads.sales_stage`). It is shown read-only and derived from workflow outcomes. Do not expose normal manual forcing to sales users.
- `Flux`: business follow-up scenario (`sequences`, `sequence_steps`, `sequence_template_mappings`). It generates future actions and is configured in `Pilotage`. In user-facing docs/UI, prefer `Flux` or `Scénario de suivi`, not `Séquence`, except for technical internals.
- The source of truth for action types, statuses, support actions, proofs, outcomes, triggers, workflow transitions, flux, and template requests is `docs/BUSINESS_LOGIC.md`, `docs/ACTION_WORKFLOW.md`, and structured constants in `sales_cockpit/business_rules.py`.
- `Tâches` is the default work page. It uses a split screen: assigned actions/persons on the left, selected prospect detail on the right.
- `Tâches` defaults to the connected user's own queue. The user can switch to another person's queue or `Tous`; that choice must persist when navigating away and back during the same session.

Inbox tabs are work queues:

- `À traiter`: someone must act now, including reply, call, contact review, blocked template work, or due follow-up.
- `En suspens`: the next action is planned later.
- `Terminées`: conversation internally marked as resolved.
- `Toutes`: all items in the current view.

`follow_up` is an action type, shown as `Envoyer relance`, not a separate top-level Inbox queue.

Visible queue and conversation controls:

- Left split-screen cards use `Voir`, not `Ouvrir`.
- Conversation-state buttons use `Clore la conversation` and `Réactiver`.
- The `Prochaine action` summary card shows only action type, due date/time, and the responsible-person badge.

Operational rule:

- New inbound WhatsApp messages reopen the conversation and create/update a `reply` next action assigned to the setter.
- If an inbound message arrives while a `setting_call` or `closing_call` is already planned, keep the planned call visible and active. The inbound creates an urgent `reply` interruption, but it must not cancel the planned call unless the user explicitly reschedules or replaces it.
- If a `reply` interruption is answered without fixing a new appointment, close the `reply` action and keep the existing planned call as the next action. Do not create a Tanjona follow-up in parallel.
- If the latest message is inbound and unanswered, the prospect is waiting. Show a visible but restrained hot signal in Inbox and `Tâches`, and sort that item above ordinary calls or follow-ups.
- `Tâches` and Inbox auto-refresh every 10 seconds while visible, so Twilio webhook updates should appear without manual navigation.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- Resolving a conversation completes open actions for that lead.
- `Non pertinent` and `Ne plus contacter` are separate concepts. `Non pertinent` is a commercial qualification. `Ne plus contacter` is `contact_status = do_not_contact`.
- If a `do_not_contact` prospect writes inbound, do not ignore it and do not create automatic follow-ups. Create a `contact_review` action for Setter 1.
- Resolving a conversation requires a controlled reason. Some reasons require a note.
- Reopening a resolved conversation requires creating the next action immediately.
- Missing WhatsApp templates are tracked as `template_requests` linked to the blocked follow-up action.
- In the main Actions tab, `reply` and `follow_up` are not closed by a generic completion button. The normal proof is the outbound WhatsApp message sent from the Conversation composer.
- The Conversation composer captures the business outcome for `reply` at send time and creates the next action from that outcome.
- Planned call actions are future actions to document the call result. When the due time arrives, they appear in `Tâches`; the user completes them in Actions with result plus mandatory note.
- Planned calls must also be visible in the conversation detail so the setter/closer can see and modify them when a prospect writes before the appointment.
- Manual WhatsApp completion belongs only in `Actions avancées`.
- Course-date reminders always win over lead-relative reminders. If both conflict, cancel the lead-relative reminder. Do not interrupt or replace a planned `setting_call` or `closing_call`.
- Minimum delay between outbound WhatsApp follow-ups is 24h.
- Business rules are centralized in `sales_cockpit/business_rules.py` and displayed in Admin.
- Main action types for V1 are `reply`, `follow_up`, `setting_call`, and `closing_call`. Qualification, manual notes, and template creation are support actions/proofs unless they block the main flow.
- Keep the UI simple: no visible `Température` field. Display `sales_stage` as `Parcours`.
- Private notes are always included in the future learning base; do not show an inclusion checkbox.
- In the global `Tâches` view, filter responsibility by individual people, not only by role.
- The mock seed must keep at least one open task per active user so each responsible-person queue can be visually checked.
- The mock seed includes at least one inbound unanswered example to verify the hot waiting-reply state.
- Use SchoolDrive terms for lead source type: `lead` and `presubscription`. Show them in French as `Lead` and `Préinscription`.
- In inbox cards, show the SD course category short title for `lead`, and the SD course short name for `presubscription`.

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
