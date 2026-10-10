# HA MQTT Store - Implementation Plan

**Status:** Active implementation roadmap
**Last updated:** 2026-10-09
**Repository:** `%INSTALL_PATH%`

`%INSTALL_PATH%` means the local directory where this repository is installed.

Status legend:

- `[x]` Implemented and verified in the current repository.
- `[~]` Partially implemented or implemented only for the current development baseline.
- `[ ]` Planned or not yet implemented.

For restart/setup instructions, see [`docs/RESTART_GUIDE.md`](docs/RESTART_GUIDE.md). This file tracks implementation status; the restart guide tracks how to resume work.

## 1. Purpose

Build a containerized Linux-preferred Python application that connects to Home Assistant and one or more MQTT brokers, stores raw and normalized data in PostgreSQL, supports vector search through pgvector, and provides a web UI for browsing, annotating, linking, and analyzing objects, entities, states, actions, MQTT topics, messages, and parsed sensor values.

The application must preserve source data while also extracting useful structured values. In particular, one MQTT message may contain one scalar value or many values inside a JSON payload. Each extracted value must be independently searchable, historized, chartable, and linkable to a Home Assistant entity.

## 2. Current scope

### Implemented baseline

- `[~]` Home Assistant connection and state/event ingestion; the worker and core HA history views exist, but broader synchronization and production hardening remain.
- `[~]` MQTT broker connection, subscriptions, raw message storage, and reconnect behavior; the development worker is operational, while resilience tests remain.
- `[x]` MQTT parsing for scalar and nested JSON payloads.
- `[x]` Normalized MQTT current values and historical observations linked to source messages.
- `[~]` Home Assistant entities, states, and history views; broader device/area/service workflows remain.
- `[~]` Generic object catalog and metadata editing; the catalog exists, but the full metadata/linking workflow is incomplete.
- `[~]` PostgreSQL relational schema with JSON/BLOB-compatible raw data and pgvector support; vector search is not implemented yet.
- `[x]` Flask web UI, health endpoint, and initial JSON API.
- `[x]` Podman Compose deployment for local development/Linux-style containers.
- `[~]` Health, logging, migration, and test foundations; integration coverage and production operations remain.

### Not in the first implementation unless explicitly approved

- Full automation trace reconstruction inside Home Assistant.
- Arbitrary MQTT command publishing from the UI.
- Multi-tenant cloud hosting.
- Guaranteed support for every vendor-specific MQTT protocol.
- Embedding every raw message.
- High-availability database clustering.

## 3. Baseline technical decisions

| Area | Decision | Rationale |
|---|---|---|
| Database | PostgreSQL + pgvector | Relational integrity, JSONB, mature indexing, vector search |
| Backend | Python + Flask | Matches preference and is sufficient for UI/API services |
| ORM | SQLAlchemy | Explicit relational models and repository support |
| Migrations | Alembic | Versioned schema changes |
| HA integration | Home Assistant WebSocket/API | Initial synchronization plus live event stream |
| MQTT | Eclipse Paho MQTT | Mature Python MQTT client |
| UI | Flask/Jinja2, progressively enhanced with HTMX or small JavaScript modules | Simple server-rendered baseline with interactive views |
| Deployment | Docker Compose | Clear separation of web, ingestion, and database services |
| Search | PostgreSQL full-text/JSONB search plus pgvector | Exact filters and semantic search together |
| Raw data | Immutable source payloads in JSONB/BLOB-compatible columns | Reprocessing and auditability |
| Secrets | Encrypted at rest, encryption key outside database | Avoid plaintext credentials in database and logs |

## 4. Current repository structure

```text
IMPLEMENTATION_PLAN.md
README.md
podman-compose.yml
Dockerfile
pyproject.toml
docs/
  ARCHITECTURE.md
  HAMQTT_STORE_ARCHITECTURE.docx
  POSTGRESQL_SETUP.md
  RESTART_GUIDE.md
src/
  hamqtt_store/
    services/
    integrations/
tests/
  test_mqtt_parser.py
migrations/
templates/
static/
```

## 5. Implementation phases and task checklist

