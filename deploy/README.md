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

## Current Access Status

- GitHub CLI is installed and authenticated locally, but the current token cannot create a repository.
- DigitalOcean CLI is not installed locally.
- Twilio CLI is not installed locally.

## Recommended Immediate Path

1. Create a private GitHub repository named `sales-cockpit`.
2. Add it as the local `origin` remote.
3. Push the current local repository.
4. Create one Ubuntu 24.04 LTS DigitalOcean droplet.
5. Clone the repository on the droplet into a temporary ops folder.
6. Run `deploy/scripts/bootstrap_ubuntu.sh` on the droplet.
7. Run `deploy/scripts/install_systemd.sh` on the droplet.
8. Deploy each environment with `deploy/scripts/deploy_env.sh`.
9. Use Twilio Sandbox only after the API webhook URL is reachable.

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
