"""Read-only MCP interface for HA MQTT Store."""
import json
import os
from datetime import UTC, datetime
from typing import Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import func, or_, select, text

from .db import (
    HAEntity,
    HAStateCurrent,
    HAStateHistory,
    MQTTCurrentValue,
    MQTTMessage,
    MQTTObservation,
    MQTTPayloadField,
    MQTTTopic,
    Object,
    SessionLocal,
    SystemSetting,
)
from .services.recovery import maintenance_status

mcp = MCPServer("HA MQTT Store")


def _setting():
    with SessionLocal() as session:
        setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "mcp"))
        value = setting.setting_value if setting else {}
    return {"enabled": bool(value.get("enabled", False)), "access_level": value.get("access_level", "read_only")}


def _require_read_access():
    if maintenance_status() is not None:
        raise RuntimeError("Database recovery is in progress")
    config = _setting()
    if not config["enabled"]:
        raise PermissionError("MCP read access is disabled in application settings")
    if config["access_level"] != "read_only":
        raise PermissionError("Unsupported MCP access level")


def _iso(value: Any):
    return value.isoformat() if isinstance(value, datetime) else value


_AGGREGATION_INTERVALS = {"15m": 900, "1h": 3600}
_AGGREGATION_METHODS = {"avg", "min", "max", "first", "last", "sum", "counter_delta"}
AggregationInterval = Literal["15m", "1h"]
AggregationMethod = Literal["avg", "min", "max", "first", "last", "sum", "counter_delta"]
_MAX_HISTORY_PAGE_SIZE = 500
_MAX_AGGREGATED_BUCKETS = 10_000
_STATEMENT_TIMEOUT_MS = 30_000


