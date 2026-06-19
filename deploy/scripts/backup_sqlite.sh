#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-}"
if [[ "${ENV_NAME}" != "prod" && "${ENV_NAME}" != "staging" && "${ENV_NAME}" != "dev" ]]; then
  echo "Usage: $0 <prod|staging|dev>"
  exit 1
fi

BASE="/opt/sales-cockpit/${ENV_NAME}"
DB_PATH="${BASE}/data/sales_cockpit.db"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/sales-cockpit/backups/${ENV_NAME}}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
BACKUP_FILE="${BACKUP_ROOT}/sales_cockpit_${ENV_NAME}_${TIMESTAMP}.db"
GZ_FILE="${BACKUP_FILE}.gz"

if [[ ! -f "${DB_PATH}" ]]; then
  echo "Database not found: ${DB_PATH}"
  exit 1
fi

mkdir -p "${BACKUP_ROOT}"

sqlite3 "${DB_PATH}" ".backup '${BACKUP_FILE}'"
sqlite3 "${BACKUP_FILE}" "PRAGMA quick_check;" | grep -qx "ok"
gzip -n "${BACKUP_FILE}"
sha256sum "${GZ_FILE}" > "${GZ_FILE}.sha256"

ln -sfn "$(basename "${GZ_FILE}")" "${BACKUP_ROOT}/latest.db.gz"
ln -sfn "$(basename "${GZ_FILE}.sha256")" "${BACKUP_ROOT}/latest.db.gz.sha256"

find "${BACKUP_ROOT}" -type f -name "sales_cockpit_${ENV_NAME}_*.db.gz" -mtime "+${RETENTION_DAYS}" -delete
find "${BACKUP_ROOT}" -type f -name "sales_cockpit_${ENV_NAME}_*.db.gz.sha256" -mtime "+${RETENTION_DAYS}" -delete

chown -R salescockpit:salescockpit "${BACKUP_ROOT}" 2>/dev/null || true

echo "backup_created=${GZ_FILE}"
