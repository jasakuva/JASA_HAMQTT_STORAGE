from datetime import datetime, timezone

from hamqtt_store.services import dashboard_cache
from hamqtt_store.services.dashboard_cache import DASHBOARD_MQTT_LIMIT, make_dashboard_entity, make_dashboard_message


def test_dashboard_message_compacts_json_and_keeps_required_fields():
    message = make_dashboard_message("home/test", b'{"temperature": 21.7}', qos=1, retain=True)

    assert message["topic"] == "home/test"
    assert message["message"] == '{"temperature":21.7}'
    assert message["qos"] == 1
    assert message["retain"] is True
    assert message["received_at"]


def test_dashboard_message_marks_binary_payloads():
    message = make_dashboard_message("home/binary", b"\xff\x00")

    assert message["message"] == "<binary payload, 2 bytes>"
    assert DASHBOARD_MQTT_LIMIT == 6


def test_dashboard_entity_preserves_numeric_value_and_update_time():
    updated = datetime(2026, 10, 12, 18, 42, tzinfo=timezone.utc)
    entity = make_dashboard_entity("sensor.temp", "Room temperature", "21.7", 21.7, None, updated)

    assert entity["value"] == 21.7
    assert entity["value_type"] == "numeric"
    assert entity["last_updated_at"] == "2026-10-12T18:42:00+00:00"


def test_dashboard_entity_supports_boolean_and_text_values():
    boolean = make_dashboard_entity("light.kitchen", "Kitchen light", "off", None, False, None)
    text = make_dashboard_entity("sensor.mode", None, "away", None, False, None)

    assert boolean["value"] is False
    assert boolean["value_type"] == "boolean"
    assert text["value"] == "away"
    assert text["value_type"] == "text"


def test_dashboard_entities_samples_fields_from_hash(monkeypatch):
    class FakeRedis:
        def hkeys(self, key):
            assert key == dashboard_cache.DASHBOARD_HA_KEY
            return ["sensor.one", "sensor.two", "sensor.three"]

        def hmget(self, key, fields):
            assert key == dashboard_cache.DASHBOARD_HA_KEY
            assert len(fields) == 3
            return [
                '{"entity_id":"sensor.one","value":1}',
                '{"entity_id":"sensor.two","value":2}',
                '{"entity_id":"sensor.three","value":3}',
            ]

    monkeypatch.setattr(dashboard_cache, "_client", FakeRedis())

    entities = dashboard_cache.get_dashboard_entities()

    assert len(entities) == 3
    assert {entity["entity_id"] for entity in entities} == {
        "sensor.one",
        "sensor.two",
        "sensor.three",
    }