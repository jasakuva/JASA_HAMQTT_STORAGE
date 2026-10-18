import subprocess
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from hamqtt_store.services import backup
from hamqtt_store.services.backup import (
    FAILED_BACKUP_RETRY_DELAY,
    _command_detail,
    _dump_command,
    _pgbackrest_command,
    _run_scheduled_backup,
    due_backup,
    list_portable_dumps,
    normalize_config,
    portable_dump_file,
)


def test_backup_config_uses_independent_default_profiles():
    config = normalize_config({})

    assert config["schedule_profile"] == "low"
    assert config["retention_profile"] == "medium"
    assert config["full_interval_days"] == 7
    assert config["differential_interval_hours"] == 24
    assert config["retention_count"] == 5


def test_backup_profiles_resolve_schedule_and_retention():
    config = normalize_config({"schedule_profile": "high", "retention_profile": "low", "portable_dump_daily": "on"})

    assert config["full_interval_days"] == 1
    assert config["differential_interval_hours"] == 1
    assert config["retention_count"] == 2
    assert config["portable_dump_daily"] is True


def test_invalid_profiles_fall_back_to_safe_defaults():
    config = normalize_config({"schedule_profile": "invalid", "retention_profile": "invalid"})

    assert config["schedule_profile"] == "low"
    assert config["retention_profile"] == "medium"


def test_due_backup_uses_completion_time():
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    latest = SimpleNamespace(completed_at=now - timedelta(hours=24), started_at=now - timedelta(hours=25))
    config = normalize_config({"differential_interval_hours": 24})

    assert due_backup(config, "diff", now, latest)


def test_due_backup_delays_retry_after_failure():
    now = datetime(2026, 10, 17, 19, 40, tzinfo=UTC)
    failed = SimpleNamespace(
        status="failed",
        started_at=now - timedelta(minutes=2),
        completed_at=now - timedelta(minutes=1),
    )
    config = normalize_config({})

    assert not due_backup(config, "diff", now, None, failed)
    assert due_backup(config, "diff", now + FAILED_BACKUP_RETRY_DELAY, None, failed)


def test_due_backup_does_not_overlap_active_request():
    now = datetime(2026, 10, 17, 19, 40, tzinfo=UTC)
    active = SimpleNamespace(status="running", started_at=now, completed_at=None)

    assert not due_backup(normalize_config({}), "full", now, None, active)


def test_command_detail_preserves_stdout_and_stderr():
    result = subprocess.CompletedProcess(
        ["pgbackrest"],
        82,
        stdout="ERROR: WAL segment was not archived\n",
        stderr="libpq.so.5: no version information available\n",
    )

    assert _command_detail(result, "fallback") == (
        "ERROR: WAL segment was not archived\n"
        "libpq.so.5: no version information available"
    )


def test_scheduled_backup_is_labeled_and_does_not_overlap(monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "_active_backup", lambda session: None)
    monkeypatch.setattr(backup, "_latest_completed", lambda session, backup_type: None)
    monkeypatch.setattr(backup, "_latest_attempt", lambda session, backup_type: None)
    monkeypatch.setattr(
        backup,
        "run_backup",
        lambda backup_type, triggered_by: calls.append((backup_type, triggered_by)),
    )

    assert _run_scheduled_backup(object(), normalize_config({}), datetime.now(UTC))
    assert calls == [("full", "schedule")]

    monkeypatch.setattr(backup, "_active_backup", lambda session: object())
    assert not _run_scheduled_backup(object(), normalize_config({}), datetime.now(UTC))
    assert calls == [("full", "schedule")]


def test_pgbackrest_backup_command_does_not_use_unsupported_json_output():
    command = _pgbackrest_command(normalize_config({}), "full")

    assert command == [
        "pgbackrest",
        "--stanza=hamqtt",
        "--repo=1",
        "backup",
        "--type=full",
        "--repo1-retention-full=5",
    ]


def test_dump_command_uses_portable_custom_format():
    command = _dump_command(normalize_config({}), __import__("pathlib").Path("/tmp/example.dump"))

    assert command[:5] == ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--dbname"]
    assert command[-2:] == ["--file", "\\tmp\\example.dump"]


def test_dump_schedule_uses_daily_interval():
    now = datetime(2026, 10, 16, 12, tzinfo=UTC)
    latest = SimpleNamespace(completed_at=now - timedelta(hours=24), started_at=now - timedelta(hours=25))
    config = normalize_config({"portable_dump_daily": True})

    assert due_backup({**config, "differential_interval_hours": 24}, "dump", now, latest)


def test_portable_dump_listing_is_filtered_and_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_REPOSITORY_PATH", str(tmp_path))
    dump_directory = tmp_path / "dumps"
    dump_directory.mkdir()
    older = dump_directory / "hamqtt-store-older.dump"
    newer = dump_directory / "hamqtt-store-newer.dump"
    older.write_bytes(b"old")
    newer.write_bytes(b"newer")
    (dump_directory / "notes.txt").write_text("not a dump", encoding="utf-8")
    older.touch()
    newer.touch()
    import os
    os.utime(older, (1_700_000_000, 1_700_000_000))
    os.utime(newer, (1_800_000_000, 1_800_000_000))

    files = list_portable_dumps(normalize_config({}))

    assert [item["name"] for item in files] == [newer.name, older.name]
    assert files[0]["size_bytes"] == 5


def test_portable_dump_file_rejects_invalid_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_REPOSITORY_PATH", str(tmp_path))
    dump_directory = tmp_path / "dumps"
    dump_directory.mkdir()
    valid = dump_directory / "hamqtt-store-valid.dump"
    valid.write_bytes(b"backup")
    (tmp_path / "secret.dump").write_bytes(b"secret")
    config = normalize_config({})

    assert portable_dump_file(config, valid.name) == valid.resolve()
    assert portable_dump_file(config, "../secret.dump") is None
    assert portable_dump_file(config, "not-a-dump.txt") is None
    assert portable_dump_file(config, "missing.dump") is None