# Release 0.3.3

Release date: 2026-10-18

HA MQTT Store 0.3.3 adds secure database recovery, unified container launchers,
published GHCR images, and a self-contained Linux Docker installer.

## Install on a new Linux Docker host

```bash
wget -O install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh
```

The installer uses `latest` by default. To select this release explicitly:

```bash
./install-hamqtt.sh --version 0.3.3
```

It creates `./jasa_hamqtt_storage`, generates secrets and deployment files,
pulls the published images, initializes pgBackRest, runs migrations, and starts
the complete stack. It refuses to overwrite an existing installation and never
deletes persistent volumes.

## Other highlights

- Browser-driven upload, validation, restore, and rollback for portable
  PostgreSQL dumps through a dedicated recovery service.
- Maintenance mode pauses database-dependent application work during recovery.
- Unified `hamqtt.sh` management for Podman and Docker source checkouts.
- Published `hamqtt-store`, `hamqtt-postgres-pgbackrest`, and
  `hamqtt-backup-pgbackrest` images tagged `0.3.3` and `latest`.
- Improved backup scheduler stability and diagnostics.

## Upgrade an existing source checkout

```bash
git fetch origin
git checkout v0.3.3
./hamqtt.sh update
```

Do not use `down -v`. Preserve `hamqtt-postgres-data`, `hamqtt-app-data`, and the
configured backup repository.

## Validation

- 53 automated Python tests passed.
- Python compilation and documentation validation passed.
- Root and standalone deployment Compose rendering passed.
- The standalone installer regression passed in Ubuntu 24.04, and
  `git diff --check` passed.

## Known limitations

Published images currently target `linux/amd64`. The single-file installer is
for a new Linux Docker installation and requires Docker Compose v2. Existing
installations should use the update workflow rather than rerunning the installer.