### Phase 0 - Confirm requirements and decisions

- [ ] Confirm PostgreSQL rather than MySQL.
- [ ] Confirm the minimum Home Assistant version to support.
- [ ] Confirm one or multiple Home Assistant connections.
- [ ] Confirm one or multiple MQTT brokers.
- [ ] Confirm whether the first release is read-only or can publish commands.
- [ ] Confirm expected entity count and MQTT message rate.
- [ ] Confirm raw MQTT, HA state, event, and action retention periods.
- [ ] Decide whether login is required from the first release.
- [ ] Select local or cloud embedding provider/model.
- [ ] Decide whether MQTT subscription defaults to explicit filters or permits `#`.

### Phase 1 - Project foundation

- [x] Create Python package and dependency configuration.
- [x] Add Flask application factory.
- [x] Add SQLAlchemy session and configuration layer.
- [x] Add Alembic migrations.
- [x] Add Podman Compose with PostgreSQL/pgvector and application services.
- [x] Add health endpoint.
- [ ] Add structured logging and correlation IDs.
- [x] Add initial test configuration.
- [~] Add initial database migration; automated migration tests remain.

### Phase 2 - Database and object catalog

- [x] Implement connection/settings tables.
- [~] Implement generic `objects` table and metadata fields; complete UI editing is still pending.
- [~] Implement HA entity/device/area/service tables; entity/state coverage is ahead of device/area/service UI coverage.
- [x] Implement MQTT connection/topic/message tables.
- [x] Implement typed object link tables.
- [x] Add foreign keys, uniqueness rules, and indexes.
- [~] Add JSON validation boundaries in the service layer; broader validation remains.

### Phase 3 - Settings and connection UI

- [x] Add Home Assistant connection settings.
- [x] Add MQTT broker settings.
- [x] Add MQTT subscription rules.
- [ ] Add encrypted secret storage.
- [ ] Add test-connection actions.
- [~] Add connection status and last-error display.

### Phase 4 - Home Assistant ingestion

- [x] Implement WebSocket authentication.
- [~] Implement initial state/entity/device/area/service synchronization; entity/state synchronization is implemented, with broader coverage pending.
- [x] Implement state-change event subscription.
- [x] Store current states and state history.
- [~] Store relevant events and service/action records.
- [x] Implement reconnect and backoff.
- [x] Add idempotent upsert behavior.
- [ ] Add ingestion metrics and status.

### Phase 5 - MQTT ingestion and parsing

- [x] Implement broker connection and reconnect behavior for the development worker.
- [x] Implement configured topic subscriptions.
- [x] Store every raw MQTT message before parsing.
- [x] Detect JSON, number, boolean, text, binary, and unknown payloads.
- [x] Extract scalar JSON leaf fields using stable field paths.
- [x] Create/update MQTT field objects.
- [x] Store normalized current values.
- [x] Store historical observations linked to source messages.
- [x] Preserve payload timestamps separately from receive timestamps.
- [ ] Add parser error and partial-success tracking.
- [ ] Add configurable parser rules and transformations.
- [ ] Add protocol decoder interface for Zigbee2MQTT, Tasmota, discovery, and custom formats.

### Phase 6 - Web UI and object management

- [x] Add dashboard.
- [~] Add HA entities/devices/areas/services views; entity/current/history views exist, broader views remain.
- [x] Add MQTT topic tree and message views.
- [x] Add parsed MQTT field/value views.
- [ ] Add object detail pages.
- [ ] Add nicknames, descriptions, tags, and custom attributes.
- [ ] Add history timelines and numeric charts.
- [x] Add raw payload viewer with safe display handling.

### Phase 7 - Mapping and search

- [ ] Add manual topic/field/entity/device links.
- [ ] Add link type, direction, confidence, notes, and evidence.
- [ ] Add automatic link suggestions based on identifiers and names.
- [ ] Add full-text and structured filtering.
- [ ] Add embedding generation for catalog objects and descriptions.
- [ ] Add vector similarity search through pgvector.
- [ ] Add hybrid text/vector search.
- [ ] Add re-indexing and embedding version management.

### Phase 8 - Retention and production hardening

