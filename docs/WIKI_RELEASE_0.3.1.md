# Release 0.3.1

Release date: 2026-10-15

HA MQTT Store 0.3.1 improves administration and data safety with focused
Settings subpages and a PostgreSQL 17-compatible pgBackRest backup workflow.

## Highlights

- Settings is split into **Authentication**, **Data sources**, **Logs**, and
  **Backups**.
- Each settings section has a direct URL and active tab navigation.
- Existing `/settings` and `/logs` routes remain compatible.
- MCP is configured under **Settings → Data sources**.
- PostgreSQL 17 and pgBackRest WAL archiving, stanza checks, and backup
  operations were validated.
- The backup worker no longer uses the unsupported `--output=json` option.
- Backup failures now include useful error details in the UI and application
  records.

## Upgrade

```bash
git fetch origin
git checkout v0.3.1
bash scripts/update.sh
```

The update workflow runs migrations before application services and preserves
the PostgreSQL data volume, application data volume, and configured backup
repository. Never use `down -v` during a routine upgrade.

## Backup verification

After the services start, verify the PostgreSQL and pgBackRest services:

```powershell
podman-compose ps -a
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
podman exec hamqtt-backup pgbackrest --stanza=hamqtt check
podman exec hamqtt-backup pgbackrest --stanza=hamqtt info
```

Configure schedules and run manual full or differential backups under
**Settings → Backups**. See the repository's [`docs/BACKUPS.md`](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/blob/0.3.1/docs/BACKUPS.md)
for repository configuration and restore-safety guidance.

## Validation

- 28 automated tests passed.
- Python compilation passed.
- Documentation validation passed.
- Compose configuration passed.
- `git diff --check` passed.

## Known limitations

This release remains intended for controlled local/LAN deployments. Fine-grained
authorization, HTTPS/TLS deployment, login throttling, audit logging, external
secret management, and authenticated MCP transport remain security work items.