#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or with sudo."
  exit 1
fi

CRON_FILE="/etc/cron.d/sales-cockpit-backups"
LOG_FILE="/var/log/sales-cockpit-backup.log"

for ENV_NAME in staging prod; do
  SCRIPT="/opt/sales-cockpit/${ENV_NAME}/app/deploy/scripts/backup_sqlite.sh"
  DB_PATH="/opt/sales-cockpit/${ENV_NAME}/data/sales_cockpit.db"
  if [[ ! -f "${SCRIPT}" ]]; then
    echo "Missing backup script for ${ENV_NAME}: ${SCRIPT}"
    exit 1
  fi
  if [[ ! -f "${DB_PATH}" ]]; then
    echo "Missing database for ${ENV_NAME}: ${DB_PATH}"
    exit 1
  fi
done

cat > "${CRON_FILE}" <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Sales Cockpit SQLite backups. Times are UTC.
# Staging keeps 14 days. Prod keeps 30 days.
17 1 * * * root /usr/bin/flock -n /run/sales-cockpit-backup-staging.lock bash /opt/sales-cockpit/staging/app/deploy/scripts/backup_sqlite.sh staging >> /var/log/sales-cockpit-backup.log 2>&1
37 1 * * * root /usr/bin/flock -n /run/sales-cockpit-backup-prod.lock env RETENTION_DAYS=30 bash /opt/sales-cockpit/prod/app/deploy/scripts/backup_sqlite.sh prod >> /var/log/sales-cockpit-backup.log 2>&1
EOF

chmod 0644 "${CRON_FILE}"
touch "${LOG_FILE}"
chown root:root "${CRON_FILE}" "${LOG_FILE}"
chmod 0644 "${LOG_FILE}"

echo "backup_cron_installed=${CRON_FILE}"
