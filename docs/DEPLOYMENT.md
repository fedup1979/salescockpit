# Deployment Plan

## Objective

Publish Sales Cockpit quickly without touching Front.io, production Twilio, SchoolDrive writes, or Notion writes.

## Current DigitalOcean Status

Staging is deployed and reachable:

```text
http://139.59.158.77:8502
```

Server:

```text
salescockpit-prod-01
Ubuntu 24.04 LTS
Public IPv4: 139.59.158.77
```

Running services:

```text
sales-cockpit-ui@staging.service
sales-cockpit-api@staging.service
```

PROD and DEV are intentionally not started yet. The scaffold supports them, but staging should be validated first so that we do not expose multiple mock copies of the cockpit.

The first staging deployment was made from a local `git archive` because the GitHub repository is private and the droplet does not yet have a GitHub deploy key.

Current staging webhook for SchoolDrive:

```text
POST http://139.59.158.77:8602/webhooks/schooldrive/lead-or-presubscription
Authorization: Bearer <staging-token>
```

The staging API port `8602` is exposed for integration testing. Do not connect production over plain HTTP; production should use HTTPS before cutover.

The deployment target is one DigitalOcean droplet running three isolated environments:

| Environment | UI port | API port | Database |
|---|---:|---:|---|
| PROD | 8501 | 8601 | `/opt/sales-cockpit/prod/data/sales_cockpit.db` |
| STAGING | 8502 | 8602 | `/opt/sales-cockpit/staging/data/sales_cockpit.db` |
| DEV | 8503 | 8603 | `/opt/sales-cockpit/dev/data/sales_cockpit.db` |

The UI ports are the ones François requested. The API ports are separate because Twilio and future integrations need webhook endpoints that Streamlit cannot provide.

## GitHub

The GitHub repository exists:

```text
https://github.com/fedup1979/salescockpit
```

Local `main` tracks `origin/main`.

The droplet has a read-only deploy key and can pull from GitHub.

Historical note: the local GitHub CLI token could push to the repository, but could not create the repository because it lacked `createRepository`.

Two valid options:

1. Refresh the GitHub CLI token with repository scope, then create the repo from the CLI.
2. Create the private repo manually in GitHub, then add it as `origin` locally.

Repository:

```text
fedup1979/salescockpit
```

## DigitalOcean

Recommended MVP droplet:

- Ubuntu 24.04 LTS.
- Frankfurt or Amsterdam region.
- Basic shared CPU.
- 2 GB RAM preferred.
- SSH key access.

Initial firewall:

- `22` for SSH.
- `8501`, `8502`, `8503` for UI testing.
- `8602` for SchoolDrive staging webhook tests.

Keep `8601` and `8603` internal. The cleaner future setup is to put FastAPI behind a reverse proxy with HTTPS.

## Server Setup

On a fresh droplet, install Git first, then clone the repo into a temporary ops folder:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone git@github.com:fedup1979/salescockpit.git /tmp/sales-cockpit
cd /tmp/sales-cockpit
```

Then bootstrap the server and install the systemd units:

```bash
sudo bash deploy/scripts/bootstrap_ubuntu.sh
sudo bash deploy/scripts/install_systemd.sh
```

For each environment:

```bash
sudo -u salescockpit cp deploy/env/staging.env.example /opt/sales-cockpit/staging/.env
sudo -u salescockpit nano /opt/sales-cockpit/staging/.env
```

Then deploy:

```bash
sudo REPO_URL=git@github.com:fedup1979/salescockpit.git BRANCH=main bash deploy/scripts/deploy_env.sh staging
sudo systemctl enable --now sales-cockpit-ui@staging sales-cockpit-api@staging
```

Repeat for `prod` and `dev` when needed.

## Twilio Sandbox

Use sandbox first. Do not switch production WhatsApp traffic until the cockpit has passed scenario testing.

Minimum Twilio values needed in the target `.env`:

```text
SALES_COCKPIT_TWILIO_MODE=sandbox
SALES_COCKPIT_TWILIO_ACCOUNT_SID=
SALES_COCKPIT_TWILIO_AUTH_TOKEN=
SALES_COCKPIT_TWILIO_WHATSAPP_SENDER=
SALES_COCKPIT_TWILIO_MESSAGING_SERVICE_SID=
SALES_COCKPIT_TWILIO_VALIDATE_SIGNATURE=true
SALES_COCKPIT_TWILIO_WEBHOOK_URL=http://139.59.158.77:8602
SALES_COCKPIT_TWILIO_STATUS_CALLBACK_URL=http://139.59.158.77:8602/webhooks/twilio/whatsapp/status
```

Twilio sandbox webhooks currently available in FastAPI:

```text
POST /webhooks/twilio/whatsapp/inbound
POST /webhooks/twilio/whatsapp/status
```

The inbound endpoint accepts Twilio's real form payload and validates `X-Twilio-Signature`.
The legacy JSON mock payload remains available only for internal tests.

Full sandbox notes:

```text
docs/TWILIO_SANDBOX.md
```

## SchoolDrive And Notion

V1 needs read-only enrichment:

- Lead or presubscription created in SchoolDrive.
- Stable SchoolDrive ID.
- Prospect name, phone, email.
- Source type: `lead` or `presubscription`.
- Course category for leads.
- Course short name and start date for presubscriptions.
- Direct SchoolDrive URL for the prospect.

If the SchoolDrive MCP can expose these fields reliably, no extra SchoolDrive API is required for V1. If not, Tiago needs to provide either a read-only endpoint or a lead-created webhook payload with these fields.

Implemented SchoolDrive webhook:

```text
POST /webhooks/schooldrive/lead-or-presubscription
```

Rules implemented:

- Bearer auth via `SALES_COCKPIT_SCHOOLDRIVE_WEBHOOK_TOKEN`.
- Environment guard.
- Idempotency on `event_id`.
- Upsert on `data.schooldrive_id`.
- Ordering by `data.aggregated_updated_at`, then `occurred_at`, then `event_id`.
- Older snapshots are logged and ignored.
- Accepted snapshots replace the SchoolDrive WhatsApp autoresponder list.
- Sent autoresponders are shown in the conversation as SchoolDrive outbound messages.
- First Tanjona follow-up is scheduled at +72h after the latest sent autoresponder if no active action exists.
- `is_archived: true` resolves the conversation and closes open actions.

## Backup

SQLite backup scripts exist:

```text
deploy/scripts/backup_sqlite.sh
deploy/scripts/restore_sqlite.sh
```

Backups are stored outside the app folder:

```text
/opt/sales-cockpit/backups/<env>/
```

Before production cutover, test restore once and then add a daily cron. Full procedure:

```text
docs/BACKUP_RESTORE.md
```
