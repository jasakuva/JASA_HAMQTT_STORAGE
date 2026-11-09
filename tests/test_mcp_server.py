import pytest
from datetime import UTC, datetime
from types import SimpleNamespace


def test_mcp_module_imports_and_registers_read_only_server():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    assert mcp_server.mcp.name == "HA MQTT Store"
    assert "get_system_summary" in mcp_server.mcp._tool_manager._tools
    assert "get_home_assistant_history_aggregated" in mcp_server.mcp._tool_manager._tools


def test_disabled_mcp_access_is_rejected(monkeypatch):
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    monkeypatch.setattr(mcp_server, "_setting", lambda: {"enabled": False, "access_level": "read_only"})
    with pytest.raises(PermissionError, match="disabled"):
        mcp_server._require_read_access()


def test_mcp_redacts_sensitive_payload_keys():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    value = {"temperature": 21, "password": "do-not-return", "nested": [{"token": "also-secret"}]}
    assert mcp_server._redact(value) == {"temperature": 21, "password": "[redacted]", "nested": [{"token": "[redacted]"}]}


def test_mcp_limits_are_clamped(monkeypatch):
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    captured = []

    class FakeScalars:
        def all(self):
            return []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def scalars(self, statement):
            captured.append(statement)
            return FakeScalars()

    monkeypatch.setattr(mcp_server, "_require_read_access", lambda: None)
    monkeypatch.setattr(mcp_server, "SessionLocal", FakeSession)
    mcp_server.search_objects("sensor", 999999)
    assert captured
    assert captured[0]._limit_clause.value == 500


def test_history_timestamp_is_normalized_to_utc():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")

    parsed = mcp_server._parse_history_timestamp("2026-11-08T14:00:00+02:00", "start")

    assert parsed == datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def test_history_aggregation_defaults_to_counter_for_energy_units():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    entity = SimpleNamespace(raw_entity={"attributes": {"unit_of_measurement": "Wh"}})

    assert mcp_server._aggregation_method(None, entity) == "counter_delta"
    assert mcp_server._aggregation_method("avg", entity) == "avg"


def test_history_aggregation_rejects_unknown_method():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    entity = SimpleNamespace(raw_entity={"attributes": {}})

    with pytest.raises(ValueError, match="aggregation_method"):
        mcp_server._aggregation_method("median", entity)


def test_aggregated_history_requires_explicit_interval(monkeypatch):
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    monkeypatch.setattr(mcp_server, "_require_read_access", lambda: None)

    with pytest.raises(ValueError, match="interval"):
        mcp_server.get_home_assistant_history_aggregated(
            "sensor.test",
            "2026-11-08T00:00:00Z",
            "2026-11-08T01:00:00Z",
            "5m",
        )


def test_history_aggregation_query_is_server_side_and_bounded(monkeypatch):
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    executed = []

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class FakeSession:
        def execute(self, statement, params=None):
            executed.append((str(statement), params))
            return FakeResult()

    result = mcp_server._aggregated_history(
        FakeSession(),
        entity_id=4,
        start=datetime(2026, 11, 8, tzinfo=UTC),
        end=datetime(2026, 11, 8, 1, tzinfo=UTC),
        interval="15m",
        method="avg",
        page_size=20,
        cursor=None,
    )

    assert result["items"] == []
    assert "generate_series" in executed[1][0]
    assert "date_bin" in executed[1][0]
    assert executed[1][1]["page_size"] == 21
    assert executed[0][0] == "SET LOCAL statement_timeout = '30000ms'"
    assert executed[0][1] is None