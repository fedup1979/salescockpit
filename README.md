# Sales Cockpit

Internal ESSR sales cockpit for WhatsApp conversations, next actions, lead qualification, template management, and future AI setter readiness.

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

To reset the local demo scenarios before a manual validation session:

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
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
- setter2@essr.ch, setter, Tanjona
- yasmine@essr.ch, closer

## Current Scope

- Email and password login.
- SQLite WAL database.
- Mock leads, conversations, messages, templates, and tasks.
- WhatsApp 24-hour window enforcement.
- Operational conversation state: internal open / resolved, shown as active / terminée in the UI.
- User actions to close or reactivate conversations.
- Resolution with mandatory reason.
- Reopening with mandatory next action.
- Separate commercial qualification and contact status.
- Do-not-contact inbound review assigned to Setter 1.
- Free-form send blocked when the window is closed.
- Template send allowed only with approved templates.
- Template requests linked to blocked follow-up actions.
- Structured follow-up sequences and sequence steps.
- Admin-only Twilio template synchronization, creation, and WhatsApp approval submission for text templates.
- Work queues: `À traiter`, `En suspens`, `Terminées`, `Toutes`. `Envoyer relance` is an action type, not a separate main queue.
- Next-action creation, scheduling, completion, and setter-to-closer handoff.
- Contextual Actions tab where WhatsApp actions are normally completed by sent-message proof, while calls require result and note.
- Lead qualification.
- Formal business rules visible in Admin.
- Manual private WhatsApp notes.
- Bug reporting with activity logs.
- Scenario reset script for clean local validation.
- FastAPI endpoints for future webhooks.
- Twilio sandbox inbound webhook, outbound send, status callback, signature validation, SDK client, and delivery checks while keeping mock mode as the local default.
- SchoolDrive snapshot webhook for lead and presubscription upserts.
- Read-only Front API client foundation for future historical imports.

## Safety

Do not put production secrets in Git. Use `.env` locally or DigitalOcean environment variables for staging.

## Deployment

Deployment preparation is documented in:

- `docs/DEPLOYMENT.md`
- `docs/TWILIO_SANDBOX.md`
- `docs/TWILIO_SENDER_MIGRATION.md`
- `docs/FRONT_IMPORT.md`
- `docs/BACKUP_RESTORE.md`
- `deploy/README.md`

Planned UI ports:

- PROD: `8501`
- STAGING: `8502`
- DEV: `8503`

## New Codex Sessions

Start with `docs/CURRENT_STATE.md` for the latest operational truth, then read the supporting docs below.

Before continuing work, read:

- `AGENTS.md`
- `IMPLEMENTATION_STATUS.md`
- `docs/CURRENT_STATE.md`
- `docs/NEXT_SESSION.md`
- `docs/BUILD_SPEC.md`
- `docs/ACTION_WORKFLOW.md`
- `docs/BUSINESS_LOGIC.md`
- `docs/GAP_ANALYSIS.md`
- `docs/TEST_PLAN.md`
- `docs/USER_GUIDE.md`
- `docs/DEPLOYMENT.md`
- `docs/SCHOOLDRIVE_WEBHOOK.md`
- `docs/TWILIO_SANDBOX.md`
- `docs/TWILIO_SENDER_MIGRATION.md`
- `docs/FRONT_IMPORT.md`
- `docs/TECHNICAL_DEBT.md`
- `docs/BACKUP_RESTORE.md`
- `PRODUCT.md`
- `DESIGN.md`

These files are intended to make the project resumable without relying on chat history.
