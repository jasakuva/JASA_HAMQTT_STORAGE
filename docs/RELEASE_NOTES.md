# HA MQTT Store 0.3.3

Release date: 2026-10-18

## Highlights

Version 0.3.3 adds secure database recovery, safer cross-platform container
management, published GitHub Container Registry images, and a self-contained
Linux Docker installer. A new user can download one script from `master` and
install the complete stack without cloning or building the source repository.

## Single-file Linux installer

- Added the self-contained `deploy/install.sh` first-install script.
- Downloads are supported with either `wget` or `curl` directly from `master`.
- Uses the stable `latest` image tag by default and accepts a fixed tag through
  `--version VERSION` or a positional version argument.
- Creates `./jasa_hamqtt_storage` and generates Compose, `.env`, pgBackRest, and
  PostgreSQL initialization files without requiring adjacent repository assets.
- Generates protected database and application secrets and sets `.env` mode to
  `0600`.
- Creates persistent volumes and the external network, pulls published images,
  validates pgBackRest, runs migrations, starts services, and verifies health.
- Refuses an existing installation directory or conflicting container names and
  never deletes persistent volumes during installation or failure handling.
- Runs the backup service as UID/GID `999:999` so the shared pgBackRest
  repository retains compatible ownership.

Install the latest stable release:

```bash
wget -O install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh
```

Install exactly version 0.3.3:

```bash
./install-hamqtt.sh --version 0.3.3
```

## Published container images

- Added GitHub Actions publishing for `hamqtt-store`,
  `hamqtt-postgres-pgbackrest`, and `hamqtt-backup-pgbackrest` on `linux/amd64`.
- The release publishes both the `0.3.3` and `latest` image tags.
- Added OCI image version, revision, source, title, and description metadata.
- Added `compose.github.yml` and `update-from-github.sh` for existing Linux
  Docker installations that pull published images instead of building locally.

## Database backup and recovery

- Added authenticated browser upload, listing, download, validation, and
  recovery for PostgreSQL custom-format portable dumps.
- Added a dedicated recovery coordinator instead of exposing the container
  engine socket to the web application.
- Added SHA-256 tracking and PostgreSQL 17 `pg_restore --list` validation before
  a dump can be selected for recovery.
- Added administrator-password and exact confirmation-phrase checks before a
  destructive restore.
- Added maintenance mode that pauses web database access, MCP, ingestion,
  cleanup, and backups during recovery.
- Added a verified pre-restore rollback dump and automatic rollback when restore
  or migration fails.
- Persisted recovery job state outside the database being replaced so status and
  diagnostics survive recovery of an older dump.

## Container management and repository layout

- Added the unified `hamqtt.sh` launcher for Podman or Docker on Unix-like hosts,
  with start, stop, update, rebuild, status, logs, engine selection, and dry-run
  support.
- Kept Podman with `podman-compose` as the canonical source-checkout workflow.
- Added safer Windows start, stop, update, and rebuild scripts.
- Reorganized build and configuration assets into clearer `build/`, `config/`,
  `deploy/`, `docs/`, and `tools/` locations and removed generated artifacts.
- Improved backup scheduling and diagnostics so scheduler failures are visible
  and backup timing remains stable.

## Validation

- 53 automated Python tests passed.
- Python compilation passed.
- Documentation validation passed.
- Root and standalone deployment Compose configuration rendered successfully.
- Installer regression coverage verifies the default `latest` tag, explicit
  version selection, generated files, permissions, pgBackRest ownership, and
  rejection of invalid or existing installations.
- `git diff --check` passed.

## Upgrade

For an existing source-checkout installation:

```bash
git fetch origin
git checkout v0.3.3
./hamqtt.sh update
```

The update workflow runs migrations before application services and preserves
`hamqtt-postgres-data`, `hamqtt-app-data`, and the configured backup repository.
Never use `down -v` during a routine update.

## Known limitations

- Published images currently target `linux/amd64`.
- The single-file installer requires Linux, Docker Engine, Docker Compose v2,
  and `sudo` for non-root users when assigning backup-directory ownership.
- The installer is for a new installation and intentionally refuses to overwrite
  `./jasa_hamqtt_storage`; use the documented update workflow for an existing
  deployment.
- HTTPS termination, login throttling, audit logging, external secret
  management, fine-grained authorization, and authenticated MCP transport remain
  deployment or future hardening work.

---

# HA MQTT Store 0.3.2

Release date: 2026-10-16

## Highlights

Version 0.3.2 improves backup portability and control, makes graph range selection reliable, and keeps Zigbee2MQTT bridge/system data out of the Graph and Export selectors while preserving stored history.

## Graph and export usability

- Replaced Plotly's embedded SVG range-selector controls with stable HTML buttons for `1h`, `6h`, `1d`, and `all`.
- Kept Plotly zooming, panning, scroll zoom, and the range slider available.
- Filtered `zigbee2mqtt/bridge` and all descendant topics from the shared Graph/Export catalog.
- Kept normal Zigbee2MQTT device topics selectable.
- Applied filtering only to the selector catalog; existing raw MQTT messages and observations are not deleted.
- Added regression coverage for graph range controls and bridge-topic filtering.

If a bookmarked graph URL contains an object ID that is now filtered, open `/graph` without the stale query parameter and select the desired series again.

## PostgreSQL backups

- Added independent low, medium, and high schedule profiles for full and differential backups.
- Added independent low, medium, and high retention profiles.
- Added manual PostgreSQL portable dumps in custom format with compression and no owner metadata.
- Added an optional daily portable-dump schedule.
- Added portable-dump retention alongside pgBackRest retention.
- Improved the Backups settings layout and action controls.
- Ensured the backup image includes the PostgreSQL 17 client used by `pg_dump`.

