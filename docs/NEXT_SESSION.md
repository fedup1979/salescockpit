# Next Session Handoff

## Current State

Sales Cockpit is a runnable local mock MVP.

Local URLs:

- Streamlit UI: `http://localhost:8501`
- FastAPI health: `http://127.0.0.1:8000/health`

The app has been iteratively reviewed by François and is currently in a good mock-prototype state.

## Important Recent Decisions

- Inbox tabs are not WhatsApp API window tabs.
- Inbox tabs are operational work queues:
  - `À traiter`
  - `À relancer`
  - `En attente`
  - `Résolues`
- WhatsApp API window state remains a separate badge:
  - `Fenêtre ouverte`
  - `Fenêtre fermée`
- Users can mark a conversation as resolved and reopen it.
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
- `Non pertinent` and `Ne plus contacter` are separate. Both stop follow-ups, but `Ne plus contacter` means strict do-not-contact.
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
- The detail tabs are now `Conversation`, `Qualification`, `Actions`, `Notes privées`; on `Tâches`, `Actions` is shown first.
- Inbox has a `Tous` tab before the operational queue tabs.

## Current Validation

Latest known validation:

- `pytest`: 11 tests passing.
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
