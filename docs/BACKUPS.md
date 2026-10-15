# PostgreSQL backups

HAMQTT runs PostgreSQL backups in the dedicated `hamqtt-backup` service. The
service uses pgBackRest and does not run inside Flask or the web worker.

## Local repository

Set `BACKUP_HOST_PATH` in `.env` to a host directory with enough space. The
default is `./backups`. This repository is separate from the
`hamqtt-postgres-data` volume and should be included in the host's normal
backup strategy.

The default schedule is:

- full backup every 7 days;
- differential backup every 24 hours;
- retain 4 full backup sets and 14 differential backups.

These values can be changed in **Settings → Backups**. A manual run
is queued for the backup service rather than executed by the web request.

The Backups page also shows the repository size, recent backup runs, status, completion time, and recorded error details. Use **Run full backup now** or **Run differential now** for an on-demand request.

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
podman-compose up -d --no-deps web mqtt-ingestor ha-ingestor mcp cleanup backup
```

The existing `start-hamqtt.cmd`, `update-hamqtt.cmd`, and
`scripts/update.sh` commands include `backup` automatically. They preserve the
PostgreSQL and application volumes.

## Restore workflow

Restore is intentionally an administrative command-line operation, not a web
action. Stop application services first, then use pgBackRest in the backup
image/container with an explicitly selected backup label. Validate the
restored database before starting the application services again. Do not
delete `hamqtt-postgres-data` or the backup repository during routine updates.

Remote providers (S3-compatible storage, SFTP, and rclone/Google Drive) are
represented in the configuration model but are not enabled until their
credential storage and provider adapters are implemented.