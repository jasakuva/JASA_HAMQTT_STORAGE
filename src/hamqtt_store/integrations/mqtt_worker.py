import logging
import time
import uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from sqlalchemy import select
from ..db import SessionLocal, MQTTConnection
from ..services.ingestion import ingest_mqtt_message

log = logging.getLogger(__name__)


def _update_connection_status(connection_id, *, connected=None, error=None):
    """Best-effort runtime status update; never interrupt MQTT processing."""
    try:
        with SessionLocal() as session:
            connection = session.get(MQTTConnection, connection_id)
            if not connection:
                return
            if connected:
                connection.last_connected_at = datetime.now(timezone.utc)
                connection.last_error = None
            elif error is not None:
                connection.last_error = str(error)
            session.commit()
    except Exception:
        log.exception("Could not update MQTT connection status for id=%s", connection_id)


def _subscription_failed(reason_code):
    """Handle both Paho v2 ReasonCode objects and integer return codes."""
    try:
        return bool(reason_code.is_failure)
    except AttributeError:
        try:
            return int(reason_code) != 0
        except (TypeError, ValueError):
            return True

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

                def on_connect(_client, _userdata, _flags, reason_code, _properties):
                    if _subscription_failed(reason_code):
                        error = f"MQTT broker rejected connection: {reason_code}"
                        _update_connection_status(connection_id, error=error)
                        log.error("%s (%s:%s)", error, host, port)
                    else:
                        _update_connection_status(connection_id, connected=True)
                        log.info("Connected to MQTT broker %s:%s for connection id=%s", host, port, connection_id)

                def on_disconnect(_client, _userdata, _disconnect_flags, reason_code, _properties):
                    log.warning("Disconnected from MQTT broker %s:%s: %s", host, port, reason_code)

                def on_subscribe(_client, _userdata, _message_id, reason_codes, _properties):
                    failures = [code for code in reason_codes if _subscription_failed(code)]
                    if failures:
                        error = f"MQTT broker rejected subscription(s): {failures}"
                        _update_connection_status(connection_id, error=error)
                        log.error("%s (%s:%s)", error, host, port)
                    else:
                        log.info("MQTT broker accepted subscription(s) for connection id=%s", connection_id)

                def on_message(_client, _userdata, message):
                    try:
                        message_id = ingest_mqtt_message(connection_id, message.topic, bytes(message.payload), message.qos, message.retain, message.dup)
                        log.debug("Stored MQTT message id=%s topic=%s bytes=%s", message_id, message.topic, len(message.payload))
                    except Exception as exc:
                        _update_connection_status(connection_id, error=f"Message save failed for {message.topic}: {exc}")
                        log.exception("Failed to store MQTT message topic=%s connection_id=%s", message.topic, connection_id)

                client.on_connect = on_connect
                client.on_disconnect = on_disconnect
                client.on_subscribe = on_subscribe
                client.on_message = on_message
                client.connect(host, port, 60)
                active_subscriptions = subscriptions or [("#", 0)]
                for topic_filter, qos in active_subscriptions:
                    result, message_id = client.subscribe(topic_filter, qos)
                    if result != mqtt.MQTT_ERR_SUCCESS:
                        error = f"Could not queue MQTT subscription for {topic_filter!r}: {result}"
                        _update_connection_status(connection_id, error=error)
                        raise RuntimeError(error)
                    log.info("Queued MQTT subscription filter=%r qos=%s mid=%s", topic_filter, qos, message_id)
                client.loop_forever()
            except Exception as exc:
                _update_connection_status(connection_id, error=exc)
                log.exception("MQTT connection failed for %s:%s", host, port)
                time.sleep(5)
