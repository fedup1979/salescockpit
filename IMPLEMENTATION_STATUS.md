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
- Inbox work queues: `À faire`, `À venir`, `Résolues`; follow-ups due now are included in `À faire`.
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
- Action workflow decisions documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`: action as operational unit, main vs support actions, statuses, proofs, outcomes, triggers, and transition table.
- Admin `Workflow` tab displays main action types, support actions, action statuses, and the transition table.
- Exhaustive business logic documented in `docs/BUSINESS_LOGIC.md`.
- Gap analysis documented in `docs/GAP_ANALYSIS.md`.
- Commercial qualification and contact status are separated in the data model.
- Manual resolution now requires a controlled reason, with note required for sensitive reasons.
- Manual reopening now requires creating the next action.
- Inbound message from a `Ne plus contacter` prospect creates a `contact_review` action for Setter 1.
- Follow-up sequences and sequence steps are stored structurally in SQLite and visible in Admin.
- Missing templates create `template_requests` linked to the blocked action.
- Outbound WhatsApp messages close the active `reply` or `follow_up` action and create the next follow-up when applicable.
- WhatsApp `reply` actions can now choose the business outcome at send time, so the sent message is the proof and the selected outcome creates the next action.
- The Actions tab is contextual by action type: WhatsApp actions guide users to the Conversation composer, calls use result + mandatory note, contact reviews show explicit do-not-contact decisions, and exceptions live in Actions avancées.
- Setting/closing calls can be completed with business outcomes that create the next action.
- Added tests for resolution/reopen guards, do-not-contact inbound review, template requests, reply-to-follow-up chaining, send-time reply outcomes, call retry chaining, and Streamlit action guidance.

## Next Checkpoints

1. Manual review of local mock UI by François, especially action outcomes, resolution/reopen popovers, template requests, and Admin rules.
2. Improve UX based on review.
3. Add read-only connectors for SchoolDrive and Notion.
4. Add Twilio sandbox integration.
5. Prepare GitHub repo and DigitalOcean staging.
6. Define backup policy for SQLite and attachments.

## Integration Policy

- Twilio production is not touched until an explicit cutover plan exists.
- SchoolDrive is read-only in V1.
- Notion is read-only in V1.
- Front.io remains active until Sales Cockpit is tested and approved.
