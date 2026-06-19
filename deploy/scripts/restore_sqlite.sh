#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-}"
BACKUP_PATH="${2:-}"
if [[ "${ENV_NAME}" != "prod" && "${ENV_NAME}" != "staging" && "${ENV_NAME}" != "dev" || -z "${BACKUP_PATH}" ]]; then
  echo "Usage: CONFIRM_RESTORE=1 $0 <prod|staging|dev> <backup.db.gz|backup.db>"
  exit 1
fi

if [[ "${CONFIRM_RESTORE:-}" != "1" ]]; then
  echo "Refusing restore without CONFIRM_RESTORE=1."
  exit 1
fi

BASE="/opt/sales-cockpit/${ENV_NAME}"
DB_PATH="${BASE}/data/sales_cockpit.db"
PRE_RESTORE_DIR="/opt/sales-cockpit/backups/${ENV_NAME}/pre-restore"
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
TMP_DB="$(mktemp "/tmp/sales_cockpit_restore_${ENV_NAME}_XXXXXX.db")"

if [[ ! -f "${BACKUP_PATH}" ]]; then
  echo "Backup not found: ${BACKUP_PATH}"
  exit 1
fi

if [[ "${BACKUP_PATH}" == *.gz ]]; then
  gzip -dc "${BACKUP_PATH}" > "${TMP_DB}"
else
  cp "${BACKUP_PATH}" "${TMP_DB}"
fi

sqlite3 "${TMP_DB}" "PRAGMA quick_check;" | grep -qx "ok"

mkdir -p "${PRE_RESTORE_DIR}" "$(dirname "${DB_PATH}")"
if [[ -f "${DB_PATH}" ]]; then
  CURRENT_BACKUP="${PRE_RESTORE_DIR}/sales_cockpit_${ENV_NAME}_before_restore_${TIMESTAMP}.db"
  sqlite3 "${DB_PATH}" ".backup '${CURRENT_BACKUP}'"
  gzip -n "${CURRENT_BACKUP}"
  sha256sum "${CURRENT_BACKUP}.gz" > "${CURRENT_BACKUP}.gz.sha256"
fi

systemctl stop "sales-cockpit-api@${ENV_NAME}.service" "sales-cockpit-ui@${ENV_NAME}.service" 2>/dev/null || true

install -m 0640 -o salescockpit -g salescockpit "${TMP_DB}" "${DB_PATH}"
rm -f "${DB_PATH}-wal" "${DB_PATH}-shm" "${TMP_DB}"

systemctl start "sales-cockpit-api@${ENV_NAME}.service" "sales-cockpit-ui@${ENV_NAME}.service" 2>/dev/null || true

chown -R salescockpit:salescockpit "${PRE_RESTORE_DIR}" 2>/dev/null || true

echo "restore_completed=${DB_PATH}"
