from hamqtt_store.services.dashboard_cache import DASHBOARD_MQTT_LIMIT, make_dashboard_message


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