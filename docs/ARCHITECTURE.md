# HA MQTT Store - Architecture and Data Design

**Document status:** Planning
**Date:** 2026-10-08

## 1. Executive summary

HA MQTT Store is a self-hosted, containerized application for collecting and exploring Home Assistant and MQTT data. It connects to Home Assistant and MQTT brokers, stores raw source data, parses MQTT payloads into normalized sensor observations, tracks historical values, and lets users relate MQTT objects to Home Assistant entities.

The recommended database is PostgreSQL with the pgvector extension. PostgreSQL provides relational integrity, JSONB for source-specific attributes, time-oriented indexes, full-text search, and vector similarity search in one system.

The central design rule is:

> Preserve every source message/event, then create normalized records for every meaningful value extracted from it.

This is necessary because an MQTT topic may contain a single scalar value or a JSON document containing temperature, humidity, battery, motion, and other values at the same time.

## 2. Goals and non-goals

### Goals

- Collect Home Assistant entities, states, attributes, events, and actions.
- Collect MQTT messages from configurable subscriptions.
- Parse MQTT scalar and JSON payloads, including nested fields.
- Store current and historical data.
- Support names, nicknames, descriptions, tags, and custom attributes.
- Link MQTT topics/fields/devices to Home Assistant entities/devices.
- Offer relational filters, raw payload inspection, historical charts, and semantic search.
- Run with Docker Compose on Linux and remain usable for local deployments.

### Non-goals for the initial release

- Replacing Home Assistant as an automation engine.
- Supporting every proprietary MQTT payload format without configuration.
- Embedding every historical message by default.
- Providing high-availability clustering.

## 3. Logical architecture

```text
Browser
   |
   v
Flask web/API service ---- PostgreSQL + pgvector
   ^                              ^
   |                              |
HA ingestion worker -------------+
MQTT ingestion worker ------------+
```

The web service and ingestion workers share domain services and database models but run as separate processes/containers. This prevents a slow or disconnected broker from blocking the UI.

### Main components

#### Web/API service

- Flask application factory.
- Server-rendered Jinja views and JSON endpoints.
- Settings, object management, history, links, and search.
- Authentication and authorization boundary.

#### Home Assistant worker

- Authenticates through the Home Assistant WebSocket API.
- Performs initial synchronization.
- Listens for state/event changes.
- Upserts entities, devices, areas, services, current states, history, events, and actions.
- Reconnects with bounded exponential backoff.

#### MQTT worker

- Connects to configured brokers.
- Applies subscription rules.
- Stores each raw message before parsing.
- Parses scalar and JSON payloads.
- Updates discovered fields, latest values, and historical observations.
- Records parser errors and supports configurable parser rules.

#### Maintenance worker

- Applies retention policies.
- Creates historical aggregates.
- Regenerates embeddings.
- Performs health and consistency checks.

## 4. Container architecture

The initial Compose deployment should contain:

```text
postgres       PostgreSQL with pgvector
web            Flask/Gunicorn application
ha-ingestor    Home Assistant synchronization/event worker
mqtt-ingestor  MQTT subscription/parser worker
```

The first version should avoid adding Redis or a separate message queue unless measured throughput requires it. PostgreSQL is the durable source of truth. A reverse proxy can be added for TLS and external access.

All containers should use environment variables or mounted secrets for deployment-specific settings. Source connection settings are managed through the UI and persisted in the database, with secret fields encrypted at rest.

## 5. Backend software modules

```text
hamqtt_store/
  web/            Flask routes, templates, static assets
  api/            JSON schemas and API error handling
  db/             SQLAlchemy models, sessions, repositories, migrations
  domain/         Object, history, link, MQTT, and HA business rules
  integrations/   Home Assistant and MQTT clients/adapters
  services/       Settings, search, retention, embedding, object services
  workers/        Long-running ingestion and maintenance entry points
  security/       Secret encryption, authentication, authorization
```

The ingestion adapters should not directly contain UI logic. They emit or persist domain-level events through services so the same behavior can be tested without a live broker.

## 6. Home Assistant integration

### Startup synchronization

1. Load an enabled HA connection.
2. Authenticate to the WebSocket API.
3. Fetch current states and registries supported by the target HA version.
4. Upsert generic objects and source-specific entity/device/area/service rows.
5. Populate current state rows.
6. Subscribe to state and relevant event streams.

### Live state processing

For each state-change event:

1. Store the raw event.
2. Resolve the entity.
3. Update the current-state row.
4. Insert a history row.
5. Update object activity timestamps.
6. Optionally update search/indexing metadata.

### Actions and events

Relevant events and service calls are stored separately from state history. The first release should capture available service-call/action-related events without promising to reconstruct every internal automation trace.

## 7. MQTT integration and parsing

### Raw message handling

