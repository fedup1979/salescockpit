# Sales Cockpit

Internal ESSR sales cockpit for WhatsApp conversations, call tasks, lead qualification, template management, and future AI setter readiness.

The current build starts in mock mode. It does not touch Twilio, Front.io, SchoolDrive, or Notion production flows.

## Local Setup

```powershell
cd C:\Users\FD\Desktop\SalesCockpit
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\init_db.py
streamlit run sales_cockpit\ui\app.py
```

In another terminal, the API can be started with:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn sales_cockpit.api.main:app --reload --port 8000
```

## Initial Users

The seed password is controlled by `SALES_COCKPIT_SEED_PASSWORD`.

Default local password:

```text
ChangeMe!2026
```

Seeded accounts:

- laura.escariz@essr.ch, admin
- francois.dupuis@essr.ch, admin
- tiago.jacobs@gmail.com, admin
- service.etudiants@essr.ch, setter, Mihary
- yasmine@essr.ch, closer

## Current Scope

- Email and password login.
- SQLite WAL database.
- Mock leads, conversations, messages, templates, and tasks.
- WhatsApp 24-hour window enforcement.
- Operational conversation state: open / resolved.
- User actions to mark conversations resolved or reopen them.
- Free-form send blocked when the window is closed.
- Template send allowed only with approved templates.
- Template creation in local draft or approved mock status.
- Call task creation and completion.
- Lead qualification.
- Manual private WhatsApp notes.
- FastAPI endpoints for future webhooks.

## Safety

Do not put production secrets in Git. Use `.env` locally or DigitalOcean environment variables for staging.

## New Codex Sessions

Before continuing work, read:

- `AGENTS.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/NEXT_SESSION.md`
- `docs/BUILD_SPEC.md`
- `PRODUCT.md`
- `DESIGN.md`

These files are intended to make the project resumable without relying on chat history.
