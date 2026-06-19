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

## Cron Recommendation

For staging, manual backups before integration tests are enough. Before production cutover, add a daily cron:

```cron
15 2 * * * root bash /opt/sales-cockpit/prod/app/deploy/scripts/backup_sqlite.sh prod >> /var/log/sales-cockpit-backup.log 2>&1
```

Do not enable automated production backups before the prod environment exists and the restore path has been tested once.
