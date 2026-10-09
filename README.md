# HA MQTT Store

HA MQTT Store is a Python/Flask application for collecting Home Assistant and MQTT data into PostgreSQL with pgvector support. It preserves raw source messages while also parsing useful scalar and nested JSON values into historical observations.

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

The PostgreSQL data is stored in the named Podman volume `hamqtt-postgres-data`.

## Installation with Podman

The documented local setup uses Podman and `podman-compose`. It works on Windows through the Podman machine and is also suitable for Linux.

### Prerequisites

Install:

- Git
- Python 3.12 or newer for local development commands
- Podman
- `podman-compose`

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

### 3. Start Podman

```powershell
podman machine start podman-machine-default
```

If the machine is already running, Podman will report that and no action is needed.

### 4. Build the application image

```powershell
podman build -t localhost/hamqtt-store:dev .
```

The image includes the Python package, dependencies, source code, templates, static files, and migrations.

### 5. Start the services

```powershell
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor
```

The `--in-pod false` option matches the local standalone-container setup and avoids Podman pod naming conflicts.

Open the application at:

```text
http://localhost:8000
```

The migration service normally exits successfully after applying the migrations. The database, web, MQTT, and HA services should remain running.

## Verify the installation

Check service status:

```powershell
podman ps -a
```

Check the application and database:

```powershell
curl.exe -sS http://localhost:8000/health
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
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

## Configure Home Assistant and MQTT

The workers intentionally remain idle until enabled connections and subscriptions have been configured in the application database.

Use the web UI's **Settings** page to configure:

- Home Assistant URL and access token.
- MQTT broker host, port, credentials, and TLS settings.
- MQTT topic subscription filters.

After configuration, inspect the worker logs if data does not appear:

```powershell
podman logs hamqtt-mqtt-ingestor
podman logs hamqtt-ha-ingestor
podman logs hamqtt-web
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

## Updating an existing installation

Pull the latest code, rebuild the image, and recreate the application containers:

```powershell
git pull origin master
podman build -t localhost/hamqtt-store:dev .
podman rm -f hamqtt-migrate hamqtt-web hamqtt-mqtt-ingestor hamqtt-ha-ingestor 2>$null
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor
```

If the PostgreSQL container also needs to be recreated, it is safe to remove the container while preserving the named data volume:

```powershell
podman rm -f hamqtt-postgres
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor
```

Do **not** remove `hamqtt-postgres-data` unless you intentionally want to delete the local database.

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
podman-compose --in-pod false down
podman volume rm hamqtt-postgres-data
```

Only run the volume removal command when a complete development reset is intended.

## Documentation

- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — current implementation status and remaining roadmap.
- [`docs/RESTART_GUIDE.md`](docs/RESTART_GUIDE.md) — how to resume the project after a break.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and data model.
- [`docs/POSTGRESQL_SETUP.md`](docs/POSTGRESQL_SETUP.md) — PostgreSQL/pgvector details.

## License

No license has been selected for this repository yet. Treat the repository as private unless the owner explicitly publishes licensing terms.