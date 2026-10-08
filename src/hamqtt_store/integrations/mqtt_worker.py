import logging
import time
import uuid
import paho.mqtt.client as mqtt
from sqlalchemy import select
from ..db import SessionLocal, MQTTConnection
from ..services.ingestion import ingest_mqtt_message

log = logging.getLogger(__name__)

def run():
    while True:
        with SessionLocal() as session:
            connections = session.scalars(select(MQTTConnection).where(MQTTConnection.enabled)).all()
            configs = [(c.id, c.host, c.port, c.username, c.password, c.client_id,
                        [(s.topic_filter, s.qos) for s in c.subscriptions if s.enabled]) for c in connections]
        if not configs:
            log.info("No enabled MQTT connections configured; retrying")
            time.sleep(10); continue
        for connection_id, host, port, username, password, client_id, subscriptions in configs:
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id or f"hamqtt-store-{uuid.uuid4().hex[:8]}")
                if username: client.username_pw_set(username, password)
                def on_message(_client, _userdata, message):
                    ingest_mqtt_message(connection_id, message.topic, bytes(message.payload), message.qos, message.retain, message.dup)
                client.on_message = on_message
                client.connect(host, port, 60)
                for topic_filter, qos in subscriptions or [("#", 0)]: client.subscribe(topic_filter, qos)
                client.loop_forever()
            except Exception:
                log.exception("MQTT connection failed for %s:%s", host, port)
                time.sleep(5)