def _parse_history_timestamp(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _history_page_size(value: int) -> int:
    return max(1, min(int(value), _MAX_HISTORY_PAGE_SIZE))


def _aggregation_method(method: str | None, entity: Any) -> str:
    if method is not None:
        if method not in _AGGREGATION_METHODS:
            raise ValueError(f"aggregation_method must be one of {sorted(_AGGREGATION_METHODS)}")
        return method
    unit = ((entity.raw_entity or {}).get("attributes") or {}).get("unit_of_measurement", "")
    return "counter_delta" if unit.lower() in {"wh", "kwh", "mwh", "bytes", "l"} else "avg"


def _aggregate_query(method: str) -> str:
    aggregate = {
        "avg": "avg(samples.state_numeric)",
        "min": "min(samples.state_numeric)",
        "max": "max(samples.state_numeric)",
        "sum": "sum(samples.state_numeric)",
        "first": "(array_agg(samples.state_numeric ORDER BY samples.observed_at ASC))[1]",
        "last": "(array_agg(samples.state_numeric ORDER BY samples.observed_at DESC))[1]",
        "counter_delta": "sum(CASE WHEN samples.delta_value > 0 THEN samples.delta_value ELSE 0 END)",
    }
    return aggregate[method]


def _aggregated_history(session, entity_id: int, start: datetime, end: datetime,
                        interval: str, method: str, page_size: int,
                        cursor: str | None) -> dict:
    step_seconds = _AGGREGATION_INTERVALS[interval]
    bucket_count = max(1, int((end - start).total_seconds() + step_seconds - 1) // step_seconds)
    if bucket_count > _MAX_AGGREGATED_BUCKETS:
        raise ValueError("requested range produces too many aggregated buckets")
    cursor_time = _parse_history_timestamp(cursor, "cursor") if cursor else start
    if cursor_time < start or cursor_time >= end:
        return {"items": [], "interval": interval, "aggregation_method": method, "next_cursor": None}

    aggregate_expression = _aggregate_query(method)
    delta_expression = "source_samples.state_numeric - lag(source_samples.state_numeric) OVER (ORDER BY source_samples.observed_at)" if method == "counter_delta" else "NULL"
    statement = text(f"""
        WITH source_samples AS (
            SELECT observed_at, state_numeric
            FROM ha_state_history
            WHERE ha_entity_id = :entity_id
              AND observed_at < :end_time
              AND state_numeric IS NOT NULL
              AND (
                  observed_at >= :start_time
                  OR observed_at = (
                      SELECT max(previous.observed_at)
                      FROM ha_state_history AS previous
                      WHERE previous.ha_entity_id = :entity_id
                        AND previous.observed_at < :start_time
                        AND previous.state_numeric IS NOT NULL
                  )
              )
        ), samples AS (
            SELECT observed_at, state_numeric,
                   {delta_expression} AS delta_value
            FROM source_samples
        ), bucket_range AS (
            SELECT date_bin(
                       (:step_seconds || ' seconds')::interval,
                       :cursor_time,
                       TIMESTAMPTZ '1970-01-01 00:00:00+00'
                   ) AS first_bucket
        ), buckets AS (
            SELECT generate_series(
                bucket_range.first_bucket,
                date_bin(
                    (:step_seconds || ' seconds')::interval,
                    :end_time - (:step_seconds || ' seconds')::interval,
                    TIMESTAMPTZ '1970-01-01 00:00:00+00'
                ),
                (:step_seconds || ' seconds')::interval
            ) AS bucket_start
            FROM bucket_range
        ), grouped AS (
            SELECT date_bin(
                       (:step_seconds || ' seconds')::interval,
                       samples.observed_at,
                       TIMESTAMPTZ '1970-01-01 00:00:00+00'
                   ) AS bucket_start,
                   {aggregate_expression} AS value,
                   count(*) AS sample_count,
                   count(*) FILTER (WHERE samples.state_numeric IS NOT NULL) AS valid_sample_count,
                   count(*) FILTER (WHERE samples.delta_value > 0) AS valid_delta_count,
                   max(samples.observed_at) AS last_observed_at
            FROM samples
            WHERE samples.observed_at >= :start_time
            GROUP BY 1
        )
        SELECT buckets.bucket_start,
               buckets.bucket_start + (:step_seconds || ' seconds')::interval AS bucket_end,
               grouped.value,
               COALESCE(grouped.sample_count, 0) AS sample_count,
               COALESCE(grouped.valid_sample_count, 0) AS valid_sample_count,
               COALESCE(grouped.valid_delta_count, 0) AS valid_delta_count,
               grouped.last_observed_at
        FROM buckets
        LEFT JOIN grouped ON grouped.bucket_start = buckets.bucket_start
        ORDER BY buckets.bucket_start
        LIMIT :page_size
    """)
    session.execute(text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT_MS}ms'"))
    rows = session.execute(statement, {
        "entity_id": entity_id,
        "start_time": start,
        "end_time": end,
        "cursor_time": cursor_time,
        "step_seconds": step_seconds,
        "page_size": page_size + 1,
    }).mappings().all()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    items = []
    for row in rows:
        sample_count = int(row["sample_count"] or 0)
        valid_count = int(row["valid_sample_count"] or 0)
        items.append({
            "bucket_start": _iso(row["bucket_start"]),
            "bucket_end": _iso(row["bucket_end"]),
            "value": row["value"],
            "interval": interval,
            "aggregation_method": method,
            "sample_count": sample_count,
            "valid_sample_count": valid_count,
            "valid_delta_count": int(row["valid_delta_count"] or 0),
            "coverage_percent": round(valid_count / sample_count * 100, 2) if sample_count else 0.0,
            "missing": sample_count == 0,
            "has_gap": sample_count == 0,
            "last_observed_at": _iso(row["last_observed_at"]),
        })
    next_cursor = _iso(rows[-1]["bucket_start"]) if has_more and rows else None
    return {
        "items": items,
        "interval": interval,
        "aggregation_method": method,
        "start": _iso(start),
        "end": _iso(end),
        "next_cursor": next_cursor,
    }


_SENSITIVE_KEYS = {"password", "passwd", "secret", "token", "access_token", "api_key", "apikey", "client_secret"}


def _redact(value: Any):
    if isinstance(value, dict):
        return {key: "[redacted]" if key.lower() in _SENSITIVE_KEYS else _redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _safe_text(value: str | None):
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return "[redacted sensitive text]" if any(key in value.lower() for key in _SENSITIVE_KEYS) else value
    return json.dumps(_redact(parsed), separators=(",", ":"))


def _object(row):
    return {"id": row.id, "type": row.object_type, "source": row.source_type,
            "identifier": row.source_identifier, "name": row.nickname or row.display_name,
            "description": row.description}


def _entity(entity, current=None):
    result = {"id": entity.id, "entity_id": entity.entity_id, "domain": entity.domain,
              "name": entity.original_name, "platform": entity.platform, "device_id": entity.device_id,
              "area_id": entity.area_id, "unique_id": entity.unique_id}
    if current:
        result["state"] = {"text": current.state_text, "numeric": current.state_numeric,
                            "boolean": current.state_boolean, "attributes": _redact(current.attributes),
                            "last_changed": _iso(current.last_changed_at),
                            "last_updated": _iso(current.last_updated_at)}
    else:
        result["state"] = None
    return result


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_system_summary() -> dict:
    """Return counts of stored objects, Home Assistant entities, MQTT topics, and messages."""
    _require_read_access()
    with SessionLocal() as session:
        return {"objects": session.scalar(select(func.count(Object.id))) or 0,
                "ha_entities": session.scalar(select(func.count(HAEntity.id))) or 0,
                "mqtt_topics": session.scalar(select(func.count(MQTTTopic.id))) or 0,
                "mqtt_messages": session.scalar(select(func.count(MQTTMessage.id))) or 0,
                "mcp_access_level": "read_only"}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def search_objects(query: str, limit: int = 50) -> list[dict]:
    """Search the object catalog by identifier, name, nickname, or description."""
    _require_read_access(); limit = max(1, min(limit, 500)); pattern = f"%{query}%"
    with SessionLocal() as session:
        rows = session.scalars(select(Object).where(or_(Object.source_identifier.ilike(pattern), Object.display_name.ilike(pattern), Object.nickname.ilike(pattern), Object.description.ilike(pattern))).order_by(Object.source_type, Object.source_identifier).limit(limit)).all()
        return [_object(row) for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_home_assistant_entities(query: str = "", limit: int = 100) -> list[dict]:
    """List Home Assistant entities with their current state; optionally filter by entity ID or name."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        statement = select(HAEntity).order_by(HAEntity.entity_id)
        if query:
            pattern = f"%{query}%"
            statement = statement.join(Object, Object.id == HAEntity.object_id).where(or_(HAEntity.entity_id.ilike(pattern), HAEntity.original_name.ilike(pattern), Object.display_name.ilike(pattern), Object.nickname.ilike(pattern)))
        entities = session.scalars(statement.limit(limit)).all()
        current = {row.ha_entity_id: row for row in session.scalars(select(HAStateCurrent).where(HAStateCurrent.ha_entity_id.in_([entity.id for entity in entities]))).all()} if entities else {}
        return [_entity(entity, current.get(entity.id)) for entity in entities]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_home_assistant_entity(entity_id: str) -> dict:
    """Return one Home Assistant entity and its current state by entity ID."""
    _require_read_access()
    with SessionLocal() as session:
        entity = session.scalar(select(HAEntity).where(HAEntity.entity_id == entity_id))
        if not entity: return {"error": "Home Assistant entity not found", "entity_id": entity_id}
        return _entity(entity, session.scalar(select(HAStateCurrent).where(HAStateCurrent.ha_entity_id == entity.id)))


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_home_assistant_history(entity_id: str, limit: int = 100) -> list[dict]:
    """Return raw Home Assistant history for one entity.

    Use only ``entity_id`` and optionally ``limit`` with this backwards-compatible
    raw-history tool. For time-bounded or aggregated history, use
    ``get_home_assistant_history_aggregated`` and provide its required ``start``,
    ``end``, and ``interval`` arguments.
    """
    _require_read_access()
    with SessionLocal() as session:
        entity = session.scalar(select(HAEntity).where(HAEntity.entity_id == entity_id))
        if not entity:
            return []
        limit = max(1, min(limit, _MAX_HISTORY_PAGE_SIZE))
        rows = session.scalars(select(HAStateHistory).where(HAStateHistory.ha_entity_id == entity.id).order_by(HAStateHistory.observed_at.desc()).limit(limit)).all()
        return [{"observed_at": _iso(row.observed_at), "state": row.state_text, "numeric": row.state_numeric, "boolean": row.state_boolean, "attributes": _redact(row.attributes)} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_home_assistant_history_aggregated(
    entity_id: str,
    start: str,
    end: str,
    interval: AggregationInterval,
    aggregation_method: AggregationMethod | None = None,
    cursor: str | None = None,
    page_size: int = 100,
) -> dict:
    """Return PostgreSQL-aggregated Home Assistant history.

    Required arguments are ``entity_id``, timezone-aware ISO-8601 ``start`` and
    ``end``, and ``interval`` (exactly ``15m`` or ``1h``). Optional aggregation
    methods are ``avg``, ``min``, ``max``, ``first``, ``last``, ``sum``, and
    ``counter_delta``. Use ``cursor`` to fetch the next page.
    """
    _require_read_access()
    if interval not in _AGGREGATION_INTERVALS:
        raise ValueError("interval must be one of ['15m', '1h']")
    start_time = _parse_history_timestamp(start, "start")
    end_time = _parse_history_timestamp(end, "end")
    if start_time is None or end_time is None or end_time <= start_time:
        raise ValueError("start and end are required and end must be after start")
    with SessionLocal() as session:
        entity = session.scalar(select(HAEntity).where(HAEntity.entity_id == entity_id))
        if not entity:
            return {"items": [], "next_cursor": None}
        method = _aggregation_method(aggregation_method, entity)
        return _aggregated_history(session, entity.id, start_time, end_time, interval, method, _history_page_size(page_size), cursor)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_mqtt_topics(query: str = "", limit: int = 100) -> list[dict]:
    """List MQTT topics with message counts and last-seen timestamps."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        statement = select(MQTTTopic).order_by(MQTTTopic.topic)
        if query: statement = statement.where(MQTTTopic.topic.ilike(f"%{query}%"))
        rows = session.scalars(statement.limit(limit)).all()
        return [{"id": row.id, "topic": row.topic, "message_count": row.message_count, "first_seen": _iso(row.first_seen_at), "last_seen": _iso(row.last_seen_at)} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_mqtt_topic_history(topic: str, limit: int = 100) -> list[dict]:
    """Return recent raw MQTT messages for a topic, excluding credentials and connection details."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        topic_row = session.scalar(select(MQTTTopic).where(MQTTTopic.topic == topic))
        if not topic_row: return []
        rows = session.scalars(select(MQTTMessage).where(MQTTMessage.mqtt_topic_id == topic_row.id).order_by(MQTTMessage.received_at.desc()).limit(limit)).all()
        return [{"id": row.id, "received_at": _iso(row.received_at), "payload_type": row.payload_type, "payload_text": _safe_text(row.payload_text), "payload_json": _redact(row.payload_json), "payload_size": row.payload_size, "qos": row.qos, "retain": row.retain, "duplicate": row.duplicate} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_mqtt_field_history(field_id: int, limit: int = 100) -> list[dict]:
    """Return recent parsed observations for one MQTT payload field."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        rows = session.scalars(select(MQTTObservation).where(MQTTObservation.mqtt_payload_field_id == field_id).order_by(MQTTObservation.observed_at.desc()).limit(limit)).all()
        return [{"id": row.id, "observed_at": _iso(row.observed_at), "received_at": _iso(row.received_at), "type": row.value_type, "text": row.value_text, "numeric": row.value_numeric, "boolean": row.value_boolean, "json": row.value_json, "quality": row.quality} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_mqtt_fields(topic: str, limit: int = 200) -> list[dict]:
    """List parsed payload fields for an MQTT topic."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        topic_row = session.scalar(select(MQTTTopic).where(MQTTTopic.topic == topic))
        if not topic_row:
            return []
        rows = session.scalars(select(MQTTPayloadField).where(MQTTPayloadField.mqtt_topic_id == topic_row.id).order_by(MQTTPayloadField.field_path).limit(limit)).all()
        return [{"id": row.id, "path": row.field_path, "name": row.field_name, "data_type": row.data_type, "observation_count": row.observation_count, "first_seen": _iso(row.first_seen_at), "last_seen": _iso(row.last_seen_at)} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_mqtt_current_value(field_id: int) -> dict:
    """Return the current parsed value for an MQTT payload field."""
    _require_read_access()
    with SessionLocal() as session:
        row = session.scalar(select(MQTTCurrentValue).where(MQTTCurrentValue.mqtt_payload_field_id == field_id))
        if not row:
            return {"error": "MQTT field current value not found", "field_id": field_id}
        return {"field_id": field_id, "last_observed_at": _iso(row.last_observed_at), "received_at": _iso(row.received_at), "type": row.value_type, "text": _safe_text(row.value_text), "numeric": row.value_numeric, "boolean": row.value_boolean, "json": _redact(row.value_json), "unit": row.unit}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_recent_mqtt_messages(limit: int = 100) -> list[dict]:
    """Return the newest raw MQTT messages across all topics."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        rows = session.scalars(select(MQTTMessage).order_by(MQTTMessage.received_at.desc()).limit(limit)).all()
        return [{"id": row.id, "topic_id": row.mqtt_topic_id, "received_at": _iso(row.received_at), "payload_type": row.payload_type, "payload_text": _safe_text(row.payload_text), "payload_json": _redact(row.payload_json), "payload_size": row.payload_size, "qos": row.qos, "retain": row.retain, "duplicate": row.duplicate} for row in rows]


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_object(object_id: int) -> dict:
    """Return one object catalog record by numeric ID."""
    _require_read_access()
    with SessionLocal() as session:
        row = session.get(Object, object_id)
        return _object(row) if row else {"error": "Object not found", "object_id": object_id}


@mcp.resource("hamqtt://summary", mime_type="application/json")
def summary_resource() -> dict:
    """Live summary of the stored HA MQTT data."""
    return get_system_summary()


@mcp.resource("hamqtt://entities/{entity_id}", mime_type="application/json")
def entity_resource(entity_id: str) -> dict:
    """Current state for a Home Assistant entity."""
    return get_home_assistant_entity(entity_id)


def main():
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "streamable-http"}:
        raise SystemExit("MCP_TRANSPORT must be stdio or streamable-http")
    if transport == "streamable-http":
        mcp.run(transport=transport, host="0.0.0.0", port=int(os.getenv("MCP_PORT", "8000")))
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()