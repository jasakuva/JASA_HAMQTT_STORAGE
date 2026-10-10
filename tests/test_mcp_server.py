import pytest


def test_mcp_module_imports_and_registers_read_only_server():
    mcp_server = pytest.importorskip("hamqtt_store.mcp_server")
    assert mcp_server.mcp.name == "HA MQTT Store"
    assert "get_system_summary" in mcp_server.mcp._tool_manager._tools


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