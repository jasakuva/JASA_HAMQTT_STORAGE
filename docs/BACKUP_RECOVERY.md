# Portable dump upload and recovery

HA MQTT Store portable backups are PostgreSQL custom-format dump files created
with `pg_dump --format=custom`. Authenticated administrators can list, download,
upload, validate, and recover them from **Settings → Backup files and recovery**.
The destructive work is performed by the dedicated `hamqtt-recovery` service,
not by the Flask request and not through a Podman socket mount.

## Browser upload and recovery

1. Open **Settings → Backup files and recovery** and select a `.dump` file.
   Uploads are streamed to `hamqtt-app-data/recovery/uploads` under an opaque
   generated ID. The original filename is display-only and cannot choose the
   stored path. `RECOVERY_MAX_UPLOAD_MB` controls the size limit and defaults to
   1024 MB.
2. The recovery coordinator calculates SHA-256 and runs PostgreSQL 17
   `pg_restore --list`. Invalid files remain recorded with an error and cannot be
   selected for recovery.
3. For a validated job, enter the current administrator password and type
   `RESTORE DATABASE` exactly. CSRF protection applies to both upload and
   confirmation requests. Only one recovery can be active.
4. The coordinator writes a shared maintenance marker. Web requests receive a
   maintenance page, MCP access is denied, and backup, cleanup, HA, and MQTT
   workers pause before new database work.
5. Before replacing the database, the coordinator creates and validates a fresh
   rollback dump in `BACKUP_HOST_PATH/dumps`. If this step fails, the active
   database is not replaced.
6. The coordinator disconnects remaining clients, drops and recreates the
   application database, restores with `pg_restore --exit-on-error --no-owner`,
   and runs `alembic upgrade head`.
7. If restore or migration fails, the coordinator automatically attempts the
   same replace-and-migrate sequence with the verified rollback dump. Job state,
   uploader, confirmer, SHA-256, timestamps, output, and errors remain in
   `hamqtt-app-data/recovery/jobs`, so restoring an older database cannot erase
   the active job record.
8. Maintenance mode clears only after success or successful rollback. If both
   recovery and rollback fail, maintenance remains active and an operator must
   use the offline procedure below.

Rebuild and start the new service after upgrading:

```powershell
Set-Location "C:\Users\janne\Documents\VS_HAMQTT_STORE"
rebuild-hamqtt.cmd
podman-compose ps -a
podman-compose logs --tail 100 recovery
```

No persistent volume deletion is required or permitted. The web container keeps
the backup repository read-only; only the recovery coordinator receives write
access for verified rollback dumps.

## Recover a portable dump with Podman

Run these commands from:

```text
C:\Users\janne\Documents\VS_HAMQTT_STORE
```

The examples assume the default container name `hamqtt-postgres`, database
`hamqtt_store`, and user `hamqtt`. If `.env` overrides them, use those values.

1. Inspect the current services and confirm the dump you intend to restore:

   ```powershell
   Set-Location "C:\Users\janne\Documents\VS_HAMQTT_STORE"
   podman-compose ps -a
   podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
   podman exec hamqtt-postgres mkdir -p /var/lib/pgbackrest/dumps
   podman exec hamqtt-postgres pg_dump --format=custom --compress=6 --no-owner --username=hamqtt --dbname=hamqtt_store --file=/var/lib/pgbackrest/dumps/hamqtt-store-before-restore.dump
   podman exec hamqtt-postgres pg_restore --list /var/lib/pgbackrest/dumps/hamqtt-store-before-restore.dump
   ```

   The first `pg_dump` creates a rollback dump in the configured backup host
   directory. Do not continue if it or `pg_restore --list` fails.

2. If the selected dump was downloaded through the browser rather than already
   present under `BACKUP_HOST_PATH/dumps`, copy it into the PostgreSQL container:

   ```powershell
   podman cp "C:\path\to\hamqtt-store-YYYYMMDD-HHMMSS.dump" hamqtt-postgres:/tmp/hamqtt-restore.dump
   podman exec hamqtt-postgres pg_restore --list /tmp/hamqtt-restore.dump
   ```

   If it is already in the repository, use
   `/var/lib/pgbackrest/dumps/<selected-file>.dump` in the later commands.

3. Stop every HAMQTT service that can connect to PostgreSQL. Keep PostgreSQL
   and Redis running, and do not remove containers or volumes:

   ```powershell
   podman-compose stop web mqtt-ingestor ha-ingestor cleanup mcp backup recovery
   podman-compose ps -a
   ```

4. Replace the database and restore the selected dump. This is the destructive
   step; verify the filename before running it:

   ```powershell
   podman exec hamqtt-postgres dropdb --force --username=hamqtt hamqtt_store
   podman exec hamqtt-postgres createdb --username=hamqtt --owner=hamqtt hamqtt_store
   podman exec hamqtt-postgres pg_restore --exit-on-error --no-owner --username=hamqtt --dbname=hamqtt_store /tmp/hamqtt-restore.dump
   ```

5. Apply migrations, restart services, and validate health:

   ```powershell
   podman-compose run --rm migrate
   podman-compose up -d web mqtt-ingestor ha-ingestor cleanup mcp backup recovery
   podman-compose ps -a
   podman-compose logs --tail 100 web
   Invoke-WebRequest http://localhost:8000/health
   ```

6. Sign in and verify settings, object counts, recent HA/MQTT data, and backup
   status. Remove `/tmp/hamqtt-restore.dump` only after validation:

   ```powershell
   podman exec hamqtt-postgres rm -f /tmp/hamqtt-restore.dump
   ```

Never use `podman-compose down -v` or remove `hamqtt-postgres-data` or
`hamqtt-app-data` during recovery.

## Validation status and remaining production work

Unit and route tests cover authenticated upload, CSRF, extension and size
limits, opaque storage names, SHA-256, malformed/tampered archives, confirmation,
duplicate active jobs, maintenance state, and recovery state transitions. The
Compose configuration and Python compilation are also validated.

The destructive restore and automatic rollback paths must still be exercised in
disposable integration containers before this workflow is considered
production-certified. Until that test is completed, retain the offline procedure
above as the operator fallback and verify recent backups independently.