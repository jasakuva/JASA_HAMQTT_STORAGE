# HA MQTT Store — Architecture and Database Design

**Document status:** Current implementation reference
**Last reviewed:** 2026-10-10
**Database:** PostgreSQL 17 with `pgvector`
**ORM:** SQLAlchemy 2.x
**Migrations:** Alembic

`%INSTALL_PATH%` denotes the local directory where the repository is installed.

> This document describes the database implemented in the repository. Planned tables are explicitly marked as planned.

## 1. Executive summary

HA MQTT Store collects Home Assistant and MQTT data into PostgreSQL. It preserves source data and derives query-friendly records:

1. Connection and ingestion settings are stored relationally.
2. Home Assistant entities and MQTT topics/fields share the `objects` catalog.
3. Raw MQTT messages are retained in `mqtt_messages`.
4. Parsed MQTT values are stored in `mqtt_observations` and accelerated by `mqtt_current_values`.
5. Home Assistant current state and history are stored separately.
6. `object_links` provides generic relationships between catalog objects.
7. The read-only MCP service queries this schema and redacts sensitive payload keys.

> Preserve the raw source message or state, then create normalized records for every meaningful value extracted from it.

## 2. Logical architecture

```text
Home Assistant ──WebSocket──► HA ingestor ─┐
                                           │
MQTT broker ─────MQTT────────► MQTT ingestor ─┼──► PostgreSQL 17 + pgvector
                                           │
Browser ─────────HTTP────────► Flask web ───┘

ChatGPT/Codex ◄── read-only MCP ── MCP service ──► same PostgreSQL database
```

| Container | Responsibility | Port |
|---|---|---:|
| `hamqtt-postgres` | PostgreSQL and pgvector | `5432` |
| `hamqtt-migrate` | Alembic migrations | — |
| `hamqtt-web` | Flask/Gunicorn UI | `8000` |
| `hamqtt-mqtt-ingestor` | MQTT ingestion and parsing | — |
| `hamqtt-ha-ingestor` | Home Assistant synchronization | — |
| `hamqtt-mcp` | Read-only MCP server | host `8001` → container `8000` |

The local MCP endpoint is `http://localhost:8001/mcp`. ChatGPT requires HTTPS, so the temporary bridge is:

```powershell
ngrok http 8001
```

The ChatGPT URL is the current ngrok HTTPS address followed by `/mcp`.

## 3. Database design principles

- **Relational first:** foreign keys, unique constraints, and typed columns protect the core model.
- **JSON for source fidelity:** source attributes, raw states, JSON payloads, and parser metadata retain original shape.
- **Typed value slots:** normalized values use text, numeric, boolean, and JSON columns; the matching slot is normally populated.
- **UTC timestamps:** application timestamps are timezone-aware UTC values.
- **Current plus history:** current tables make UI/MCP reads fast; history tables preserve time-series detail.
- **Raw-to-derived lineage:** every MQTT observation points to its original `mqtt_messages` row through `source_message_id`.
- **Cascade awareness:** source-specific rows use `ON DELETE CASCADE`; deleting a connection can delete its ingested data.
- **Schema authority:** `src/hamqtt_store/db.py` is the model authority; Alembic revisions create/evolve the database.

## 4. Implemented schema at a glance

| Group | Tables | Purpose |
|---|---|---|
| Configuration | `system_settings`, `ha_connections`, `mqtt_connections`, `ingestion_subscriptions` | Runtime settings and source connections |
| Shared catalog | `objects` | Stable cross-source identity and display metadata |
| Home Assistant | `ha_entities`, `ha_state_current`, `ha_state_history` | Entity registry and state data |
| MQTT | `mqtt_topics`, `mqtt_messages`, `mqtt_payload_fields`, `mqtt_observations`, `mqtt_current_values`, `mqtt_parse_events` | Raw MQTT storage and parsed values |
| Relationships/search | `object_links`, `embeddings` | Cross-source links and optional semantic search |

### Relationship map

```text
ha_connections ──< ha_entities ──1── ha_state_current
       │                  └──────<── ha_state_history

mqtt_connections ──< ingestion_subscriptions
       └───────────< mqtt_topics ──< mqtt_messages ──< mqtt_parse_events
                              │
                              └──< mqtt_payload_fields ──1── mqtt_current_values
                                             └────────────<── mqtt_observations ──> mqtt_messages

objects ◄── referenced by HA entities, MQTT topics, MQTT fields, observations,
           current values, object_links, and embeddings
objects ──< object_links >── objects
```

