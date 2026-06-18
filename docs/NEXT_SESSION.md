# Next Session Handoff

## Current State

Sales Cockpit is a runnable local mock MVP.

Local URLs:

- Streamlit UI: `http://localhost:8501`
- FastAPI health: `http://127.0.0.1:8000/health`

The app has been iteratively reviewed by François and is currently in a good mock-prototype state.

## Important Recent Decisions

- The action is now explicitly validated as the central operational unit of the system.
- A conversation with `open` status must always have one open next action.
- The exhaustive validated business logic is now in `docs/BUSINESS_LOGIC.md`.
- The implementation gap analysis is now in `docs/GAP_ANALYSIS.md`.
- The validated workflow model is documented in `docs/ACTION_WORKFLOW.md` and structured in `sales_cockpit/business_rules.py`; read it before changing `Tâches`, actions, follow-ups, calls, templates, qualification, or automation.
- Admin now includes a `Workflow` tab showing main action types, support actions, action statuses, and the transition table.
- The main V1 action chain is `reply`, `follow_up`, `setting_call`, `closing_call`.
- Qualification, manual notes, and template creation are support actions/proofs by default, not main workflow actions.
- `setting_call` is the preferred internal term over generic `call`; UI may still show `Appel` or `Appel de setting`.
- Persisted action statuses should be `planned`, `open`, `in_progress`, `done`, `cancelled`, `blocked`; `due` should be calculated from `due_at`, not stored as a status.
- The transition table is partially implemented in the local mock system: resolution/reopen guards, contact review, template requests, outbound message chaining, and call outcome chaining are now active.
- Inbox tabs are not WhatsApp API window tabs.
- Inbox tabs are operational work queues:
  - `À faire`
  - `À venir`
  - `Résolues`
- `Relancer` is an action type, not a separate top-level Inbox queue.
- WhatsApp API window state remains a separate badge:
  - `Fenêtre ouverte`
  - `Fenêtre fermée`
- Users can mark a conversation as resolved only with a controlled reason.
- Users can reopen a conversation only by creating the next action.
- New inbound messages reopen resolved conversations automatically.
- New inbound messages create or update a setter `reply` next action.
- Passing to closer completes current open actions, moves the lead to `closing`, and creates a `closing_call` action for the closer.
- Resolving a conversation completes open actions for that lead.
- The old technical `tasks` table remains, but the UI should call these `actions` or `prochaines actions`.
- Business rules are centralized in `sales_cockpit/business_rules.py` and shown in Admin.
- `Température` is no longer shown in the UI. Keep the DB field for compatibility, but do not reintroduce it as a visible qualification field unless François explicitly asks.
- `sales_stage` is displayed as `Parcours`.
- Private notes are always included in the future learning base; there is no checkbox in the UI.
- The global `Tâches` view filters by individual responsible people, not only by role.
- `Non pertinent` and `Ne plus contacter` are separate. `Non pertinent` is commercial qualification. `Ne plus contacter` is a separate contact status.
- If a `Ne plus contacter` prospect writes again, create a `contact_review` action for Setter 1. Do not create automatic follow-ups.
- Missing templates create `template_requests` linked to the blocked follow-up action.
- Follow-up sequences and sequence steps are stored structurally in SQLite and displayed in Admin.
- Outbound WhatsApp messages close the active `reply` or `follow_up` action and create the next follow-up when applicable.
- `reply` and `follow_up` should not be manually marked as sent in the main Actions flow. The normal proof is the outbound WhatsApp message from the Conversation composer.
- The Conversation composer can capture the send-time outcome for a `reply`: no appointment, setting appointment booked, non pertinent, or ne plus contacter.
- The Actions tab is contextual: WhatsApp actions explain where to send, call actions collect result + mandatory note, blocked relances show template-request state, and manual overrides are inside `Actions avancées`.
- Setting and closing calls can be completed with business outcomes that create the next action.
- Lead-relative reminders follow `+72h, +72h, +72h, +7j, +7j, +30j, stop`.
- Course-date reminders win over lead-relative reminders. The losing lead-relative reminder is cancelled.
- Minimum outbound WhatsApp follow-up delay is 24h.
- Setter 2 is currently seeded as `setter2@essr.ch`.
- Dropdown labels should be displayed in French while internal values remain English.
- Private notes remain yellow and align right like team messages.
- Reply tools live below the conversation thread.
- SchoolDrive link appears next to the prospect name, opening in a new tab.
- SchoolDrive lead types use SD terms internally: `lead` and `presubscription`.
- Inbox conversation cards show `Lead` or `Préinscription` above the prospect name.
- For `lead`, the course line shows the SD course category short title, e.g. `APP`; for `presubscription`, it shows the SD course short name, e.g. `APP GE P26`.
- Checkpoint tag before the `Tâches` layout experiment: `checkpoint-before-a-faire-layout-2026-06-18-0829`.
- Navigation now opens on `Tâches`, then `Inbox`, `Modèles`, `Admin`.
- `Tâches` is being tested with the same split-screen pattern as Inbox: action/person list on the left, selected prospect detail on the right.
- In `Tâches`, every user defaults to their own assigned actions, including admins. They can still switch to another user or `Tous`, and that choice persists while navigating between pages.
- Mock seed creates at least one open task per active user so every responsible-person queue can be inspected.
- Inbound unanswered prospects show a restrained hot signal in Inbox and `Tâches`, sort above ordinary due actions, and the mock seed includes `Léa Martin` as a waiting-reply example.
- Inbox and `Tâches` auto-refresh every 10 seconds while visible.
- The right-side detail tabs use the same order in `Tâches` and Inbox: `Conversation`, `Actions`, `Qualification`, `Notes privées`.
- Inbox has a `Tous` tab before the operational queue tabs.

## Current Validation

Latest known validation:

- `pytest`: 25 tests passing.
- Streamlit AppTest smoke covers reply-action guidance and absence of the generic `Terminer l'action` button in the main Actions flow.
- Streamlit smoke tests passed during the session.
- Streamlit and FastAPI were restarted after a stale import issue.

If a future session sees an import error for a recently added function, restart Streamlit. Streamlit can keep old modules in memory.

## Stale Process Note

During development, a stale Streamlit process caused:

`ImportError: cannot import name 'set_conversation_status' from 'sales_cockpit.store'`

The function existed in the file and imported correctly in a fresh Python process. Restarting Streamlit fixed it.

Useful commands:

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(8000,8501) }
```

Stop a process:

```powershell
Stop-Process -Id <PID> -Force
```

## Known Gaps

- SchoolDrive connector is placeholder only.
- SchoolDrive URL format is mock and must be confirmed by Tiago.
- Notion connector is placeholder only.
- Twilio is mock only.
- Attachments UI exists but persistence/send is not implemented.
- Auth is local password-based only.
- No GitHub remote yet.
- No DigitalOcean staging yet.
- No backup strategy implemented yet.

## Recommended Next Work

1. Let François continue UX review on the mock UI, especially the `Tâches` workflow.
2. After the UI shape stabilizes, create first Git commit.
3. Add GitHub remote.
4. Implement SchoolDrive read-only lead lookup.
5. Implement Notion historical enrichment.
6. Implement Twilio sandbox mode.
7. Prepare staging deployment.

## Files Most Likely to Change Next

- `sales_cockpit/ui/app.py`
- `sales_cockpit/ui/styles.py`
- `sales_cockpit/store.py`
- `sales_cockpit/db.py`
- `sales_cockpit/services/schooldrive.py`
- `sales_cockpit/services/notion.py`
- `sales_cockpit/services/mock_twilio.py`
- `tests/test_store.py`
