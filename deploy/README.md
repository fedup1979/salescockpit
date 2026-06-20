# Sales Cockpit Deployment

This folder contains the lightweight deployment scaffold for GitHub + DigitalOcean.

Target runtime layout on the droplet:

```text
/opt/sales-cockpit/
  prod/
    app/
    data/
    storage/
  staging/
    app/
    data/
    storage/
  dev/
    app/
    data/
    storage/
```

Public Streamlit UI ports:

- PROD: `8501`
- STAGING: `8502`
- DEV: `8503`

Internal FastAPI ports:

- PROD API: `8601`
- STAGING API: `8602`
- DEV API: `8603`

The API ports are reserved for Twilio and future integrations. They should normally sit behind a reverse proxy or be exposed only when explicitly needed for sandbox testing.
When API ports are exposed outside localhost, configure `SALES_COCKPIT_API_TOKEN`; configure `SALES_COCKPIT_MOCK_WEBHOOK_TOKEN` as well if JSON mock webhooks are enabled outside local tests.

## Current Access Status

The GitHub repository and DigitalOcean droplet now exist. Treat this file as a deployment layout reference. For the current operational deployment procedure, read `docs/DEPLOYMENT.md`, `docs/CUTOVER_RUNBOOK.md`, and `docs/BACKUP_RESTORE.md`.

## Recommended Immediate Path

1. Pull the GitHub repository on the droplet through `deploy/scripts/deploy_env.sh`.
2. Keep prod, staging, and dev databases isolated.
3. Create a SQLite backup before every staging/prod data operation.
4. Run production with `SALES_COCKPIT_SEED_DEMO_DATA=false`.
5. Use Twilio Sandbox or live senders only after the relevant API webhook URL is reachable and the explicit safety posture is confirmed.

## Droplet Recommendation

For the MVP, one droplet is enough:

- Ubuntu 24.04 LTS.
- Region close to Switzerland, for example Frankfurt or Amsterdam.
- Basic shared CPU.
- Prefer 2 GB RAM because three Streamlit processes plus API workers are planned.
- SSH key access only.

Open firewall ports for the first test:

- `22` SSH.
- `8501` PROD UI.
- `8502` STAGING UI.
- `8503` DEV UI.

API ports `8601` / `8602` / `8603` should stay internal unless a temporary Twilio sandbox test requires direct access.
