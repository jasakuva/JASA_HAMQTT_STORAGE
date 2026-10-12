from hamqtt_store.services.mqtt_parser import flatten_scalars, parse_payload
from hamqtt_store.services.ingestion import should_skip_mqtt_parsing

def test_scalar_number():
    payload_type, value, fields, _ = parse_payload(b"21.7")
    assert payload_type == "number"
    assert value == 21.7
    assert fields[0].path == "value"

def test_json_multiple_nested_values():
    payload_type, _, fields, _ = parse_payload(b'{"environment":{"temperature":21.7,"humidity":46},"motion":false}')
    assert payload_type == "json"
    assert {f.path for f in fields} == {"environment.temperature", "environment.humidity", "motion"}

def test_json_array_paths():
    fields = flatten_scalars({"values": [1, 2]})
    assert [field.path for field in fields] == ["values[0]", "values[1]"]


def test_zigbee2mqtt_bridge_topics_skip_parsing():
    assert should_skip_mqtt_parsing("zigbee2mqtt/bridge")
    assert should_skip_mqtt_parsing("zigbee2mqtt/bridge/definitions")
    assert should_skip_mqtt_parsing("zigbee2mqtt/bridge/devices")
    assert not should_skip_mqtt_parsing("zigbee2mqtt/living_room_sensor")
    assert not should_skip_mqtt_parsing("other/zigbee2mqtt/bridge/devices")
