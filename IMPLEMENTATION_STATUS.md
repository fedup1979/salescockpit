# Sales Cockpit Implementation Status

## Current Status

V1 local mock build is runnable.

## Completed

- Product context.
- Design context.
- Project-level `AGENTS.md` for future Codex sessions.
- Self-contained build spec in `docs/BUILD_SPEC.md`.
- Handoff notes in `docs/NEXT_SESSION.md`.
- Local project structure.
- PRD reference exists in `C:\Users\FD\Desktop\MarketForge\marketforge-dev\docs\PRD_SALES_COCKPIT.md`.
- SQLite WAL persistence.
- Streamlit internal cockpit UI.
- FastAPI webhook-ready backend.
- Initial seeded users.
- Mock leads, conversations, messages, templates, and tasks.
- WhatsApp 24-hour window rule enforcement.
- Streamlit smoke test for login and inbox.
- French display labels for dropdowns.
- Operational conversation status separate from WhatsApp window state.
- Mark conversation resolved / reopen conversation.
- Inbound messages reopen resolved conversations.
- Inbox work queues: `À traiter`, `À relancer`, `En attente`, `Résolues`.
- Next-action model on top of the existing `tasks` table.
- Inbound WhatsApp messages create/update a setter `reply` action.
- Follow-up scheduling and setter-to-closer handoff from the conversation detail.
- Global `Tâches` page with responsible-person and action filters.
- Formal business rules module in `sales_cockpit/business_rules.py`.
- Admin view for roles, qualifications, operating rules, follow-up sequences, lead types, and demo templates.
- Seeded Setter 2 user: `setter2@essr.ch`.
- Demo WhatsApp templates for initial offer, 72h/7d/30d follow-ups, setting, will-sign, course-date, and out-of-hours.
- Stop statuses `Non pertinent`, `Ne plus contacter`, and `A signé` complete open actions and resolve conversations.
- UI simplification: `Température` hidden, `sales_stage` displayed as `Parcours`, private notes always included for future learning.
- Global `Tâches` filters responsibility by individual people, defaults to the connected user's own queue, and persists a manual responsible-person choice during navigation.
- SchoolDrive lead source types use `lead` and `presubscription`; inbox cards display `Lead` / `Préinscription` and use course category vs course short name accordingly.
- Experimental UX pass: `Tâches` is first in navigation and uses a split-screen action/person list with the selected prospect detail on the right.
- Mock seed ensures at least one open task for each active user for visual queue checks.
- Inbound unanswered prospects are highlighted with a restrained hot signal and sorted above ordinary due actions.
- `Tâches` and Inbox auto-refresh every 10 seconds while visible.
- Action workflow decisions documented in `docs/ACTION_WORKFLOW.md`: action as operational unit, main vs support actions, statuses, proofs, outcomes, triggers, and transition table.

## Next Checkpoints

1. Manual review of local mock UI by François, especially the `Tâches` / next-action workflow.
2. Implement the validated action workflow model from `docs/ACTION_WORKFLOW.md`.
3. Improve UX based on first review.
4. Create first Git commit after François approves the current checkpoint.
5. Add read-only connectors for SchoolDrive and Notion.
6. Add Twilio sandbox integration.
7. Prepare GitHub repo and DigitalOcean staging.
8. Define backup policy for SQLite and attachments.

## Integration Policy

- Twilio production is not touched until an explicit cutover plan exists.
- SchoolDrive is read-only in V1.
- Notion is read-only in V1.
- Front.io remains active until Sales Cockpit is tested and approved.