Each HA entity, MQTT topic, and MQTT payload field has a one-to-one `objects` row, providing a common identity model for UI, links, and MCP.

## 5. Detailed database schema

`PK` = primary key, `FK` = foreign key, `UQ` = unique, `IDX` = explicit index.

### 5.1 `system_settings`

Stores structured application settings such as the MCP configuration.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Row identifier |
| `setting_key` | varchar(150) | UQ | Stable setting name, e.g. `mcp` |
| `setting_value` | JSON | `{}` | Structured configuration |
| `is_secret` | boolean | `false` | Secret classification flag |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

### 5.2 `ha_connections`

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Connection identifier |
| `name` | varchar(150) | required | Friendly name |
| `base_url` | varchar(500) | required | Home Assistant URL |
| `access_token` | text | nullable | Access token; protect operationally |
| `enabled` | boolean | `true` | Worker enable flag |
| `verify_tls` | boolean | `true` | TLS verification policy |
| `last_connected_at` | timestamptz | nullable | Last successful connection |
| `last_error` | text | nullable | Latest connection error |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

### 5.3 `mqtt_connections`

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Broker identifier |
| `name` | varchar(150) | required | Friendly name |
| `host` | varchar(255) | required | Broker host |
| `port` | integer | `1883` | Broker port |
| `username` | varchar(255) | nullable | Broker username |
| `password` | text | nullable | Broker password; protect operationally |
| `tls_enabled` | boolean | `false` | TLS flag |
| `client_id` | varchar(255) | nullable | MQTT client ID |
| `enabled` | boolean | `true` | Worker enable flag |
| `last_connected_at`, `last_error` | timestamptz/text | nullable | Runtime status |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

### 5.4 `ingestion_subscriptions`

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Subscription ID |
| `mqtt_connection_id` | integer | FK → `mqtt_connections.id`, cascade | Broker |
| `topic_filter` | varchar(500) | required | Filter such as `sensors/#` |
| `qos` | integer | `0` | Requested QoS |
| `enabled` | boolean | `true` | Active flag |

### 5.5 `objects`

The shared catalog. `(source_type, source_identifier)` is unique.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Catalog ID |
| `object_type` | varchar(50) | required | `ha_entity`, `mqtt_topic`, `mqtt_value`, etc. |
| `source_type` | varchar(50) | required | `ha`, `mqtt`, or another namespace |
| `source_identifier` | varchar(1000) | UQ with source type | Stable source identity |
| `display_name`, `nickname` | varchar(500) | nullable | Display labels |
| `description` | text | nullable | User description |
| `is_active` | boolean | `true` | Active flag |
| `first_seen_at`, `last_seen_at` | timestamptz | nullable | Activity range |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

### 5.6 Home Assistant tables

#### `ha_entities`

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Internal ID |
| `object_id` | integer | FK → `objects.id`, UQ, cascade | Shared object |
| `ha_connection_id` | integer | FK → `ha_connections.id`, cascade | Source connection |
| `entity_id` | varchar(255) | IDX | HA ID, e.g. `sensor.room_temperature` |
| `domain` | varchar(100) | required | HA domain |
| `platform` | varchar(255) | nullable | Integration/platform |
| `device_id`, `area_id` | varchar(255) | nullable | Registry references |
| `unique_id` | varchar(500) | nullable | Integration unique ID |
| `original_name` | varchar(500) | nullable | Registry name |
| `raw_entity` | JSON | `{}` | Original entity payload |

#### `ha_state_current`

One row per entity; `ha_entity_id` is unique.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Current row ID |
| `ha_entity_id` | integer | FK → `ha_entities.id`, UQ, cascade | Entity |
| `state_text`, `state_numeric`, `state_boolean` | text/float/boolean | nullable | Typed state slots |
| `attributes` | JSON | `{}` | Current attributes |
| `last_changed_at`, `last_updated_at` | timestamptz | nullable | HA timestamps |
| `raw_state` | JSON | `{}` | Original state payload |

#### `ha_state_history`

Append-oriented history. `(ha_entity_id, observed_at)` is unique; `ha_entity_id` and `observed_at` are indexed.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | History ID |
| `ha_entity_id` | integer | FK → `ha_entities.id`, IDX, cascade | Entity |
| `observed_at` | timestamptz | IDX; UQ with entity | Observation time |
| `state_text`, `state_numeric`, `state_boolean` | text/float/boolean | nullable | Typed state slots |
| `attributes` | JSON | `{}` | Historical attributes |
| `raw_state` | JSON | `{}` | Original historical state |

