"""Read-only MCP interface for HA MQTT Store."""
import json
import os
from datetime import datetime
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import func, or_, select

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

mcp = MCPServer("HA MQTT Store")


def _setting():
    with SessionLocal() as session:
        setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == "mcp"))
        value = setting.setting_value if setting else {}
    return {"enabled": bool(value.get("enabled", False)), "access_level": value.get("access_level", "read_only")}


def _require_read_access():
    config = _setting()
    if not config["enabled"]:
        raise PermissionError("MCP read access is disabled in application settings")
    if config["access_level"] != "read_only":
        raise PermissionError("Unsupported MCP access level")


def _iso(value: Any):
    return value.isoformat() if isinstance(value, datetime) else value


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
    """Return newest-first state history for a Home Assistant entity."""
    _require_read_access(); limit = max(1, min(limit, 500))
    with SessionLocal() as session:
        entity = session.scalar(select(HAEntity).where(HAEntity.entity_id == entity_id))
        if not entity: return []
        rows = session.scalars(select(HAStateHistory).where(HAStateHistory.ha_entity_id == entity.id).order_by(HAStateHistory.observed_at.desc()).limit(limit)).all()
        return [{"observed_at": _iso(row.observed_at), "state": row.state_text, "numeric": row.state_numeric, "boolean": row.state_boolean, "attributes": _redact(row.attributes)} for row in rows]


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