from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from hamqtt_store.integrations.ha_worker import upsert_state


def test_replayed_state_does_not_create_duplicate_history():
    observed_at = datetime(2026, 10, 9, 19, 47, 29, 823534, tzinfo=timezone.utc)
    obj = SimpleNamespace(id=10, display_name="Example")
    entity = SimpleNamespace(id=20)
    current = SimpleNamespace()
    existing_history = SimpleNamespace(id=30)
    session = MagicMock()
    session.scalar.side_effect = [obj, entity, current, existing_history]

    upsert_state(session, 1, {
        "entity_id": "sensor.example",
        "state": "61",
        "last_changed": observed_at.isoformat(),
        "last_updated": observed_at.isoformat(),
        "attributes": {"friendly_name": "Example"},
    })

    added_history = [
        call.args[0]
        for call in session.add.call_args_list
        if call.args and call.args[0].__class__.__name__ == "HAStateHistory"
    ]
    assert added_history == []