### 5.7 MQTT tables

#### `mqtt_topics`

`(mqtt_connection_id, topic)` is unique. Each topic has one shared object.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Topic ID |
| `object_id` | integer | FK → `objects.id`, UQ, cascade | Shared object |
| `mqtt_connection_id` | integer | FK → `mqtt_connections.id`, cascade | Broker |
| `topic` | varchar(1000) | IDX | Full topic |
| `first_seen_at`, `last_seen_at` | timestamptz | defaults | Activity range |
| `message_count` | integer | `0` | Message counter |

#### `mqtt_messages`

Raw ingestion record. It is inserted before parsed derived data.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Message ID |
| `mqtt_connection_id` | integer | FK → `mqtt_connections.id`, cascade | Broker |
| `mqtt_topic_id` | integer | FK → `mqtt_topics.id`, IDX, cascade | Topic |
| `received_at` | timestamptz | IDX/default | Application receive time |
| `qos`, `payload_size` | integer | `0` | QoS and byte length |
| `retain`, `duplicate` | boolean | `false` | MQTT flags |
| `payload_type` | varchar(30) | required | JSON/number/boolean/text/binary/etc. |
| `payload_text` | text | nullable | Text payload |
| `payload_json` | JSON | nullable | Parsed JSON payload |
| `payload_binary` | bytea | nullable | Original binary payload |
| `payload_hash` | varchar(64) | IDX | Content hash |

#### `mqtt_payload_fields`

`(mqtt_topic_id, field_path)` is unique.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Field ID |
| `mqtt_topic_id` | integer | FK → `mqtt_topics.id`, cascade | Parent topic |
| `object_id` | integer | FK → `objects.id`, UQ, cascade | Shared field object |
| `field_path` | varchar(1000) | UQ with topic | `environment.temperature` |
| `field_name` | varchar(500) | required | Leaf name |
| `data_type` | varchar(30) | required | Parsed type |
| `unit` | varchar(50) | nullable | Optional unit |
| `first_seen_at`, `last_seen_at` | timestamptz | defaults | Activity range |
| `observation_count` | integer | `0` | Parsed count |

#### `mqtt_observations`

Time-series facts derived from raw messages. `source_message_id` preserves lineage.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Observation ID |
| `mqtt_topic_id` | integer | FK → `mqtt_topics.id`, IDX, cascade | Topic |
| `mqtt_payload_field_id` | integer | FK → `mqtt_payload_fields.id`, IDX, cascade | Field |
| `object_id` | integer | FK → `objects.id`, cascade | Field object |
| `source_message_id` | integer | FK → `mqtt_messages.id`, cascade | Raw source |
| `observed_at` | timestamptz | IDX | Source observation time |
| `received_at` | timestamptz | required | Application time |
| `value_type` | varchar(30) | required | Parsed type |
| `value_text`, `value_numeric`, `value_boolean`, `value_json` | text/float/boolean/JSON | nullable | Typed value slots |
| `unit` | varchar(50) | nullable | Unit |
| `quality` | varchar(30) | `good` | Quality marker |
| `raw_field_value` | JSON | nullable | Original extracted field |

#### `mqtt_current_values`

One latest value per field; `mqtt_payload_field_id` is unique. It repeats the typed value columns for fast reads.

#### `mqtt_parse_events`

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Event ID |
| `mqtt_message_id` | integer | FK → `mqtt_messages.id`, cascade | Raw message |
| `status` | varchar(40) | required | `success` or `partial_success` currently used |
| `error_message` | text | nullable | Failure detail |
| `details` | JSON | `{}` | Diagnostics, including field count |
| `created_at` | timestamptz | default | Event time |

### 5.8 `object_links`

Generic directed relationships. `(from_object_id, to_object_id, link_type)` is unique.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Link ID |
| `from_object_id`, `to_object_id` | integer | FK → `objects.id`, cascade | Source and target |
| `link_type` | varchar(50) | UQ tuple | Relationship type |
| `direction` | varchar(30) | `one_way` | Direction semantics |
| `confidence` | float | nullable | Match confidence |
| `source` | varchar(30) | `manual` | Creation source |
| `is_active` | boolean | `true` | Active flag |
| `notes` | text | nullable | Explanation |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

### 5.9 `embeddings`

Optional semantic-search row per object; `object_id` is unique and `embedding` is `vector(1536)`.

