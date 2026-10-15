# HA MQTT Store

![Release](https://img.shields.io/github/v/release/jasakuva/JASA_HAMQTT_STORAGE?display_name=tag&sort=semver)
![Tests](https://img.shields.io/badge/tests-28%20passing-2ea44f)
![Python](https://img.shields.io/badge/python-3.12%2B-3776ab)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791)
![Podman](https://img.shields.io/badge/containers-Podman-892ca0)

HA MQTT Store is a Python/Flask application for collecting Home Assistant and MQTT data into PostgreSQL with pgvector support. It preserves raw source messages while also parsing useful scalar and nested JSON values into historical observations.

> **Documentation:** More detailed deployment, architecture, database schema, table relationships, field definitions, and practical SQL examples are available in the [project Wiki](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/wiki). Start with the [Database Schema and SQL guide](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/wiki/Database-Schema-and-SQL) for database usage.

> **Current status:** Active development. The local dashboard, live MQTT/HA tiles, historical graphs, CSV export, authentication, and core ingestion workflows are implemented. Production hardening, advanced MQTT decoders, retention jobs, and several HA/linking workflows remain planned.

> **Current release:** **0.3.1** adds focused Settings subpages and completes the PostgreSQL 17-compatible pgBackRest backup-service workflow. See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) and the [0.3.1 GitHub release](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/releases/tag/v0.3.1).

Repository: [github.com/jasakuva/JASA_HAMQTT_STORAGE](https://github.com/jasakuva/JASA_HAMQTT_STORAGE)

## Features currently available

- PostgreSQL 17 with pgvector 0.8.7.
- Flask dashboard and browser UI.
- MQTT worker with scalar and nested JSON payload parsing.
- Home Assistant WebSocket state synchronization worker.
- Raw MQTT message storage and normalized observation history.
- MQTT topic overview with topic IDs, topic names, message counts, and recent messages.
- MQTT topic history with parsed fields, current values, observations, and raw message history.
- Field-specific value history linked to each observation's originating raw MQTT message.
- Main dashboard with PostgreSQL counts, compact workspace status, live MQTT feed, and sampled Home Assistant state snapshot.
- Redis-backed dashboard cache that keeps the live UI responsive without replacing PostgreSQL history.
- Interactive Plotly graphs for up to four historical HA entities or MQTT fields.
- CSV export for up to ten historical HA entities or MQTT fields.
- Local web authentication with first-run account setup, hashed passwords, authenticated sessions, logout, and CSRF protection.
- Settings subpages for Authentication, Data sources, Logs, and Backups.
- PostgreSQL 17-compatible pgBackRest full and differential backup service with backup history and error reporting.
- SQLAlchemy models and Alembic migrations.
- Basic JSON API and `/health` endpoint.

Detailed worker heartbeats, ingestion freshness monitoring, and a full system-health dashboard are planned; see the [self-diagnostics and monitoring roadmap](IMPLEMENTATION_PLAN.md#phase-9---self-diagnostics-and-monitoring).

For the full implementation status, see [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). For restarting or resuming work later, see [`docs/RESTART_GUIDE.md`](docs/RESTART_GUIDE.md).

## Architecture

The local stack contains these services:

| Service | Container | Purpose |
|---|---|---|
| PostgreSQL | `hamqtt-postgres` | Durable database and pgvector |
| Migration | `hamqtt-migrate` | Runs `alembic upgrade head` |
| Web | `hamqtt-web` | Flask/Gunicorn UI on port 8000 |
| MQTT worker | `hamqtt-mqtt-ingestor` | Connects to configured MQTT brokers |
| HA worker | `hamqtt-ha-ingestor` | Connects to configured Home Assistant instances |
| MCP | `hamqtt-mcp` | Read-only AI access to stored HA/MQTT data |
| Backup | `hamqtt-backup` | pgBackRest PostgreSQL backup worker |

The PostgreSQL data is stored in the named Podman volume `hamqtt-postgres-data`.

## Installation with Podman

The documented local setup uses Podman and `podman-compose`. It works on Windows through the Podman machine and is also suitable for Linux.

### Prerequisites

Install:

- Git
- Python 3.12 or newer for local development commands
- Podman and `podman-compose`

On Windows, make sure the Podman machine is initialized and running. The commands below use PowerShell syntax where applicable.

### 1. Clone the repository

```powershell
git clone https://github.com/jasakuva/JASA_HAMQTT_STORAGE.git
cd JASA_HAMQTT_STORAGE
```

### 2. Create local environment configuration

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set a local PostgreSQL password. At minimum:

```dotenv
POSTGRES_PASSWORD=change-this-development-password
```

`.env` contains local configuration and must not be committed. The repository `.gitignore` is configured to exclude it.

For a production or HTTPS deployment, set a unique `SECRET_KEY` and change `SESSION_COOKIE_SECURE=true`. The default session duration is 365 days and can be changed with `SESSION_DAYS`.

### 3. Start Podman

On Windows or Linux, start the Podman machine when required:

```powershell
podman machine start
```

If the machine is already running, Podman will report that and no action is needed.

### 4. Validate and start the services

```powershell
podman-compose config
podman-compose up -d --build
```

`podman-compose` builds the application image, starts PostgreSQL, waits for it to become healthy, applies database migrations, and only then starts the web, MQTT, Home Assistant, MCP, cleanup, and backup services.

Open the application at:

```text
http://localhost:8000
```

On the first visit, create the administrator username and password. The login session is remembered for 365 days by default. You can change the credentials later from **Settings → Authentication**.

If the credentials are forgotten, run this from the project directory and restart the web service:

```powershell
podman-compose run --rm --no-deps web python -m hamqtt_store.cli reset-auth
podman-compose up -d --no-deps web
```

The next visit opens the account setup page again. The reset marker is stored in the persistent `hamqtt-app-data` volume.

The migration service normally exits successfully after applying the migrations. The database, web, MQTT, HA, and backup services should remain running. If migration fails, inspect it with `podman-compose logs migrate`; application services intentionally remain stopped.

## Verify the installation

Check service status:

```powershell
podman-compose ps -a
```

Check the application and database:

```powershell
curl -sS http://localhost:8000/health
podman-compose exec postgres pg_isready -U hamqtt -d hamqtt_store
```

Expected application response:

```json
{"database":"ok","status":"ok"}
```

Expected services:

- `hamqtt-postgres` — healthy
- `hamqtt-web` — running
- `hamqtt-mqtt-ingestor` — running
- `hamqtt-ha-ingestor` — running
- `hamqtt-migrate` — exited with status 0 after migration

The `hamqtt-mcp` container is also available. Configure it under **Settings → Data sources → AI / MCP service**; MCP is disabled by default and currently supports only read-only access.

## Configure Home Assistant and MQTT

The workers intentionally remain idle until enabled connections and subscriptions have been configured in the application database.

Use the web UI's **Settings → Data sources** page to configure:

- Home Assistant URL and access token.
- MQTT broker host, port, credentials, and TLS settings.
- MQTT topic subscription filters.

After configuration, inspect the worker logs if data does not appear:

```powershell
podman-compose logs mqtt-ingestor
podman-compose logs ha-ingestor
podman-compose logs web
```

## MQTT history workflow

1. Open **MQTT data**.
2. The upper topic list shows topic ID, topic name, message count, and last-seen time.
3. The lower recent-message list shows topic ID, topic name, payload type, payload, and received time.
4. Select **View history** for a topic.
5. The topic page shows current parsed fields, observation history, and raw message history.
6. Select **View values** for a field.
7. The field page shows newest-first values and an expandable raw MQTT message for each observation.

Each observation is linked to its source message through `mqtt_observations.source_message_id`.

## Dashboard, graphs, and export

The main dashboard combines durable database counters with a small live-data path. MQTT and Home Assistant workers write compact updates to Redis after their PostgreSQL writes. The browser polls the MQTT endpoint every two seconds and a sampled Home Assistant endpoint every ten seconds, updating only the feed tiles. Redis is best-effort and bounded; PostgreSQL remains the source of truth for history, graphs, and exports.

The **Graphs** page reads historical HA state and MQTT observation rows, supports one to four selected series, and uses Plotly zooming, a range slider, and time-range buttons. The **Export CSV** page reads the same historical sources, supports one to ten series, and returns timestamped rows with source, identifier, value, type, unit, and state columns.

See [`docs/DASHBOARD_DATA_FLOW.md`](docs/DASHBOARD_DATA_FLOW.md) for the complete live-data flow, Redis keys, polling behavior, graph downsampling, export format, and troubleshooting steps.

## Authentication

On a new installation, open the web UI and complete the one-time setup at `/setup` with a username and password of at least six characters. The application stores a password hash, not the plaintext password. After setup, application pages require login at `/login`; use **Sign out** in the top bar to end the session.

State-changing form submissions use CSRF tokens, and changing the account credentials invalidates existing sessions. The unauthenticated `/health` endpoint remains available for container health checks. Review [`docs/SECURITY_TODO.md`](docs/SECURITY_TODO.md) before exposing the service beyond a trusted network; HTTPS, throttling, audit logging, and other production hardening are not supplied by the local Flask deployment alone.

## MCP service

The optional MCP service exposes read-only tools and resources for Home Assistant entities, state history, MQTT topics, messages, parsed fields, current values, and the object catalog. It never publishes MQTT messages, calls Home Assistant services, or writes to the database.

After enabling it in Settings, restart the service. The local Streamable HTTP endpoint is `http://localhost:8001/mcp`.

## Updating an existing installation

Use the supplied update script. It builds the new image, creates missing infrastructure, waits for PostgreSQL, applies pending migrations automatically, and recreates only the application containers:

```bash
git fetch origin
git checkout v0.3.1
bash scripts/update.sh
```

The script uses the project’s Podman and `podman-compose` workflow. It keeps the fixed HAMQTT container names. If a different, unrecognized container already uses one of those names, the script stops without removing anything and reports the conflict.

The database volume is preserved during updates. Do not remove `hamqtt-postgres-data` or `hamqtt-app-data` unless you intentionally want to delete application data.

For Windows Podman users, `start-hamqtt.cmd` starts the stack and `update-hamqtt.cmd` builds and updates it while preserving named volumes.

For a first installation, use the same command:

```powershell
git clone <repository-url> hamqtt-store
cd hamqtt-store
Copy-Item .env.example .env
# Edit .env and set POSTGRES_PASSWORD and any deployment-specific values.
bash scripts/update.sh
```

## Docker Compose compatibility

Podman with `podman-compose` is the canonical and tested workflow for this
repository. Docker users can use the same `compose.yml` with Docker Compose,
but should replace each `podman-compose` command with `docker compose` and
omit `podman machine start`. Do not mix Podman and Docker commands in the same
startup or update procedure.

## Local development

Install the project and development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the test suite:

```powershell
python -m pytest -q
```

Run migrations against the configured database:

```powershell
python -m alembic upgrade head
```

Other useful checks:

```powershell
python -m compileall -q src
python tools/validate_docs.py
git diff --check
```

## Data and reset safety

The database uses the named volume `hamqtt-postgres-data`. Removing containers does not remove database data.

To intentionally reset all local database data:

```powershell
podman-compose down
podman volume rm hamqtt-postgres-data
```

Only run the volume removal command when a complete development reset is intended.

## Documentation

- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — current implementation status and remaining roadmap.
- [`docs/RESTART_GUIDE.md`](docs/RESTART_GUIDE.md) — how to resume the project after a break.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and data model.
- [`docs/DASHBOARD_DATA_FLOW.md`](docs/DASHBOARD_DATA_FLOW.md) — dashboard live-data pipeline, graphs, CSV export, and troubleshooting.
- [`docs/POSTGRESQL_SETUP.md`](docs/POSTGRESQL_SETUP.md) — PostgreSQL/pgvector details.
- [`docs/BACKUPS.md`](docs/BACKUPS.md) — pgBackRest backup configuration, verification, and restore safety.
- [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md) — current security review and release limitations.

## License

No license has been selected for this repository yet. Treat the repository as private unless the owner explicitly publishes licensing terms.