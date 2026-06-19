#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-}"
if [[ "${ENV_NAME}" != "prod" && "${ENV_NAME}" != "staging" && "${ENV_NAME}" != "dev" ]]; then
  echo "Usage: REPO_URL=<git-url> [BRANCH=main] $0 prod|staging|dev"
  exit 1
fi

REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-salescockpit}"
if [[ -z "${REPO_URL}" ]]; then
  echo "REPO_URL is required."
  exit 1
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this script as root so it can restart systemd services."
  exit 1
fi
if ! id "${APP_USER}" >/dev/null 2>&1; then
  echo "Application user '${APP_USER}' does not exist."
  exit 1
fi

BASE="/opt/sales-cockpit/${ENV_NAME}"
APP="${BASE}/app"
ENV_FILE="${BASE}/.env"

mkdir -p "${BASE}/data" "${BASE}/storage"
chown -R "${APP_USER}:${APP_USER}" "${BASE}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  echo "Create it from deploy/env/${ENV_NAME}.env.example before deploying."
  exit 1
fi

if [[ ! -d "${APP}/.git" ]]; then
  sudo -H -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP}"
else
  sudo -H -u "${APP_USER}" git -C "${APP}" fetch --all --prune
  sudo -H -u "${APP_USER}" git -C "${APP}" checkout "${BRANCH}"
  sudo -H -u "${APP_USER}" git -C "${APP}" pull --ff-only
fi

sudo -H -u "${APP_USER}" python3 -m venv "${APP}/.venv"
sudo -H -u "${APP_USER}" "${APP}/.venv/bin/python" -m pip install --upgrade pip
sudo -H -u "${APP_USER}" "${APP}/.venv/bin/pip" install -r "${APP}/requirements.txt"

sudo -H -u "${APP_USER}" bash -c "
  cd "${APP}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  "${APP}/.venv/bin/python" scripts/init_db.py
"

chown -R "${APP_USER}:${APP_USER}" "${BASE}/data" "${BASE}/storage"

systemctl restart "sales-cockpit-ui@${ENV_NAME}.service"
systemctl restart "sales-cockpit-api@${ENV_NAME}.service"

echo "Deployment complete for ${ENV_NAME}."
