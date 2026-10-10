# HA MQTT Store

HA MQTT Store is a Python/Flask application for collecting Home Assistant and MQTT data into PostgreSQL with pgvector support. It preserves raw source messages while also parsing useful scalar and nested JSON values into historical observations.

> **Documentation:** More detailed deployment, architecture, database schema, table relationships, field definitions, and practical SQL examples are available in the [project Wiki](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/wiki). Start with the [Database Schema and SQL guide](https://github.com/jasakuva/JASA_HAMQTT_STORAGE/wiki/Database-Schema-and-SQL) for database usage.

> **Current status:** Active development. The MQTT ingestion and history views are usable locally. Authentication, production hardening, advanced MQTT decoders, charts, retention jobs, and several HA/linking workflows are still planned.

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
- SQLAlchemy models and Alembic migrations.
- Basic JSON API and `/health` endpoint.

Detailed worker diagnostics, ingestion freshness monitoring, and a system-health dashboard are planned; see the [self-diagnostics and monitoring roadmap](IMPLEMENTATION_PLAN.md#phase-9---self-diagnostics-and-monitoring).

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

The PostgreSQL data is stored in the named Podman volume `hamqtt-postgres-data`.

## Installation with Podman

The documented local setup uses Podman and `podman-compose`. It works on Windows through the Podman machine and is also suitable for Linux.

### Prerequisites

Install:

- Git
- Python 3.12 or newer for local development commands
- Docker Engine with Docker Compose v2, or Podman with a Compose-compatible tool

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

### 3. Start the container engine

On Linux, make sure Docker is running:

```bash
sudo systemctl enable --now docker
```

On Windows with Podman, start the Podman machine:

```powershell
podman machine start podman-machine-default
```

If the machine is already running, Podman will report that and no action is needed.

### 4. Start the services

```bash
docker compose up -d
```

Compose builds the application image, starts PostgreSQL, waits for it to become healthy, applies database migrations, and only then starts the web, MQTT, Home Assistant, and MCP services.

Open the application at:

```text
http://localhost:8000
```

The migration service normally exits successfully after applying the migrations. The database, web, MQTT, and HA services should remain running. If migration fails, inspect it with `docker compose logs migrate`; application services intentionally remain stopped.

## Verify the installation

Check service status:

```bash
docker compose ps -a
```

Check the application and database:

```bash
curl -sS http://localhost:8000/health
docker compose exec postgres pg_isready -U hamqtt -d hamqtt_store
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

The `hamqtt-mcp` container is also available. Configure it under **Settings → AI / MCP service**; MCP is disabled by default and currently supports only read-only access.

## Configure Home Assistant and MQTT

The workers intentionally remain idle until enabled connections and subscriptions have been configured in the application database.

Use the web UI's **Settings** page to configure:

- Home Assistant URL and access token.
- MQTT broker host, port, credentials, and TLS settings.
- MQTT topic subscription filters.

After configuration, inspect the worker logs if data does not appear:

```bash
docker compose logs mqtt-ingestor
docker compose logs ha-ingestor
docker compose logs web
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

## MCP service

The optional MCP service exposes read-only tools and resources for Home Assistant entities, state history, MQTT topics, messages, parsed fields, current values, and the object catalog. It never publishes MQTT messages, calls Home Assistant services, or writes to the database.

After enabling it in Settings, restart the service. The local Streamable HTTP endpoint is `http://localhost:8001/mcp`.

## Updating an existing installation

Use the supplied update script. It builds the new image, creates missing infrastructure, waits for PostgreSQL, applies pending migrations automatically, and recreates only the application containers:

```bash
git pull origin master
bash scripts/update.sh
```

The script supports Docker Compose and Podman Compose. It keeps the fixed HAMQTT container names. If a different, unrecognized container already uses one of those names, the script stops without removing anything and reports the conflict.

The database volume is preserved during updates. Do not remove `hamqtt-postgres-data` unless you intentionally want to delete the local database.

For a first installation, use the same command:

```bash
git clone <repository-url> hamqtt-store
cd hamqtt-store
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD and any deployment-specific values.
bash scripts/update.sh
```

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
docker compose down
docker volume rm hamqtt-postgres-data
```

Only run the volume removal command when a complete development reset is intended.

## Documentation

- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — current implementation status and remaining roadmap.
- [`docs/RESTART_GUIDE.md`](docs/RESTART_GUIDE.md) — how to resume the project after a break.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and data model.
- [`docs/POSTGRESQL_SETUP.md`](docs/POSTGRESQL_SETUP.md) — PostgreSQL/pgvector details.

## License

No license has been selected for this repository yet. Treat the repository as private unless the owner explicitly publishes licensing terms.