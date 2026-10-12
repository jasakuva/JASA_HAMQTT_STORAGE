import json
import logging
from datetime import datetime, timezone

import redis

from ..config import settings

log = logging.getLogger(__name__)

DASHBOARD_MQTT_KEY = "dashboard:mqtt:latest"
DASHBOARD_MQTT_LIMIT = 6
_client = None


def _redis_client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                       socket_connect_timeout=1, socket_timeout=1)
    return _client


def make_dashboard_message(topic, payload, qos=0, retain=False):
    """Build the intentionally small representation used by the dashboard cache."""
    raw = bytes(payload)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = f"<binary payload, {len(raw)} bytes>"
    else:
        try:
            text = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "message": text[:500] + ("…" if len(text) > 500 else ""),
        "qos": qos,
        "retain": bool(retain),
    }


def cache_dashboard_message(message):
    """Best-effort cache write; Redis must never interrupt MQTT ingestion."""
    try:
        client = _redis_client()
        client.lpush(DASHBOARD_MQTT_KEY, json.dumps(message, ensure_ascii=False))
        client.ltrim(DASHBOARD_MQTT_KEY, 0, DASHBOARD_MQTT_LIMIT - 1)
    except Exception:
        log.warning("Could not update dashboard MQTT cache", exc_info=True)


def get_dashboard_messages():
    try:
        values = _redis_client().lrange(DASHBOARD_MQTT_KEY, 0, DASHBOARD_MQTT_LIMIT - 1)
        return [json.loads(value) for value in values]
    except Exception:
        log.warning("Could not read dashboard MQTT cache", exc_info=True)
        return []