| Column | Type | Key/default | Meaning |
|---|---|---|---|
| `id` | integer | PK | Embedding ID |
| `object_id` | integer | FK → `objects.id`, UQ, cascade | Embedded object |
| `source_text` | text | required | Embedded text |
| `embedding` | vector(1536) | nullable | pgvector vector |
| `embedding_model` | varchar(150) | nullable | Model identifier |
| `content_hash` | varchar(64) | nullable | Rebuild detection |
| `created_at`, `updated_at` | timestamptz | required | Audit timestamps |

## 6. Ingestion and lineage

For each MQTT message, the worker:

1. Resolves/creates the topic `objects` row.
2. Resolves/creates `mqtt_topics` for `(mqtt_connection_id, topic)`.
3. Parses the payload.
4. Inserts `mqtt_messages` with raw data.
5. Resolves/creates `mqtt_payload_fields`.
6. Inserts `mqtt_observations` with `source_message_id`.
7. Inserts/updates `mqtt_current_values`.
8. Inserts a `mqtt_parse_events` result.
9. Commits the transaction.

```text
mqtt_messages.id = 9001, topic = sensors/living-room
 ├─ mqtt_payload_fields.id = 7, path = temperature
 │   ├─ mqtt_observations.source_message_id = 9001
 │   └─ mqtt_current_values.mqtt_payload_field_id = 7
 └─ mqtt_payload_fields.id = 8, path = humidity
     ├─ mqtt_observations.source_message_id = 9001
     └─ mqtt_current_values.mqtt_payload_field_id = 8
```

The HA worker maintains one `ha_entities` row, one `ha_state_current` row, and many `ha_state_history` rows per entity. The history uniqueness rule makes repeated synchronization idempotent for the same entity/timestamp pair.

## 7. SQL query examples

Examples target PostgreSQL and are read-only unless stated otherwise.

### 7.1 Extension and database health

```sql
SELECT current_database(), version();

SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
```

### 7.2 Table row estimates

```sql
SELECT relname AS table_name, n_live_tup AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC;
```

### 7.3 Current Home Assistant states

```sql
SELECT e.entity_id, e.original_name,
       c.state_text, c.state_numeric, c.state_boolean,
       c.last_changed_at, c.last_updated_at
FROM ha_entities AS e
JOIN ha_state_current AS c ON c.ha_entity_id = e.id
ORDER BY e.entity_id;
```

### 7.4 HA history for one entity

```sql
SELECT h.observed_at, h.state_text, h.state_numeric,
       h.state_boolean, h.attributes
FROM ha_state_history AS h
JOIN ha_entities AS e ON e.id = h.ha_entity_id
WHERE e.entity_id = 'sensor.living_room_temperature'
  AND h.observed_at >= now() - interval '24 hours'
ORDER BY h.observed_at DESC;
```

### 7.5 Latest MQTT values with names

```sql
SELECT t.topic, f.field_path, f.field_name,
       c.value_type, c.value_numeric, c.value_boolean,
       c.value_text, c.value_json, c.last_observed_at
FROM mqtt_current_values AS c
JOIN mqtt_payload_fields AS f ON f.id = c.mqtt_payload_field_id
JOIN mqtt_topics AS t ON t.id = f.mqtt_topic_id
ORDER BY t.topic, f.field_path;
```

### 7.6 Trace a value to its raw message

```sql
SELECT o.observed_at, t.topic, f.field_path, o.value_type,
       o.value_numeric, o.value_boolean, o.value_text,
       o.raw_field_value, m.id AS source_message_id,
       m.received_at, m.payload_type, m.payload_json, m.payload_text
FROM mqtt_observations AS o
JOIN mqtt_payload_fields AS f ON f.id = o.mqtt_payload_field_id
JOIN mqtt_topics AS t ON t.id = o.mqtt_topic_id
JOIN mqtt_messages AS m ON m.id = o.source_message_id
WHERE t.topic = 'sensors/living-room'
  AND f.field_path = 'temperature'
ORDER BY o.observed_at DESC
LIMIT 100;
```

### 7.7 Parser failures and partial success

```sql
SELECT pe.created_at, pe.status, pe.error_message, pe.details,
       m.id AS message_id, t.topic, m.payload_type,
       m.payload_text, m.payload_json
FROM mqtt_parse_events AS pe
JOIN mqtt_messages AS m ON m.id = pe.mqtt_message_id
JOIN mqtt_topics AS t ON t.id = m.mqtt_topic_id
WHERE pe.status <> 'success'
ORDER BY pe.created_at DESC;
```

### 7.8 Cross-source links

