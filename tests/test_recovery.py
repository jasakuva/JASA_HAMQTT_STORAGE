import hashlib
import io
from types import SimpleNamespace

import pytest
from werkzeug.datastructures import FileStorage

from hamqtt_store.services import recovery


@pytest.fixture
def recovery_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "settings", SimpleNamespace(app_data_dir=str(tmp_path)))
    return tmp_path


def upload(filename="portable.dump", content=b"portable backup"):
    return FileStorage(stream=io.BytesIO(content), filename=filename)


def test_stage_upload_uses_opaque_name_and_records_digest(recovery_directory):
    job = recovery.stage_upload(upload("../customer-backup.dump"), uploader_id=7, uploader_name="admin")

    stored = recovery.uploads_path() / job["stored_name"]
    assert stored.read_bytes() == b"portable backup"
    assert stored.name == f"{job['id']}.dump"
    assert job["original_name"] == "customer-backup.dump"
    assert job["sha256"] == hashlib.sha256(b"portable backup").hexdigest()
    assert recovery.load_job(job["id"])["state"] == "uploaded"


def test_stage_upload_rejects_extension_empty_and_oversize(monkeypatch, recovery_directory):
    with pytest.raises(ValueError, match=r"\.dump"):
        recovery.stage_upload(upload("backup.sql"), uploader_id=7, uploader_name="admin")
    with pytest.raises(ValueError, match="empty"):
        recovery.stage_upload(upload(content=b""), uploader_id=7, uploader_name="admin")
    monkeypatch.setattr(recovery, "max_upload_bytes", lambda: 3)
    with pytest.raises(ValueError, match="limit"):
        recovery.stage_upload(upload(content=b"four"), uploader_id=7, uploader_name="admin")


def test_validate_job_records_success_and_checksum_failure(monkeypatch, recovery_directory):
    job = recovery.stage_upload(upload(), uploader_id=7, uploader_name="admin")
    monkeypatch.setattr(recovery, "_run", lambda command, timeout=3600: "archive contents")

    validated = recovery.validate_job(job)

    assert validated["state"] == "validated"
    assert validated["validation_output"] == "archive contents"

    tampered = recovery.stage_upload(upload("second.dump"), uploader_id=7, uploader_name="admin")
    (recovery.uploads_path() / tampered["stored_name"]).write_bytes(b"changed")
    invalid = recovery.validate_job(tampered)
    assert invalid["state"] == "invalid"
    assert "checksum" in invalid["error"]


def test_request_recovery_requires_validated_job_and_blocks_concurrency(recovery_directory):
    first = recovery.stage_upload(upload(), uploader_id=7, uploader_name="admin")
    with pytest.raises(ValueError, match="validated"):
        recovery.request_recovery(first["id"], confirmed_by="admin")

    first["state"] = "validated"
    recovery.save_job(first)
    queued = recovery.request_recovery(first["id"], confirmed_by="admin")
    assert queued["state"] == "recovery_requested"

    second = recovery.stage_upload(upload("second.dump"), uploader_id=7, uploader_name="admin")
    second["state"] = "validated"
    recovery.save_job(second)
    with pytest.raises(ValueError, match="already active"):
        recovery.request_recovery(second["id"], confirmed_by="admin")


def test_maintenance_status_round_trip(recovery_directory):
    job = {"id": "a" * 32, "state": "recovering"}
    recovery._set_maintenance(job, "Restoring")
    assert recovery.maintenance_status()["message"] == "Restoring"
    recovery._clear_maintenance()
    assert recovery.maintenance_status() is None


def test_failed_rollback_backup_validation_does_not_replace_database(monkeypatch, recovery_directory):
    job = recovery.stage_upload(upload(), uploader_id=7, uploader_name="admin")
    job["state"] = "recovery_requested"
    recovery.save_job(job)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://hamqtt:secret@postgres/hamqtt_store")
    calls = []

    def fake_run(command, timeout=3600):
        calls.append(command)
        if command[0] == "pg_dump":
            output = command[command.index("--file") + 1]
            __import__("pathlib").Path(output).write_bytes(b"broken rollback")
            return ""
        raise RuntimeError("rollback dump is invalid")

    monkeypatch.setattr(recovery, "_run", fake_run)
    monkeypatch.setattr(
        recovery,
        "_replace_database",
        lambda *args: (_ for _ in ()).throw(AssertionError("database replacement attempted")),
    )

    result = recovery.recover_job(job)

    assert result["state"] == "failed"
    assert [command[0] for command in calls] == ["pg_dump", "pg_restore"]
    assert recovery.maintenance_status() is None


def test_replace_database_uses_postgres_maintenance_database(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(recovery, "_run", lambda command, timeout=3600: commands.append(command) or "")
    monkeypatch.setenv("POSTGRES_USER", "hamqtt")

    recovery._replace_database(
        tmp_path / "restore.dump",
        "postgresql://hamqtt:secret@postgres/hamqtt_store",
        "postgresql://hamqtt:secret@postgres/postgres",
    )

    assert commands[1] == [
        "dropdb",
        "--if-exists",
        "--force",
        "--maintenance-db",
        "postgresql://hamqtt:secret@postgres/postgres",
        "hamqtt_store",
    ]
    assert commands[2] == [
        "createdb",
        "--maintenance-db",
        "postgresql://hamqtt:secret@postgres/postgres",
        "--owner",
        "hamqtt",
        "hamqtt_store",
    ]