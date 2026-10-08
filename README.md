# HA MQTT Store

Containerized Python/Flask application for collecting Home Assistant and MQTT data into PostgreSQL with pgvector support.

## Current implementation

- PostgreSQL 17 with pgvector 0.8.7 under Podman.
- SQLAlchemy models and Alembic migration.
- Flask dashboard and browser views.
- MQTT worker with scalar and nested JSON payload parsing.
- Home Assistant WebSocket state synchronization worker.
- Raw MQTT message storage and normalized observation history.
- Generic object catalog and object metadata editing.

## Start all services

The Podman machine must be running:

```powershell
podman machine start podman-machine-default
python -m podman_compose -f podman-compose.yml build
python -m podman_compose -f podman-compose.yml up -d postgres migrate web mqtt-ingestor ha-ingestor
```

Open the web UI at `http://localhost:8000`.

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
