from datetime import datetime, timezone
from sqlalchemy import select
from ..db import (SessionLocal, Object, MQTTTopic, MQTTMessage, MQTTPayloadField,
                  MQTTObservation, MQTTCurrentValue, MQTTParseEvent, utcnow)
from .mqtt_parser import parse_payload, payload_hash

def get_or_create_object(session, object_type, source_type, identifier, display_name=None):
    obj = session.scalar(select(Object).where(Object.source_type == source_type, Object.source_identifier == identifier))
    if not obj:
        obj = Object(object_type=object_type, source_type=source_type, source_identifier=identifier,
                     display_name=display_name or identifier, first_seen_at=utcnow(), last_seen_at=utcnow())
        session.add(obj); session.flush()
    else:
        obj.last_seen_at = utcnow()
        if display_name and not obj.display_name: obj.display_name = display_name
    return obj

def _typed_values(value):
    return {
        "value_text": value if isinstance(value, str) else None,
        "value_numeric": float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
        "value_boolean": value if isinstance(value, bool) else None,
        "value_json": value if isinstance(value, (dict, list)) else None,
    }

def ingest_mqtt_message(connection_id: int, topic: str, payload: bytes, qos=0, retain=False, duplicate=False):
    received_at = utcnow()
    with SessionLocal() as session:
        topic_obj = get_or_create_object(session, "mqtt_topic", "mqtt", topic, topic)
        mqtt_topic = session.scalar(select(MQTTTopic).where(MQTTTopic.mqtt_connection_id == connection_id, MQTTTopic.topic == topic))
        if not mqtt_topic:
            mqtt_topic = MQTTTopic(object_id=topic_obj.id, mqtt_connection_id=connection_id, topic=topic,
                                   first_seen_at=received_at, last_seen_at=received_at)
            session.add(mqtt_topic); session.flush()
        payload_type, parsed, fields, payload_text = parse_payload(payload)
        message = MQTTMessage(mqtt_connection_id=connection_id, mqtt_topic_id=mqtt_topic.id,
                              received_at=received_at, qos=qos, retain=retain, duplicate=duplicate,
                              payload_type=payload_type, payload_text=payload_text if payload_type != "json" else None,
                              payload_json=parsed if payload_type == "json" else None,
                              payload_binary=payload if payload_type not in {"json", "number", "boolean", "text", "empty"} else None,
                              payload_size=len(payload), payload_hash=payload_hash(payload))
        session.add(message); session.flush()
        mqtt_topic.last_seen_at = received_at; mqtt_topic.message_count += 1
        try:
            for field in fields:
                identifier = f"{topic}.{field.path}"
                field_obj = get_or_create_object(session, "mqtt_value", "mqtt", identifier, f"{topic} / {field.name}")
                field_row = session.scalar(select(MQTTPayloadField).where(MQTTPayloadField.mqtt_topic_id == mqtt_topic.id,
                                                                           MQTTPayloadField.field_path == field.path))
                if not field_row:
                    field_row = MQTTPayloadField(mqtt_topic_id=mqtt_topic.id, object_id=field_obj.id,
                                                 field_path=field.path, field_name=field.name, data_type=field.value_type,
                                                 first_seen_at=received_at, last_seen_at=received_at)
                    session.add(field_row); session.flush()
                field_row.last_seen_at = received_at; field_row.observation_count += 1
                typed = _typed_values(field.value)
                observation = MQTTObservation(mqtt_topic_id=mqtt_topic.id, mqtt_payload_field_id=field_row.id,
                    object_id=field_obj.id, source_message_id=message.id, observed_at=received_at,
                    received_at=received_at, value_type=field.value_type, raw_field_value=field.value, **typed)
                session.add(observation)
                current = session.scalar(select(MQTTCurrentValue).where(MQTTCurrentValue.mqtt_payload_field_id == field_row.id))
                if not current:
                    current = MQTTCurrentValue(mqtt_payload_field_id=field_row.id, object_id=field_obj.id,
                                               last_observed_at=received_at, received_at=received_at,
                                               value_type=field.value_type, **typed)
                    session.add(current)
                else:
                    current.last_observed_at = received_at; current.received_at = received_at
                    current.value_type = field.value_type
                    for key, val in typed.items(): setattr(current, key, val)
            session.add(MQTTParseEvent(mqtt_message_id=message.id, status="success", details={"fields": len(fields)}))
        except Exception as exc:
            session.add(MQTTParseEvent(mqtt_message_id=message.id, status="partial_success", error_message=str(exc)))
        session.commit()
        return message.id
