"""Staged portable-dump validation and database recovery coordination."""

import hashlib
import json
import logging
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from ..config import settings

log = logging.getLogger(__name__)

CONFIRMATION_PHRASE = "RESTORE DATABASE"
ACTIVE_STATES = {"recovery_requested", "recovering", "rolling_back"}


def recovery_root() -> Path:
    return Path(settings.app_data_dir) / "recovery"


def jobs_path() -> Path:
    return recovery_root() / "jobs"


def uploads_path() -> Path:
    return recovery_root() / "uploads"


def maintenance_path() -> Path:
    return recovery_root() / "maintenance.json"


def request_lock_path() -> Path:
    return recovery_root() / "recovery-request.lock"


def max_upload_bytes() -> int:
    try:
        megabytes = int(os.getenv("RECOVERY_MAX_UPLOAD_MB", "1024"))
    except ValueError:
        megabytes = 1024
    return max(1, megabytes) * 1024 * 1024


def _utcnow_text() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def save_job(job: dict) -> dict:
    job["updated_at"] = _utcnow_text()
    _atomic_json(jobs_path() / f"{job['id']}.json", job)
    return job


def load_job(job_id: str) -> dict | None:
    if not job_id or len(job_id) != 32 or any(character not in "0123456789abcdef" for character in job_id):
        return None
    path = jobs_path() / f"{job_id}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def list_jobs() -> list[dict]:
    if not jobs_path().is_dir():
        return []
    jobs = []
    for path in jobs_path().glob("*.json"):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            log.warning("Ignoring unreadable recovery job %s", path)
    return sorted(jobs, key=lambda item: item.get("created_at", ""), reverse=True)


def stage_upload(file_storage, *, uploader_id: int, uploader_name: str) -> dict:
    original_name = Path(file_storage.filename or "").name
    if not original_name or not original_name.lower().endswith(".dump"):
        raise ValueError("Select a PostgreSQL .dump file")

    job_id = uuid.uuid4().hex
    uploads_path().mkdir(parents=True, exist_ok=True)
    target = uploads_path() / f"{job_id}.dump"
    digest = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := file_storage.stream.read(1024 * 1024):
                size += len(chunk)
                if size > max_upload_bytes():
                    raise ValueError(f"Upload exceeds the {max_upload_bytes() // (1024 * 1024)} MB limit")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise ValueError("The uploaded dump is empty")
    except Exception:
        target.unlink(missing_ok=True)
        raise

    now = _utcnow_text()
    return save_job(
        {
            "id": job_id,
            "state": "uploaded",
            "original_name": original_name,
            "stored_name": target.name,
            "size_bytes": size,
            "sha256": digest.hexdigest(),
            "uploader_id": uploader_id,
            "uploader_name": uploader_name,
            "created_at": now,
            "updated_at": now,
            "validation_output": None,
            "restore_output": None,
            "rollback_dump": None,
            "error": None,
        }
    )


def request_recovery(job_id: str, *, confirmed_by: str) -> dict:
    recovery_root().mkdir(parents=True, exist_ok=True)
    try:
        lock = request_lock_path().open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("Another database recovery request is being processed") from exc
    try:
        lock.write(job_id)
        lock.close()
        job = load_job(job_id)
        if not job or job.get("state") != "validated":
            raise ValueError("Only a validated dump can be recovered")
        if any(item.get("state") in ACTIVE_STATES for item in list_jobs() if item.get("id") != job_id):
            raise ValueError("Another database recovery is already active")
        job["state"] = "recovery_requested"
        job["confirmed_by"] = confirmed_by
        job["confirmed_at"] = _utcnow_text()
        return save_job(job)
    finally:
        lock.close()
        request_lock_path().unlink(missing_ok=True)


def wait_while_maintenance(poll_seconds: int = 3) -> None:
    while maintenance_status() is not None:
        time.sleep(poll_seconds)


def maintenance_status() -> dict | None:
    try:
        return json.loads(maintenance_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _set_maintenance(job: dict, message: str) -> None:
    _atomic_json(
        maintenance_path(),
        {"job_id": job["id"], "state": job["state"], "message": message, "updated_at": _utcnow_text()},
    )


def _clear_maintenance() -> None:
    maintenance_path().unlink(missing_ok=True)


def _run(command: list[str], *, timeout: int = 3600) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part and part.strip())
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit status {result.returncode}: {output[-4000:]}")
    return output[-12000:]


def _database_urls() -> tuple[str, str]:
    parsed = urlsplit(os.getenv("DATABASE_URL", "").replace("postgresql+psycopg", "postgresql", 1))
    if not parsed.scheme or not parsed.hostname or parsed.path in {"", "/"}:
        raise RuntimeError("DATABASE_URL must identify the application PostgreSQL database")
    database_url = urlunsplit(parsed)
    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))
    return database_url, admin_url


