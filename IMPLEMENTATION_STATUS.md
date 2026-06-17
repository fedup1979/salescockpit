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
- Global `À faire` page with role and action-type filters.
- Formal business rules module in `sales_cockpit/business_rules.py`.
- Admin view for roles, qualifications, operating rules, follow-up sequences, lead types, and demo templates.
- Seeded Setter 2 user: `setter2@essr.ch`.
- Demo WhatsApp templates for initial offer, 72h/7d/30d follow-ups, setting, will-sign, course-date, and out-of-hours.
- Stop statuses `Non pertinent`, `Ne plus contacter`, and `A signé` complete open actions and resolve conversations.

## Next Checkpoints

1. Manual review of local mock UI by François, especially the `À faire` / next-action workflow.
2. Improve UX based on first review.
3. Create first Git commit after François approves the current checkpoint.
4. Add read-only connectors for SchoolDrive and Notion.
5. Add Twilio sandbox integration.
6. Prepare GitHub repo and DigitalOcean staging.
7. Define backup policy for SQLite and attachments.

## Integration Policy

- Twilio production is not touched until an explicit cutover plan exists.
- SchoolDrive is read-only in V1.
- Notion is read-only in V1.
- Front.io remains active until Sales Cockpit is tested and approved.
