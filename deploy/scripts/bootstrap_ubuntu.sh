#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root or with sudo."
  exit 1
fi

apt-get update
apt-get install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  build-essential \
  curl

if ! id salescockpit >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash salescockpit
fi

mkdir -p /opt/sales-cockpit/{prod,staging,dev}
for env_name in prod staging dev; do
  mkdir -p "/opt/sales-cockpit/${env_name}/data" "/opt/sales-cockpit/${env_name}/storage"
done

chown -R salescockpit:salescockpit /opt/sales-cockpit

echo "Bootstrap complete. Copy env files, install systemd units, then deploy."