def validate_job(job: dict) -> dict:
    job["state"] = "validating"
    save_job(job)
    target = uploads_path() / job["stored_name"]
    try:
        if target.is_symlink() or not target.is_file() or target.parent.resolve() != uploads_path().resolve():
            raise RuntimeError("Staged upload is missing or unsafe")
        current_hash = _sha256(target)
        if current_hash != job["sha256"]:
            raise RuntimeError("Staged upload checksum changed")
        job["validation_output"] = _run(["pg_restore", "--list", str(target)], timeout=300)
        job["state"] = "validated"
        job["validated_at"] = _utcnow_text()
        job["error"] = None
    except Exception as exc:
        job["state"] = "invalid"
        job["error"] = str(exc)
        log.exception("Recovery upload validation failed for job %s", job["id"])
    return save_job(job)


def _replace_database(dump: Path, database_url: str, admin_url: str) -> str:
    database_name = urlsplit(database_url).path.lstrip("/")
    database_literal = database_name.replace("'", "''")
    outputs = [
        _run(
            [
                "psql",
                "--dbname",
                admin_url,
                "--set",
                "ON_ERROR_STOP=1",
                "--command",
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{database_literal}' AND pid <> pg_backend_pid();",
            ]
        ),
        _run(["dropdb", "--if-exists", "--force", "--maintenance-db", admin_url, database_name]),
        _run(["createdb", "--maintenance-db", admin_url, "--owner", os.getenv("POSTGRES_USER", "hamqtt"), database_name]),
        _run(["pg_restore", "--exit-on-error", "--no-owner", "--dbname", database_url, str(dump)]),
        _run(["python", "-m", "alembic", "upgrade", "head"]),
    ]
    return "\n".join(output for output in outputs if output)[-12000:]


def recover_job(job: dict) -> dict:
    database_url, admin_url = _database_urls()
    target = uploads_path() / job["stored_name"]
    dump_directory = Path(os.getenv("BACKUP_REPOSITORY_PATH", "/var/lib/pgbackrest")) / "dumps"
    dump_directory.mkdir(parents=True, exist_ok=True)
    rollback = dump_directory / f"hamqtt-store-before-recovery-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{job['id'][:8]}.dump"

    job["state"] = "recovering"
    job["started_at"] = _utcnow_text()
    job["rollback_dump"] = rollback.name
    save_job(job)
    _set_maintenance(job, "Creating and validating the rollback backup.")
    rollback_verified = False
    replacement_started = False
    try:
        _run(["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--dbname", database_url, "--file", str(rollback)])
        _run(["pg_restore", "--list", str(rollback)], timeout=300)
        rollback_verified = True
        _set_maintenance(job, "Replacing the database and applying migrations.")
        replacement_started = True
        job["restore_output"] = _replace_database(target, database_url, admin_url)
        job["state"] = "completed"
        job["completed_at"] = _utcnow_text()
        job["error"] = None
    except Exception as exc:
        job["error"] = str(exc)
        log.exception("Database recovery failed for job %s", job["id"])
        if replacement_started and rollback_verified and rollback.is_file():
            job["state"] = "rolling_back"
            save_job(job)
            _set_maintenance(job, "Recovery failed; restoring the verified rollback dump.")
            try:
                rollback_output = _replace_database(rollback, database_url, admin_url)
                job["restore_output"] = f"{job.get('restore_output') or ''}\nRollback:\n{rollback_output}".strip()
                job["state"] = "rolled_back"
            except Exception as rollback_exc:
                job["state"] = "failed"
                job["error"] = f"Recovery failed: {exc}; automatic rollback failed: {rollback_exc}"
                log.exception("Automatic rollback failed for job %s", job["id"])
        else:
            job["state"] = "failed"
        job["completed_at"] = _utcnow_text()
    finally:
        save_job(job)
        if job["state"] in {"completed", "rolled_back"} or not replacement_started:
            _clear_maintenance()
        else:
            _set_maintenance(
                job,
                "Recovery and automatic rollback failed. Keep services paused and follow docs/BACKUP_RECOVERY.md.",
            )
    return job


def run_scheduler() -> None:
    recovery_root().mkdir(parents=True, exist_ok=True)
    while True:
        try:
            jobs = list_jobs()
            uploaded = next((job for job in reversed(jobs) if job.get("state") == "uploaded"), None)
            requested = next((job for job in reversed(jobs) if job.get("state") == "recovery_requested"), None)
            if requested:
                recover_job(requested)
            elif uploaded:
                validate_job(uploaded)
        except Exception:
            log.exception("Recovery coordinator iteration failed")
        time.sleep(3)