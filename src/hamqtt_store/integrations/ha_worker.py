import json
import logging
import time
from datetime import datetime, timezone
import websocket
from sqlalchemy import select
from ..db import SessionLocal, HAConnection, HAEntity, HAStateCurrent, HAStateHistory
from ..services.ingestion import get_or_create_object
from ..services.logging import record_log

log = logging.getLogger(__name__)

def _dt(value):
    if not value: return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

def run_connection(config):
    record_log("INFO", "ha_worker", "connecting", "Connecting to Home Assistant", context={"name": config.name, "url": config.base_url}, connection_id=config.id)
    ws_url = config.base_url.rstrip("/").replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"
    ws = websocket.create_connection(ws_url, timeout=30)
    auth = json.loads(ws.recv())
    if auth.get("type") != "auth_required": raise RuntimeError(f"Unexpected HA response: {auth}")
    ws.send(json.dumps({"type": "auth", "access_token": config.access_token}))
    if json.loads(ws.recv()).get("type") != "auth_ok": raise RuntimeError("Home Assistant authentication failed")
    record_log("INFO", "ha_worker", "connected", "Home Assistant authentication accepted", connection_id=config.id)
    ws.send(json.dumps({"id": 1, "type": "get_states"}))
    states = json.loads(ws.recv()).get("result", [])
    with SessionLocal() as session:
        for state in states: upsert_state(session, config.id, state)
        session.commit()
    ws.send(json.dumps({"id": 2, "type": "subscribe_events", "event_type": "state_changed"}))
    if not json.loads(ws.recv()).get("success"): raise RuntimeError("Could not subscribe to state_changed")
    record_log("INFO", "ha_worker", "subscribed", "Subscribed to Home Assistant state changes", connection_id=config.id)
    while True:
        message = json.loads(ws.recv())
        event = message.get("event", {}).get("data", {})
        if event.get("new_state"):
            with SessionLocal() as session:
                upsert_state(session, config.id, event["new_state"])
                session.commit()

def upsert_state(session, connection_id, state):
    entity_id = state.get("entity_id", "")
    domain = entity_id.split(".", 1)[0] if "." in entity_id else "unknown"
    obj = get_or_create_object(session, "ha_entity", "home_assistant", entity_id, state.get("attributes", {}).get("friendly_name", entity_id))
    entity = session.scalar(select(HAEntity).where(HAEntity.ha_connection_id == connection_id, HAEntity.entity_id == entity_id))
    if not entity:
        entity = HAEntity(object_id=obj.id, ha_connection_id=connection_id, entity_id=entity_id, domain=domain,
                          original_name=state.get("attributes", {}).get("friendly_name"), raw_entity=state)
        session.add(entity); session.flush()
    value = state.get("state")
    numeric = None
    try: numeric = float(value)
    except (TypeError, ValueError): pass
    boolean = value.lower() in {"on", "true"} if isinstance(value, str) else None
    changed = _dt(state.get("last_changed")); updated = _dt(state.get("last_updated"))
    current = session.scalar(select(HAStateCurrent).where(HAStateCurrent.ha_entity_id == entity.id))
    values = dict(state_text=str(value) if value is not None else None, state_numeric=numeric, state_boolean=boolean,
                  attributes=state.get("attributes", {}), last_changed_at=changed, last_updated_at=updated, raw_state=state)
    if not current: session.add(HAStateCurrent(ha_entity_id=entity.id, **values))
    else:
        for key, val in values.items(): setattr(current, key, val)
    history_exists = session.scalar(
        select(HAStateHistory.id).where(
            HAStateHistory.ha_entity_id == entity.id,
            HAStateHistory.observed_at == updated,
        )
    )
    if history_exists is None:
        session.add(HAStateHistory(
            ha_entity_id=entity.id,
            observed_at=updated,
            **{k: values[k] for k in ["state_text", "state_numeric", "state_boolean", "attributes", "raw_state"]},
        ))

def run():
    record_log("INFO", "ha_worker", "worker_started", "Home Assistant worker started")
    while True:
        with SessionLocal() as session:
            configs = session.scalars(select(HAConnection).where(HAConnection.enabled)).all()
        if not configs:
            log.info("No enabled Home Assistant connections configured; retrying")
            time.sleep(10); continue
        for config in configs:
            try: run_connection(config)
            except Exception as exc:
                detail = str(exc).strip() or repr(exc)
                exception_type = type(exc).__name__
                message = f"Home Assistant connection failed for '{config.name}' at {config.base_url}: {exception_type}: {detail}"
                log.exception("Home Assistant connection failed for %s", config.name)
                record_log(
                    "ERROR",
                    "ha_worker",
                    "worker_error",
                    message,
                    context={
                        "name": config.name,
                        "url": config.base_url,
                        "exception_type": exception_type,
                        "error": detail,
                    },
                    connection_id=config.id,
                )
                time.sleep(5)
