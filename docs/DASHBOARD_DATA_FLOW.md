# Dashboard data flow and current analysis features

This document describes how data reaches the main dashboard and how the dashboard differs from the historical graph and CSV export views.

## Overview

The application has two complementary data paths:

1. **Durable history path** — MQTT and Home Assistant workers write normalized and raw data to PostgreSQL. The graph and CSV export pages query this history.
2. **Live dashboard path** — after a successful database write, each worker writes a compact, best-effort representation to Redis. The browser reads these short-lived dashboard caches through Flask JSON endpoints.

```text
MQTT broker ──► MQTT worker ──► PostgreSQL history
                    │
                    └──────────► Redis dashboard:mqtt:latest ──► Flask API ──► browser

Home Assistant ─► HA WebSocket worker ─► PostgreSQL current/history
                         │
                         └──────────────► Redis dashboard:ha:states ──► Flask API ──► browser

PostgreSQL history ──► /graph ──► Plotly interactive graph
PostgreSQL history ──► /export?download=1 ──► CSV download
```

The Redis path is an optimization for the dashboard, not the system of record. If Redis is unavailable, ingestion continues and the durable PostgreSQL path remains independent.

## MQTT live feed

When the MQTT worker receives a message, `on_message` performs these operations:

1. `ingest_mqtt_message(...)` stores the raw message and parsed observations in PostgreSQL.
2. `make_dashboard_message(...)` creates a compact display object containing `received_at`, `topic`, a display-safe `message`, `qos`, and `retain`.
3. `cache_dashboard_message(...)` pushes the JSON object to the Redis list `dashboard:mqtt:latest`.
4. Redis trims the list to the newest six messages.

JSON payloads are compacted, binary payloads are represented by a size marker, and displayed payload text is limited to 500 characters. A Redis write failure is logged but does not interrupt MQTT ingestion.

The Flask endpoint `GET /api/dashboard/latest-mqtt` reads the newest six Redis entries and returns:

```json
{
  "messages": [
    {
      "received_at": "2026-10-12T19:30:00+00:00",
      "topic": "sensors/living-room",
      "message": "{\"temperature\":21.4}",
      "qos": 0,
      "retain": false
    }
  ]
}
```

The dashboard JavaScript calls this endpoint immediately when the page loads and every two seconds afterward. It replaces the MQTT feed rows in the DOM without reloading the page. Polling is skipped while the browser tab is hidden. A failed request changes the MQTT badge from `Live` to `Offline`; a later successful request restores `Live`.

## Home Assistant live snapshot

The HA worker first synchronizes the current states and then subscribes to Home Assistant `state_changed` events.

For the initial state result and every subsequent state event:

1. `upsert_state(...)` updates `ha_entities`, `ha_state_current`, and, when new, `ha_state_history` in PostgreSQL.
2. `make_dashboard_entity(...)` creates a compact object with the entity ID, friendly name, typed value, value type, and `last_updated_at`.
3. `cache_dashboard_entity(...)` stores that object in the Redis hash `dashboard:ha:states`, keyed by entity ID.

The hash represents the latest known value for each cached entity. The Flask endpoint `GET /api/dashboard/random-ha` samples up to five entity IDs from that hash and returns their current compact values. The random sample means the dashboard can show a representative snapshot without transferring every Home Assistant entity on every request.

The browser calls this endpoint immediately and every ten seconds. It renders each entity as name, value, and relative update time. As with MQTT, hidden tabs do not poll and request failures mark the tile `Offline` without affecting stored data.

## Dashboard page lifecycle

The `GET /` dashboard route is server-rendered by Flask:

- Metric cards are counted from PostgreSQL (`objects`, HA entities, MQTT topics/messages, and links).
- The initial MQTT feed is populated from the Redis cache so the page is useful before the first browser poll.
- The Home Assistant snapshot and MQTT feed are then refreshed by `static/app.js`.

The browser uses `cache: no-store` for both JSON requests. This prevents an intermediary or browser cache from making the dashboard appear stale. The dashboard is authenticated like the other application routes; `/health` remains unauthenticated for container checks.

## Graphs

The **Graphs** page is historical analysis, not a Redis live view.

- The catalog combines Home Assistant entities and MQTT payload fields from the shared `objects` catalog.
- The user selects a UTC-compatible time range and one to four series.
- HA values come from `ha_state_history`.
- MQTT values come from `mqtt_observations`.
- Values are sorted by timestamp and numeric rows are downsampled when the result exceeds 4,000 numeric points.
- The rendered page creates Plotly line-and-marker traces with zoom, pan, scroll zoom, a range slider, and 1-hour, 6-hour, and 1-day range buttons.
- Non-numeric observations remain available to history views and export but are not plotted as numeric graph points.

The optional `standalone=1` query parameter opens the graph without the normal application shell; `/plot/<object_id>` redirects to this standalone graph form for one object.

## CSV export

The **Export CSV** page uses the same historical catalog and range semantics as graphs, but permits one to ten selected series. The download request is:

```text
/export?from=<ISO timestamp>&to=<ISO timestamp>&object_id=<id>&download=1
```

The generated `hamqtt-export.csv` contains:

```text
timestamp,series,source,identifier,value,value_type,unit,state
```

Exports read PostgreSQL history directly. They are not limited to the six MQTT messages or five sampled HA entities shown by the dashboard.

## Troubleshooting live data

If the dashboard is empty or a live badge is offline:

1. Check the service and database health:

   ```powershell
   podman-compose ps -a
   curl.exe -sS http://localhost:8000/health
   ```

2. Inspect the ingestion logs:

   ```powershell
   podman-compose logs --tail 100 mqtt-ingestor
   podman-compose logs --tail 100 ha-ingestor
   podman-compose logs --tail 100 web
   ```

3. Confirm that enabled connections and MQTT subscriptions are configured in **Settings**. Workers intentionally remain idle when no enabled source configuration exists.
4. Check Redis availability. Redis failures should appear in worker logs as dashboard-cache warnings; they should not prevent PostgreSQL ingestion.
5. Hard-refresh the browser after a frontend image update with `Ctrl+F5`.

The dashboard cache is bounded and disposable. Historical data is recovered from PostgreSQL after Redis or web-container recreation; the dashboard will repopulate as workers receive new states and messages.