The MQTT worker must write the raw message before attempting parsing. The raw record should include topic, received time, QoS, retain flag, duplicate flag, payload type, payload bytes/text/JSON, size, and a content hash.

If parsing fails, the original message remains available for diagnosis or later reprocessing.

### Payload classification

The parser should attempt:

1. Valid JSON.
2. Configured boolean forms such as `true`, `false`, `on`, and `off`.
3. Numeric conversion.
4. Plain text.
5. Binary or unknown storage.

Conversion of words such as `ON`, `OFF`, `OPEN`, and `CLOSED` must be configurable because they may be semantic states rather than booleans.

### JSON extraction

For JSON objects, recursively walk scalar leaf fields. Each field receives a stable path, for example:

```text
temperature
environment.temperature
battery.level
```

Arrays and complex subtrees remain available in the raw JSON. Array-path support can be added where a device format requires it.

For this message:

```json
{
  "temperature": 21.7,
  "humidity": 46.2,
  "battery": 87,
  "motion": false
}
```

the system creates four observations and four field-level objects, all linked to the same raw message.

### Parser rules and transformations

Automatic parsing is supplemented by rules matching a topic filter and optional field path. Rules may define:

- Friendly name.
- Unit.
- Type override.
- Timestamp path.
- Device identifier path.
- Boolean mapping.
- Multiply/divide/offset/round transformations.
- Range validation.
- Field renaming.

The original field value remains stored even after transformation. Parsing may produce a partial-success result: valid fields are stored and invalid fields generate a parse event.

### Time semantics

Each observation stores:

- `observed_at`: source timestamp if valid and configured; otherwise receive time.
- `received_at`: application receive time.

This distinguishes delayed data from data observed at ingestion time.

## 8. Database architecture

The schema is relational first, with JSONB used for source payloads and extensible attributes. All tables should use UTC timestamps and explicit foreign keys.

### 8.1 Settings and connections

#### `system_settings`

Stores key/value JSON settings, secret classification, and timestamps.

#### `ha_connections`

Stores name, URL, encrypted access token, TLS policy, enabled state, last connection time, and last error.

#### `mqtt_connections`

Stores broker host/port, encrypted credentials, TLS settings, client ID, enabled state, and connection status.

#### `ingestion_subscriptions`

Stores MQTT topic filters, QoS, enabled state, and retained-message policy.

### 8.2 Generic object catalog

#### `objects`

Common catalog record for HA entities, HA devices, HA areas, MQTT topics, MQTT fields, MQTT devices, and custom objects.

Key fields:

```text
id, object_type, source_type, source_identifier,
display_name, nickname, description, is_active,
first_seen_at, last_seen_at, created_at, updated_at
```

The `(source_type, source_identifier)` pair should normally be unique.

#### `object_aliases`, `object_tags`, `object_metadata`, `object_metadata_history`

Support search aliases, many tags, user-defined attributes, and audit history for metadata changes.

### 8.3 Home Assistant tables

#### `ha_entities`

Stores `entity_id`, domain, platform, unique ID, device/area references, original name, registry flags, and raw registry JSON.

#### `ha_devices`, `ha_areas`, `ha_services`

Store source-specific registry and service information while linking to generic objects.

#### `ha_state_current`

One current row per entity with text, numeric, boolean, attributes JSONB, timestamps, context, and raw state JSON.

#### `ha_state_history`

Append-oriented history of observations with entity, timestamps, normalized values, attributes, context, event ID, and raw state JSON. Index by entity/time and time. Partition by time if volume requires it.

#### `ha_events` and `ha_actions`

Store relevant raw events and service/action calls. Actions include domain, service, target, service data, context, user, origin, and raw event JSON.

### 8.4 MQTT tables

#### `mqtt_topics`

Stores topic identity, parent topic, broker connection, first/last seen timestamps, message counts, and retained-message information.

#### `mqtt_messages`

Stores every received message with topic, timestamps, QoS, retain/duplicate flags, payload type, text/JSON/binary representations, size, hash, and raw metadata.

#### `mqtt_payload_fields`

Tracks discovered paths within topic payloads:

```text
topic, field_path, field_name, data_type,
sample_value_json, first_seen_at, last_seen_at,
observation_count, is_active
```

#### `mqtt_observations`

Normalized time-series values linked to topic, field, object, source message, and timestamps. Store one typed value representation where possible: numeric, boolean, text, JSON, or unknown.

#### `mqtt_current_values`

One latest parsed value per field/object for fast UI access.

#### `mqtt_parser_rules`

Topic/field matching rules for names, units, types, timestamps, transformations, and validation.

#### `mqtt_parse_events`

Records success, partial success, invalid JSON, transformation errors, and other parser outcomes.

### 8.5 Mapping tables

#### `object_links`

