from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from hamqtt_store.services.backup import _pgbackrest_command, due_backup, normalize_config


def test_backup_config_supports_weekly_full_and_daily_differential_defaults():
    config = normalize_config({})

    assert config["full_interval_days"] == 7
    assert config["differential_interval_hours"] == 24
    assert config["retention_full_count"] == 4


def test_backup_config_supports_aggressive_intervals_and_clamps_values():
    config = normalize_config({"full_interval_days": 1, "differential_interval_hours": 1, "retention_full_count": 0})

    assert config["full_interval_days"] == 1
    assert config["differential_interval_hours"] == 1
    assert config["retention_full_count"] == 1


def test_due_backup_uses_completion_time():
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    latest = SimpleNamespace(completed_at=now - timedelta(hours=24), started_at=now - timedelta(hours=25))
    config = normalize_config({"differential_interval_hours": 24})

    assert due_backup(config, "diff", now, latest)


def test_pgbackrest_backup_command_does_not_use_unsupported_json_output():
    command = _pgbackrest_command(normalize_config({}), "full")

    assert command == [
        "pgbackrest",
        "--stanza=hamqtt",
        "--repo=1",
        "backup",
        "--type=full",
        "--repo1-retention-full=4",
        "--repo1-retention-diff=14",
    ]