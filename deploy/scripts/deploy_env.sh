#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-}"
if [[ "${ENV_NAME}" != "prod" && "${ENV_NAME}" != "staging" && "${ENV_NAME}" != "dev" ]]; then
  echo "Usage: REPO_URL=<git-url> [BRANCH=main] $0 prod|staging|dev"
  exit 1
fi

REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-main}"
if [[ -z "${REPO_URL}" ]]; then
  echo "REPO_URL is required."
  exit 1
fi

BASE="/opt/sales-cockpit/${ENV_NAME}"
APP="${BASE}/app"
ENV_FILE="${BASE}/.env"

mkdir -p "${BASE}/data" "${BASE}/storage"

if [[ ! -d "${APP}/.git" ]]; then
  git clone --branch "${BRANCH}" "${REPO_URL}" "${APP}"
else
  git -C "${APP}" fetch --all --prune
  git -C "${APP}" checkout "${BRANCH}"
  git -C "${APP}" pull --ff-only
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}."
  echo "Create it from deploy/env/${ENV_NAME}.env.example before deploying."
  exit 1
fi

python3 -m venv "${APP}/.venv"
"${APP}/.venv/bin/python" -m pip install --upgrade pip
"${APP}/.venv/bin/pip" install -r "${APP}/requirements.txt"

(
  cd "${APP}"
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
  "${APP}/.venv/bin/python" scripts/init_db.py
)

chown -R salescockpit:salescockpit "${BASE}/data" "${BASE}/storage"

systemctl restart "sales-cockpit-ui@${ENV_NAME}.service"
systemctl restart "sales-cockpit-api@${ENV_NAME}.service"

echo "Deployment complete for ${ENV_NAME}."