```sql
SELECT src.source_type AS from_source,
       src.source_identifier AS from_identifier,
       l.link_type, l.confidence, l.source AS link_source,
       dst.source_type AS to_source,
       dst.source_identifier AS to_identifier, l.notes
FROM object_links AS l
JOIN objects AS src ON src.id = l.from_object_id
JOIN objects AS dst ON dst.id = l.to_object_id
WHERE l.is_active = true
ORDER BY l.confidence DESC NULLS LAST, src.source_identifier;
```

### 7.9 High-volume topics

```sql
SELECT topic, message_count, first_seen_at, last_seen_at
FROM mqtt_topics
ORDER BY message_count DESC
LIMIT 25;
```

### 7.10 Retention review candidates

Review only; this does not delete data.

```sql
SELECT id, mqtt_topic_id, received_at, payload_size, payload_hash
FROM mqtt_messages
WHERE received_at < now() - interval '90 days'
ORDER BY received_at
LIMIT 1000;
```

### 7.11 pgvector similarity search

```sql
SELECT o.id, o.source_type, o.source_identifier, o.display_name,
       1 - (e.embedding <=> '[0.01,0.02,0.03]'::vector) AS similarity
FROM embeddings AS e
JOIN objects AS o ON o.id = e.object_id
WHERE e.embedding IS NOT NULL
ORDER BY e.embedding <=> '[0.01,0.02,0.03]'::vector
LIMIT 10;
```

## 8. MCP read-only access

`src/hamqtt_store/mcp_server.py` uses the same SQLAlchemy session/database as the web app.

| MCP operation | Primary tables |
|---|---|
| `get_system_summary` | `objects`, `ha_entities`, `mqtt_topics`, `mqtt_messages` |
| `search_objects` | `objects` |
| `list_home_assistant_entities` | `ha_entities`, `ha_state_current`, `objects` |
| `get_home_assistant_entity` | `ha_entities`, `ha_state_current` |
| `get_home_assistant_history` | `ha_entities`, `ha_state_history` |
| `list_mqtt_topics` | `mqtt_topics`, `mqtt_connections` |
| `list_mqtt_fields` | `mqtt_topics`, `mqtt_payload_fields` |
| `get_mqtt_current_value` | `mqtt_current_values` |
| `list_recent_mqtt_messages` | `mqtt_messages` |
| `get_object` | `objects` |

The server requires the `mcp` setting to be enabled with `access_level = 'read_only'`. It clamps list limits and redacts keys such as passwords, tokens, secrets, and API keys from JSON/text responses. It never publishes MQTT, calls HA services, or writes to the database.

```text
ChatGPT/Codex → HTTPS or stdio → MCP server → SQLAlchemy → PostgreSQL
```

For ChatGPT Personal, the temporary HTTPS boundary is `ngrok http 8001`; configure `https://<current-ngrok-host>/mcp` and stop ngrok after use.

## 9. Performance and indexing

Explicit indexes cover `ha_entities.entity_id`, HA history entity/time, MQTT topic, raw message topic/time/hash, and MQTT observation topic/field/time. Unique constraints create additional identity/current-value indexes.

If volume grows, review query plans and consider `(mqtt_topic_id, received_at DESC)`, `(mqtt_payload_field_id, observed_at DESC)`, time partitioning for raw/history tables, and an appropriate pgvector index.

## 10. Security and data lifecycle

- Treat HA tokens, MQTT passwords, and raw payloads as sensitive.
- Do not expose unauthenticated MCP beyond the required ngrok session.
- Keep backups encrypted and test restores.
- Retain catalog/current values while applying explicit policies to high-volume raw/history data.
- Deleting raw messages currently cascades to observations and parse events.
- Add authentication, CSRF protection, authorization, and stronger secret-at-rest protection before production exposure.

## 11. Implemented versus planned

### Implemented now

PostgreSQL/pgvector, Alembic, HA connection/entity/current/history tables, MQTT connection/subscription/topic/raw message/field/observation/current/parse-event tables, shared objects, object links, embeddings, MQTT lineage, and read-only MCP.

### Planned or not currently represented

Earlier planning text mentioned aliases, tags, metadata history, HA devices/areas/services/events/actions, MQTT parser rules, link evidence, and retention tables. These are **not** currently defined in `src/hamqtt_store/db.py`; add them only through explicit models and Alembic migrations.

## 12. Schema change checklist

```powershell
cd "<path-to-installation>"
python -m pytest -q
python -m compileall -q src
python tools/validate_docs.py
python tools/generate_architecture_docx.py
git diff --check
```

Before a schema change: update `db.py`, add an Alembic migration, update this document and tests, regenerate the `.docx`, and run the complete checks.