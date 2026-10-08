import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select

from hamqtt_store.db import MQTTObservation, MQTTTopic, SessionLocal
from hamqtt_store.services.ingestion import ingest_mqtt_message


connection_id = 1
with SessionLocal() as session:
    from hamqtt_store.db import MQTTConnection

    connection = session.get(MQTTConnection, connection_id)
    if connection is None:
        connection = MQTTConnection(name="Smoke Test Broker", host="smoke-test", port=1883, enabled=False)
        session.add(connection)
        session.commit()

ingest_mqtt_message(connection_id, "smoke/scalar/temperature", b"21.7")
ingest_mqtt_message(
    connection_id,
    "smoke/living-room",
    json.dumps({"temperature": 21.7, "humidity": 46.2, "motion": False}).encode(),
)

with SessionLocal() as session:
    topic = session.scalar(select(MQTTTopic).where(MQTTTopic.topic == "smoke/living-room"))
    observations = session.scalars(
        select(MQTTObservation).where(MQTTObservation.mqtt_topic_id == topic.id)
    ).all()
    fields = {observation.value_type for observation in observations}
    assert topic is not None
    assert len(observations) == 3, len(observations)
    assert {"number", "boolean"}.issubset(fields), fields
    print(f"MQTT smoke test passed: {len(observations)} observations")
