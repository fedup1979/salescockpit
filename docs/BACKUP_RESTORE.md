# Backup And Restore

## Scope

Sales Cockpit uses SQLite in WAL mode for the MVP. Before real SchoolDrive staging data or production traffic, every environment needs a simple database backup path.

The scripts below operate on the deployed DigitalOcean layout:

```text
/opt/sales-cockpit/<env>/data/sales_cockpit.db
/opt/sales-cockpit/backups/<env>/
```

Supported environments:

- `prod`
- `staging`
- `dev`

## Create A Backup

Run on the droplet:

```bash
sudo bash /opt/sales-cockpit/staging/app/deploy/scripts/backup_sqlite.sh staging
```

The script:

- uses SQLite `.backup`, so WAL data is included coherently;
- runs `PRAGMA quick_check` on the backup;
- compresses the backup with gzip;
- writes a SHA-256 checksum;
- updates `latest.db.gz`;
- deletes backups older than the retention window.

Default retention is 14 days. Override if needed:

```bash
sudo RETENTION_DAYS=30 bash /opt/sales-cockpit/staging/app/deploy/scripts/backup_sqlite.sh staging
```

Backups are stored in:

```text
/opt/sales-cockpit/backups/staging/
```

## Restore A Backup

Restore is intentionally guarded. It refuses to run unless `CONFIRM_RESTORE=1` is set.

```bash
sudo CONFIRM_RESTORE=1 bash /opt/sales-cockpit/staging/app/deploy/scripts/restore_sqlite.sh staging /opt/sales-cockpit/backups/staging/latest.db.gz
```

The script:

- decompresses the selected backup if needed;
- validates it with `PRAGMA quick_check`;
- creates a pre-restore backup of the current database;
- stops the staging API and UI services;
- replaces the database;
- removes stale WAL/SHM sidecar files;
- restarts the staging services.

Pre-restore backups are stored in:

```text
/opt/sales-cockpit/backups/staging/pre-restore/
```

## Manual Smoke Check After Restore

```bash
curl http://139.59.158.77:8602/health
```

Then open:

```text
http://139.59.158.77:8502
```

## Automated Cron Backups

Install the standard cron file from the deployed app:

```bash
sudo bash /opt/sales-cockpit/staging/app/deploy/scripts/install_backup_cron.sh
```

This writes:

```text
/etc/cron.d/sales-cockpit-backups
```

Schedule, in UTC:

- staging: daily at `01:17`, 14-day retention;
- prod: daily at `01:37`, 30-day retention.

Logs go to:

```text
/var/log/sales-cockpit-backup.log
```

The cron is safe to install once both staging and prod databases exist and restore has been tested once.