- [ ] Add configurable retention jobs.
- [ ] Add time-based partitioning if volume requires it.
- [ ] Add aggregate history tables for long-term charts.
- [ ] Add database backup and restore documentation.
- [ ] Add authentication, CSRF protection, secure cookies, and authorization.
- [ ] Add integration tests using disposable services.
- [ ] Add reconnect, malformed payload, duplicate message, and migration tests.
- [ ] Add production Compose profile and reverse-proxy guidance.
- [ ] Add monitoring/metrics and operational runbook.

## 6. Core data model decisions

### Raw plus normalized storage

Every source message/event is stored in raw form. Parsed values are separate rows linked to the raw source. Normalized columns are used for common filters and charts; JSONB preserves fields that are not yet modeled.

### MQTT value granularity

An MQTT topic is not necessarily one sensor. A JSON message can create several logical MQTT value objects:

```text
sensors/living-room.temperature
sensors/living-room.humidity
sensors/living-room.battery
```

Each value object can have its own history and its own link to a Home Assistant entity.

### Time semantics

Store both:

- `observed_at`: timestamp from the payload when valid/configured, otherwise receive time.
- `received_at`: timestamp when this application received the message.

This preserves delayed-message behavior and supports accurate history analysis.

## 7. Open questions

1. What Home Assistant versions must be supported?
2. Is the system read-only initially, or should it publish MQTT and call HA services?
3. How many messages per second and total retained messages are expected?
4. What retention is required for raw MQTT messages?
5. Should binary MQTT payloads be stored indefinitely or only metadata/hash?
6. Which MQTT protocol decoders are required in version one?
7. Should automatic mappings require manual approval?
8. Can one entity be linked to multiple MQTT fields, and should one link be marked primary?
9. Is external network access for embeddings allowed?
10. Is local user authentication required from the beginning?
11. Should deleted source objects remain as historical/inactive objects?
12. Are multiple users and roles required?

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| MQTT volume grows quickly | Retention policies, partitions, aggregates, topic filters |
| Vendor payload formats vary | Raw preservation, configurable parser rules, decoder plugins |
| HA API details differ by version | Version-aware adapter and integration tests |
| Incorrect automatic mappings | Suggestions with evidence and manual confirmation |
| Credentials leak through logs/UI | Secret redaction, encryption, no secret response fields |
| Vector model changes | Store model name, dimensions, content hash, and re-index status |
| Event duplication after reconnect | Idempotency keys where available and explicit duplicate policy |
| Schema becomes too rigid | JSONB raw fields plus normalized fields only for stable concepts |

## 9. Definition of done for the first usable release

- [x] Podman Compose starts PostgreSQL/pgvector, web, and ingestion services.
- [~] User can configure HA and MQTT connections through the UI; test-connection actions remain.
- [x] HA entities and current states are visible.
- [x] HA state changes are stored historically.
- [x] MQTT raw messages are visible.
- [x] Scalar MQTT values are parsed and historized.
- [x] Multi-field JSON MQTT values are parsed and historized independently.
- [ ] Users can assign names, attributes, and tags.
- [ ] Users can link MQTT fields to HA entities.
- [x] Users can inspect current and historical values.
- [ ] Application survives temporary source disconnections.
- [~] Database migrations are documented; backup/restore procedures remain to be completed.

## 10. Decision log

| Date | Decision | Status |
|---|---|---|
| 2026-10-08 | Prefer PostgreSQL with pgvector | Accepted |
| 2026-10-08 | Use Python and Flask unless implementation findings show a strong reason otherwise | Accepted |
| 2026-10-08 | Preserve raw MQTT/HA source data and normalize extracted values separately | Accepted |
| 2026-10-08 | Support scalar MQTT payloads and multi-field/nested JSON payloads | Accepted |
| 2026-10-08 | Link at topic, field, device, and entity levels through typed object links | Accepted; workflows pending |
| 2026-10-09 | Use Podman Compose with standalone containers for the local development stack | Accepted |
| 2026-10-09 | Keep restart/setup instructions in `docs/RESTART_GUIDE.md` and implementation status here | Accepted |
