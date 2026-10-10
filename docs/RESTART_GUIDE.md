# HA MQTT Store Restart Guide

This guide is for returning to the project after a break or starting development on another machine. It describes the current repository state as of October 9, 2026.

## 1. What this project is

HA MQTT Store is a Python/Flask application that stores Home Assistant and MQTT data in PostgreSQL with pgvector support.

The current application includes:

- PostgreSQL 17 with pgvector 0.8.7.
- Flask web application served by Gunicorn.
- MQTT ingestion worker for scalar and nested JSON payloads.
- Home Assistant WebSocket ingestion worker.
- Raw MQTT message storage.
- Normalized MQTT current values and historical observations.
- MQTT topic overview and topic history pages.
- Field-specific MQTT value history linked to the originating raw message.
- Alembic database migrations.
- Basic parser tests and documentation validation.

## 2. Important files

| Path | Purpose |
|---|---|
| `README.md` | Short project overview and basic commands |
| `IMPLEMENTATION_PLAN.md` | Feature checklist and remaining work |
| `docs/ARCHITECTURE.md` | Data model and architectural decisions |
| `docs/POSTGRESQL_SETUP.md` | PostgreSQL/pgvector setup and data-volume guidance |
| `podman-compose.yml` | PostgreSQL, migration, web, MQTT, and HA services |
| `.env` | Local secrets and connection configuration; never commit it |
| `src/hamqtt_store/db.py` | SQLAlchemy models and database engine |
| `src/hamqtt_store/web.py` | Flask routes and page data loading |
| `src/hamqtt_store/services/ingestion.py` | MQTT message ingestion and observation creation |
| `src/hamqtt_store/services/mqtt_parser.py` | Scalar/JSON payload parsing |
| `templates/mqtt.html` | MQTT topic overview and recent messages |
| `templates/mqtt_topic.html` | Topic fields, observations, and raw message history |
| `templates/mqtt_field.html` | Field-specific value history and source messages |
| `src/hamqtt_store/mcp_server.py` | Read-only MCP tools and resources |
| `migrations/` | Alembic migration history |
| `tests/` | Automated tests |
| `tools/validate_docs.py` | Documentation consistency check |

## 3. Start or resume locally

Run commands from:

```text
C:\Users\janne\Documents\VS_HAMQTT_STORE
```

### Start Podman

```powershell
podman machine start podman-machine-default
```

It is safe if Podman reports that the machine is already running.

### Build the application image

```powershell
podman build -t localhost/hamqtt-store:dev .
```

The image contains the source code, templates, static files, and dependencies.

### Start the database and application services

Normally use:

```powershell
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor mcp
```

The `--in-pod false` option is important for this local setup because the existing containers are managed as standalone containers rather than in one Podman pod.

If existing containers with the same names prevent recreation, remove only the containers and recreate them:

```powershell
podman rm -f hamqtt-migrate hamqtt-web hamqtt-mqtt-ingestor hamqtt-ha-ingestor hamqtt-postgres
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor mcp
```

The PostgreSQL data is stored in the named volume `hamqtt-postgres-data`. Removing the PostgreSQL container does **not** delete that volume. Do not run `podman volume rm hamqtt-postgres-data` unless intentionally resetting all local database data.

## 4. Verify that the stack is healthy

```powershell
podman ps -a
curl.exe -sS http://localhost:8000/health
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
```

Expected application response:

```json
{"database":"ok","status":"ok"}
```

Expected running services:

- `hamqtt-postgres` — healthy
- `hamqtt-web` — running
- `hamqtt-mqtt-ingestor` — running
- `hamqtt-ha-ingestor` — running
- `hamqtt-migrate` — normally exited successfully after applying migrations
- `hamqtt-mcp` — running when configured/enabled

Open the UI at:

```text
http://localhost:8000
```

## 5. Configure data sources

The workers intentionally remain idle until enabled Home Assistant and MQTT connections/subscriptions exist in the application database.

Configure them in the web UI under **Settings**. If the UI appears empty, first check:

```powershell
podman logs hamqtt-mqtt-ingestor
podman logs hamqtt-ha-ingestor
podman logs hamqtt-web
```

MCP is configured under **Settings → AI / MCP service** and is disabled by default. It currently supports only read-only access. The local Streamable HTTP endpoint is `http://localhost:8001/mcp`; restart `hamqtt-mcp` after changing the setting.

## 6. Development checks

For local Python development:

```powershell
python -m pip install -e ".[dev]"
set PYTHONPATH=src
python -m pytest -q
python -m compileall -q src
python tools/validate_docs.py
git diff --check
```

The current parser test suite has three tests. Always run the tests and documentation validator before committing changes.

## 7. Current MQTT UI flow

1. Open **MQTT data**.
2. The upper topic list shows topic ID, topic name, message count, and last seen time.
3. The lower recent-message list shows topic ID, topic name, payload type, payload, and received time.
4. Select **View history** for a topic.
5. The topic page shows current parsed fields, observation history, and raw message history.
6. Select **View values** for a field.
7. The field page shows newest-first values and an expandable raw MQTT message for each observation.

Observations are connected to their raw messages through `mqtt_observations.source_message_id`.

## 8. How to continue implementation

Read these in order:

1. This file, `docs/RESTART_GUIDE.md`.
2. `README.md` for the short operational overview.
3. `IMPLEMENTATION_PLAN.md` for completed and remaining feature checkboxes.
4. `docs/ARCHITECTURE.md` for the intended data model and design decisions.
5. The relevant route/template/service files listed in the important-files table above.

Likely next tasks include:

- Add UI/API integration tests for MQTT topic and field history pages.
- Add parser error/partial-success UI.
- Add parser rules and transformations.
- Add MQTT protocol-specific decoders.
- Add numeric charts and retention jobs.
- Add HA/MQTT linking workflows.
- Add authentication, CSRF protection, and authorization.
- Improve production backup, monitoring, and integration-test documentation.

When adding a feature, update both `IMPLEMENTATION_PLAN.md` and this guide if the startup process, important files, or current behavior changes.

## 9. Commit workflow

Before committing:

```powershell
git status --short
python -m pytest -q
python tools/validate_docs.py
git diff --check
```

Use a short descriptive commit message and confirm the working tree is clean afterward:

```powershell
git add <changed-files>
git commit -m your-message
git status --short
```
