# Next Session Handoff

## Current State

Sales Cockpit is a runnable local mock MVP.

Local URLs:

- Streamlit UI: `http://localhost:8501`
- FastAPI health: `http://127.0.0.1:8000/health`

The app has been iteratively reviewed by François and is currently in a good mock-prototype state.

## Important Recent Decisions

- Inbox tabs are not WhatsApp API window tabs.
- Inbox tabs are user-controlled operational states:
  - `Ouvertes`
  - `Résolues`
- WhatsApp API window state remains a separate badge:
  - `Fenêtre ouverte`
  - `Fenêtre fermée`
- Users can mark a conversation as resolved and reopen it.
- New inbound messages reopen resolved conversations automatically.
- Dropdown labels should be displayed in French while internal values remain English.
- Private notes remain yellow and align right like team messages.
- Reply tools live below the conversation thread.
- SchoolDrive link appears next to the prospect name, opening in a new tab.

## Current Validation

Latest known validation:

- `pytest`: 6 tests passing.
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

1. Let François continue UX review on the mock UI.
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

