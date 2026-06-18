#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or with sudo."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cp "${DEPLOY_DIR}/systemd/sales-cockpit-ui@.service" /etc/systemd/system/
cp "${DEPLOY_DIR}/systemd/sales-cockpit-api@.service" /etc/systemd/system/

systemctl daemon-reload

echo "Systemd units installed."
echo "Use: systemctl enable --now sales-cockpit-ui@staging sales-cockpit-api@staging"
