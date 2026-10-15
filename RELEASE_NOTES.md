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