# PostgreSQL backups

HAMQTT runs PostgreSQL backups in the dedicated `hamqtt-backup` service. The
service uses pgBackRest and does not run inside Flask or the web worker.

## Local repository

Set `BACKUP_HOST_PATH` in `.env` to a host directory with enough space. The
default is `./backups`. This repository is separate from the
`hamqtt-postgres-data` volume and should be included in the host's normal
backup strategy.

The backup settings use two independent plans:

### Schedule plan

- **Low:** full backup every 7 days and differential backup every 24 hours.
- **Medium:** full backup every day and differential backup every 6 hours.
- **High:** full backup every day and differential backup every hour.

### Retention plan

- **Low:** retain 2 pgBackRest full backup sets and 2 portable dumps.
- **Medium:** retain 5 pgBackRest full backup sets and 5 portable dumps.
- **High:** retain 14 pgBackRest full backup sets and 14 portable dumps.

The **Create portable dump daily** option is independent of both plans. Manual
portable dumps are always available; enabling the option queues one dump per day.

These values can be changed in **Settings → Backups**. A manual run
is queued for the backup service rather than executed by the web request.

The Backups page also shows the repository size, recent backup runs, status,
completion time, and recorded error details. Use **Run full backup now**, **Run
differential now**, or **Create portable dump now** for an on-demand request.
Authenticated users can list, download, upload, validate, and recover portable
`.dump` files from **Settings → Backup files and recovery**. The public web
container receives read-only access to the backup repository; uploaded files and
durable recovery job records are stored in `hamqtt-app-data`.

## PostgreSQL 17 and pgBackRest validation

The backup image and PostgreSQL image are validated together for PostgreSQL 17.
The backup worker uses pgBackRest to read the configured stanza and repository;
it does not use the unsupported `--output=json` option. Validate the installation
before relying on scheduled backups:

```powershell
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
podman exec hamqtt-postgres psql -U hamqtt -d hamqtt_store -c "SHOW archive_mode;"
podman exec hamqtt-backup pgbackrest --stanza=hamqtt check
podman exec hamqtt-backup pgbackrest --stanza=hamqtt info
```

The exact container command may vary when a custom Compose project name is used;
use `podman-compose ps -a` to identify the active backup container.

## Startup and migration

The normal Podman workflow starts the backup service after migrations:

```text
podman-compose run --rm --no-deps migrate
podman-compose up -d --no-deps web mqtt-ingestor ha-ingestor mcp cleanup backup recovery
```

The existing `start-hamqtt.cmd`, `update-hamqtt.cmd`, and
`scripts/update.sh` commands include `backup` and `recovery` automatically. They
preserve the PostgreSQL and application volumes.

## Restore workflow

Browser recovery is implemented as an authenticated staged job. The dedicated
`hamqtt-recovery` service validates uploads, creates a verified rollback dump,
places the application in maintenance mode, replaces the database, runs Alembic,
and attempts automatic rollback on failure. It does not mount the Podman socket.
For the complete workflow and the offline fallback commands, see
[`BACKUP_RECOVERY.md`](BACKUP_RECOVERY.md). Do not delete
`hamqtt-postgres-data`, `hamqtt-app-data`, or the backup repository during
recovery or routine updates.

Remote providers (S3-compatible storage, SFTP, and rclone/Google Drive) are
represented in the configuration model but are not enabled until their
credential storage and provider adapters are implemented.