Many-to-many links between any catalog objects. Fields include source/target object, link type, direction, confidence, source, active flag, notes, creator, and timestamps.

Examples:

```text
MQTT field -> reports_state_to -> HA entity
MQTT device <-> same_device <-> HA device
MQTT topic -> represents -> MQTT device
```

#### `link_evidence`

Stores why an automatic link was suggested: matching identifiers, discovery metadata, naming similarity, device data, or manual confirmation.

### 8.6 Embeddings

#### `embeddings`

Stores object ID, source text, embedding vector, model, dimensions, content hash, and timestamps. Initially embed catalog objects, aliases, descriptions, and selected summaries rather than every raw message.

## 9. Data mapping examples

### Scalar topic

```text
Topic: house/living-room/temperature
Payload: 21.7
```

Creates:

```text
MQTT topic object: house/living-room/temperature
MQTT field object: house/living-room/temperature.value
Observation: numeric 21.7
```

### Multi-value JSON topic

```text
Topic: sensors/living-room
Payload: {"temperature":21.7,"humidity":46.2,"motion":false}
```

Creates three field objects and three observations, each linked to the same raw message. Each field can independently link to a different HA entity.

### Mapping confidence

Exact identifiers and discovery metadata receive higher confidence than name similarity or vector similarity. Automatic matches should be suggestions until explicitly approved unless a future policy says otherwise.

## 10. Search and vector design

Use exact relational queries for IDs, domains, topic filters, dates, values, and metadata. Use PostgreSQL full-text search for names and descriptions. Use pgvector for semantic searches over object summaries and descriptions.

Embedding records must include the model and content hash so changed descriptions or model versions can be re-indexed safely. Hybrid search combines text relevance, structured filters, and vector similarity.

## 11. UI design

### Dashboard

Show HA/MQTT connection health, ingestion rates, last errors, object counts, unresolved mapping suggestions, and database status.

### Home Assistant views

Entities, devices, areas, services, current states, history charts, attributes, actions, and linked MQTT objects.

### MQTT views

Topic tree, raw messages, retained values, parsed fields, latest values, observations, parser rules, parse errors, and linked HA entities.

### Object detail

Display name, nickname, description, tags, custom attributes, source data, current values, history, links, and activity.

### Settings

Connection configuration, subscriptions, retention, embedding/search settings, users, and export/import.

## 12. History and retention

Current values, object metadata, and mappings are long-lived. Raw messages, HA events, and high-frequency state history require configurable retention. When volume grows, use time partitions and aggregate tables for hourly/daily numeric history.

Retention must be explicit per data category and should run as a maintenance job. Deletion must not remove catalog objects or mapping records unless the user explicitly requests it.

## 13. Security

- Encrypt tokens and passwords at rest.
- Keep encryption keys outside PostgreSQL.
- Redact credentials from logs.
- Never return stored secrets in normal API responses.
- Use CSRF protection, secure cookies, input validation, and authorization.
- Require TLS verification by default where practical.
- Support MQTT topic exclusions and future payload masking for sensitive data.

## 14. Testing strategy

### Unit tests

- Scalar payload classification.
- JSON flattening and field-path stability.
- Boolean/numeric conversion.
- Parser transformations and validation.
- Link confidence/evidence rules.
- Secret encryption/decryption.

### Integration tests

- Database migrations and foreign keys.
- HA synchronization using recorded fixtures.
- MQTT ingestion using test broker or fixtures.
- Raw message plus observation transaction behavior.
- Reconnect and duplicate-message handling.
- Retention jobs.

### UI/API tests

- Settings validation and secret handling.
- Object edits and metadata history.
- Manual link creation and removal.
- History and search endpoints.

## 15. Deployment and operations

Use Docker Compose with persistent PostgreSQL storage, health checks, restart policies, environment-based deployment configuration, and backup instructions. The database is the durable source of truth; workers should be safe to restart and should report connection/processing status in the database for the UI.

Operational documentation must cover migrations, backups, restores, logs, credentials, retention, and troubleshooting disconnected integrations.

## 16. Implementation order

1. Foundation, Compose, PostgreSQL/pgvector, Flask, migrations.
2. Settings and encrypted connection management.
3. Generic object catalog and HA/MQTT source tables.
4. HA synchronization and history.
5. MQTT raw ingestion.
6. MQTT scalar/JSON parser and normalized observations.
7. UI object browsing and history.
8. Typed mapping and suggestions.
9. Search and vector indexing.
10. Retention, authentication, tests, and production hardening.

## 17. Open decisions

- Home Assistant version range.
- Read-only versus command-capable first release.
- Expected data rate and retention.
- Required MQTT vendor decoders.
- External versus local embedding model.
- Login and multi-user requirements.
- Automatic-link approval policy.
- Binary-payload retention policy.