## Validation

- 33 automated tests passing.
- Python compilation passing.
- Documentation validation passing.
- Compose configuration rendering successfully.
- `git diff --check` passing.
- Recreated the web container and confirmed `GET /health` returned healthy.

## Upgrade

From an existing installation:

```bash
git fetch origin
git checkout v0.3.2
bash scripts/update.sh
```

The update workflow uses Podman and `podman-compose`, runs migrations before application services, and preserves the PostgreSQL and application data volumes. Do **not** use `down -v`, and do not remove `hamqtt-postgres-data`, `hamqtt-app-data`, or the configured backup repository during a routine upgrade.

---

# HA MQTT Store 0.3.1

Release date: 2026-10-15

## Highlights

Version 0.3.1 focuses on administration and data safety. It splits the large Settings page into focused subpages and completes the PostgreSQL 17-compatible pgBackRest backup-service fixes.

## Settings UI

- Split Settings into **Authentication**, **Data sources**, **Logs**, and **Backups** subpages.
- Added direct, bookmarkable routes for each settings section.
- Added active tab navigation and section-aware save redirects.
- Preserved the existing `/settings` and `/logs` compatibility routes.
- Kept MCP configuration under **Settings → Data sources**.

## PostgreSQL backups

- Added the PostgreSQL 17-compatible dedicated pgBackRest backup service.
- Enabled and validated WAL archiving and pgBackRest stanza/check operations.
- Corrected the backup worker command to avoid unsupported `--output=json` usage.
- Added detailed backup error reporting and regression coverage.
- Retained non-destructive update behavior for PostgreSQL and application volumes.
- Documented backup repository configuration, manual runs, verification, and restore safety.

## Validation

- 28 automated tests passing.
- Python compilation passing.
- Documentation validation passing.
- Compose configuration rendering successfully.
- `git diff --check` passing.

## Upgrade

From an existing installation:

```bash
git fetch origin
git checkout v0.3.1
bash scripts/update.sh
```

For Docker Compose installations, use the checked-out release and run the equivalent non-destructive workflow:

```bash
docker compose build
docker compose down
docker compose up -d --no-deps postgres redis
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps web mqtt-ingestor ha-ingestor cleanup mcp backup
```

Do **not** use `docker compose down -v`, and do not remove `hamqtt-postgres-data`, `hamqtt-app-data`, or the configured backup repository.

---

# HA MQTT Store 0.3.0

Release date: 2026-10-14

## Highlights

Version 0.3.0 delivers the complete dashboard live-data and historical-analysis workflow, a more compact dashboard experience, and safer operational tooling for updating and starting installations on Windows and Linux.

## Authentication and security

- Added local web-application authentication with a first-run setup page at `/setup`.
- Added username and password sign-in at `/login` and sign-out from the application shell.
- Passwords are stored as Werkzeug password hashes, never as plaintext.
- Protected application routes require an authenticated session; `/health`, static assets, setup, login, and logout remain available for their intended bootstrap or operational purposes.
- Added CSRF tokens for state-changing form submissions.
- Added session-version invalidation so changing credentials ends existing sessions.
- Added authentication database migration `0007_application_authentication` and authentication tests.
- HTTPS termination, login throttling, audit logging, and broader production hardening remain deployment responsibilities and are tracked in `docs/SECURITY_TODO.md`.

## Dashboard and analysis

- Added a live MQTT dashboard feed backed by a bounded Redis cache.
- Added a sampled Home Assistant live snapshot backed by Redis.
- Added browser polling with MQTT refreshes every 2 seconds and Home Assistant refreshes every 10 seconds.
- Kept PostgreSQL as the durable source of truth for current data, history, graphs, and exports.
- Added interactive Plotly graphs for historical Home Assistant entities and MQTT fields.
- Added graph time ranges, range controls, zooming, panning, and numeric downsampling.
- Added CSV export for selected historical Home Assistant entities and MQTT fields.
- Added dashboard live/offline status behavior and documented failure behavior when Redis or a worker is unavailable.
- Removed the dashboard's duplicate “Configure sources” action; source configuration remains available in Settings.
- Reduced the default dashboard scale so cards and panels use the workspace more efficiently.
- Added a custom HA MQTT Store browser-tab favicon.

## Operations and deployment

- Added `start-hamqtt.cmd` for Windows Podman startup.
- Added `update-hamqtt.cmd` for Windows Podman updates.
- The Windows scripts wait for PostgreSQL and Redis health, run migrations, preserve named volumes, and start application services without destructive volume cleanup.
- Maintained `scripts/update.sh` for Linux-style Podman deployments.
- Documented Docker Compose update compatibility for Linux installations using Docker.
- Added operational documentation for dashboard data flow, graphs, CSV export, troubleshooting, and restart procedures.

## Data safety

- Redis remains a bounded, best-effort live-dashboard cache rather than the system of record.
- PostgreSQL history is preserved during application updates.
- Upgrade instructions explicitly avoid `down -v` and database-volume deletion.
- Database migrations run before application services are started.

## Upgrade

From an existing installation on an older release:

```bash
cd /opt/jasa-hamqtt-store
git fetch origin
git checkout v0.3.1
bash scripts/update.sh
```

For Docker Compose installations, use the same checked-out release and run the equivalent non-destructive workflow:

```bash
docker compose build
docker compose down
docker compose up -d --no-deps postgres redis
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps web mqtt-ingestor ha-ingestor cleanup mcp
```

Do **not** use `docker compose down -v`, and do not remove `hamqtt-postgres-data` or `hamqtt-app-data`.

## Validation

- 20 automated tests passing.
- Python compilation passing.
- Documentation validation passing.
- Compose configuration rendering successfully.
- `git diff --check` passing.