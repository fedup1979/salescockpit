# Deployment Plan

## Objective

Publish Sales Cockpit quickly without touching Front.io, production Twilio, SchoolDrive writes, or Notion writes.

The deployment target is one DigitalOcean droplet running three isolated environments:

| Environment | UI port | API port | Database |
|---|---:|---:|---|
| PROD | 8501 | 8601 | `/opt/sales-cockpit/prod/data/sales_cockpit.db` |
| STAGING | 8502 | 8602 | `/opt/sales-cockpit/staging/data/sales_cockpit.db` |
| DEV | 8503 | 8603 | `/opt/sales-cockpit/dev/data/sales_cockpit.db` |

The UI ports are the ones François requested. The API ports are separate because Twilio and future integrations need webhook endpoints that Streamlit cannot provide.

## GitHub

The local machine already has GitHub CLI installed and authenticated, but the current token cannot create repositories.

Two valid options:

1. Refresh the GitHub CLI token with repository scope, then create the repo from the CLI.
2. Create the private repo manually in GitHub, then add it as `origin` locally.

Recommended repository:

```text
fedup1979/sales-cockpit
```

After the repo exists:

```powershell
git remote add origin https://github.com/fedup1979/sales-cockpit.git
git push -u origin main
```

If the local branch is still `master`, either push `master` first or rename it before pushing:

```powershell
git branch -M main
git push -u origin main
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

Keep `8601`, `8602`, `8603` internal unless a Twilio sandbox test explicitly needs direct access. The cleaner future setup is to put FastAPI behind a reverse proxy with HTTPS.

## Server Setup

On a fresh droplet, install Git first, then clone the repo into a temporary ops folder:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/fedup1979/sales-cockpit.git /tmp/sales-cockpit
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
sudo REPO_URL=https://github.com/fedup1979/sales-cockpit.git BRANCH=main bash deploy/scripts/deploy_env.sh staging
sudo systemctl enable --now sales-cockpit-ui@staging sales-cockpit-api@staging
```

Repeat for `prod` and `dev` when needed.

## Twilio Sandbox

Use sandbox first. Do not switch production WhatsApp traffic until the cockpit has passed scenario testing.

Minimum Twilio values needed in the target `.env`:

```text
SALES_COCKPIT_TWILIO_ACCOUNT_SID=
SALES_COCKPIT_TWILIO_AUTH_TOKEN=
SALES_COCKPIT_TWILIO_WHATSAPP_SENDER=
SALES_COCKPIT_TWILIO_MESSAGING_SERVICE_SID=
```

Webhook currently available in the FastAPI mock:

```text
POST /webhooks/twilio/whatsapp/inbound
```

Before connecting real Twilio, the webhook must be adapted to Twilio's real inbound form payload and signature validation. The current endpoint is intentionally mock-shaped.

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

## Backup

SQLite backup is not yet automated.

Minimum before PROD:

- Daily copy of each `sales_cockpit.db`.
- Keep at least 7 daily backups.
- Store backups outside the app folder.
- Test restore once before live cutover.
