# HA MQTT Store

Containerized Python/Flask application for collecting Home Assistant and MQTT data into PostgreSQL with pgvector support.

## Current implementation

- PostgreSQL 17 with pgvector 0.8.7 under Podman.
- SQLAlchemy models and Alembic migration.
- Flask dashboard and browser views.
- MQTT worker with scalar and nested JSON payload parsing.
- Home Assistant WebSocket state synchronization worker.
- Raw MQTT message storage and normalized observation history.
- MQTT topic overview with topic IDs, topic names, message counts, and recent raw messages.
- MQTT topic history with parsed fields, current values, observation history, and raw message history.
- Field-specific value history with the originating raw MQTT payload linked to each observation.
- Generic object catalog and object metadata editing.

## Start all services

The Podman machine must be running:

```powershell
podman machine start podman-machine-default
python -m podman_compose -f podman-compose.yml build
python -m podman_compose -f podman-compose.yml up -d postgres migrate web mqtt-ingestor ha-ingestor
```

Open the web UI at `http://localhost:8000`.

## MQTT history views

Open **MQTT data** in the web UI to browse topics and recent messages. Each topic can be opened with **View history** to inspect:

- Parsed fields and their current values.
- Observation counts and parsed observation history.
- Raw MQTT message history, including payload type, QoS, retained status, and payload.

Each parsed field has a **View values** action. The field history page shows values newest first and links each value to its originating raw MQTT message, including the message ID and received timestamp.

The workers intentionally remain idle when no enabled Home Assistant or MQTT connection has been configured through the database/UI.

## Useful checks

```powershell
podman ps
podman logs hamqtt-web
podman logs hamqtt-mqtt-ingestor
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
```

## Local development

```powershell
python -m pip install -e ".[dev]"
set PYTHONPATH=src
python -m pytest -q
python -m alembic upgrade head
```
