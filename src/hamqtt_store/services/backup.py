"""Scheduled PostgreSQL backups using pgBackRest."""

import hashlib
import logging
import os
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select

from ..db import BackupRun, SessionLocal, SystemSetting, utcnow
from .recovery import wait_while_maintenance

log = logging.getLogger(__name__)

SETTING_KEY = "backup"
DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "local",
    "repository_subdirectory": "hamqtt",
    "schedule_profile": "low",
    "retention_profile": "medium",
    "portable_dump_daily": False,
    "encryption_passphrase": "",
}
SCHEDULE_PROFILES = {
    "low": {"full_interval_days": 7, "differential_interval_hours": 24},
    "medium": {"full_interval_days": 1, "differential_interval_hours": 6},
    "high": {"full_interval_days": 1, "differential_interval_hours": 1},
}
RETENTION_PROFILES = {"low": 2, "medium": 5, "high": 14}
SUPPORTED_PROVIDERS = {"local"}
FAILED_BACKUP_RETRY_DELAY = timedelta(minutes=15)
ACTIVE_BACKUP_STATUSES = {"queued", "running"}


def get_backup_config(session) -> dict:
    setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == SETTING_KEY))
    return normalize_config(setting.setting_value if setting and isinstance(setting.setting_value, dict) else {})


def normalize_config(values: dict) -> dict:
    config = dict(DEFAULT_CONFIG)
    config["enabled"] = bool(values.get("enabled", DEFAULT_CONFIG["enabled"]))
    config["provider"] = values.get("provider", "local") if values.get("provider") in SUPPORTED_PROVIDERS else "local"
    config["repository_subdirectory"] = (values.get("repository_subdirectory") or "hamqtt").strip().replace("\\", "/").strip("/") or "hamqtt"
    schedule_profile = values.get("schedule_profile")
    if schedule_profile not in SCHEDULE_PROFILES:
        legacy_schedule = (values.get("full_interval_days"), values.get("differential_interval_hours"))
        schedule_profile = {(7, 24): "low", (1, 6): "medium", (1, 1): "high"}.get(legacy_schedule, "low")
    retention_profile = values.get("retention_profile")
    if retention_profile not in RETENTION_PROFILES:
        try:
            legacy_count = int(values.get("retention_full_count", 4))
        except (TypeError, ValueError):
            legacy_count = 4
        retention_profile = "low" if legacy_count <= 2 else "medium" if legacy_count <= 5 else "high"
    config["schedule_profile"] = schedule_profile
    config["retention_profile"] = retention_profile
    dump_daily = values.get("portable_dump_daily", False)
    config["portable_dump_daily"] = dump_daily if isinstance(dump_daily, bool) else str(dump_daily).lower() in {"1", "true", "yes", "on"}
    config.update(SCHEDULE_PROFILES[schedule_profile])
    config["retention_count"] = RETENTION_PROFILES[retention_profile]
    config["encryption_passphrase"] = values.get("encryption_passphrase", "").strip()
    return config


def repository_path(config: dict) -> Path:
    root = Path(os.getenv("BACKUP_REPOSITORY_PATH", "/var/lib/pgbackrest"))
    return root / config["repository_subdirectory"]


def dump_path(config: dict) -> Path:
    return repository_path(config).parent / "dumps"


def list_portable_dumps(config: dict) -> list[dict]:
    """Return downloadable portable dumps without exposing repository internals."""
    directory = dump_path(config)
    if not directory.is_dir():
        return []
    dumps = []
    for path in directory.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".dump":
            continue
        stat = path.stat()
        dumps.append(
            {
                "name": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC),
            }
        )
    return sorted(dumps, key=lambda item: item["modified_at"], reverse=True)


def portable_dump_file(config: dict, filename: str) -> Path | None:
    """Resolve one direct-child .dump file, rejecting traversal and symlinks."""
    if not filename or filename != Path(filename).name or Path(filename).suffix.lower() != ".dump":
        return None
    directory = dump_path(config)
    candidate = directory / filename
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return None
        resolved_directory = directory.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved_candidate.parent != resolved_directory:
        return None
    return resolved_candidate


def _latest_completed(session, backup_type: str):
    return session.scalar(
        select(BackupRun)
        .where(BackupRun.backup_type == backup_type, BackupRun.status == "completed")
        .order_by(BackupRun.completed_at.desc())
    )


def _latest_attempt(session, backup_type: str):
    return session.scalar(
        select(BackupRun)
        .where(BackupRun.backup_type == backup_type)
        .order_by(BackupRun.started_at.desc())
    )


def _active_backup(session):
    return session.scalar(
        select(BackupRun)
        .where(BackupRun.status.in_(ACTIVE_BACKUP_STATUSES))
        .order_by(BackupRun.started_at.asc())
    )


def due_backup(
    config: dict,
    backup_type: str,
    now: datetime,
    latest: BackupRun | None,
    latest_attempt: BackupRun | None = None,
) -> bool:
    if latest is not None:
        reference = latest.completed_at or latest.started_at
        interval = timedelta(days=config["full_interval_days"] if backup_type == "full" else config["differential_interval_hours"] / 24)
        if now < reference + interval:
            return False
    if latest_attempt is not None:
        if latest_attempt.status in ACTIVE_BACKUP_STATUSES | {"requested"}:
            return False
        if latest_attempt.status == "failed":
            reference = latest_attempt.completed_at or latest_attempt.started_at
            if now < reference + FAILED_BACKUP_RETRY_DELAY:
                return False
    return True


def _pgbackrest_command(config: dict, backup_type: str) -> list[str]:
    command = ["pgbackrest", "--stanza=hamqtt", "--repo=1", "backup", f"--type={backup_type}"]
    command.append(f"--repo1-retention-full={config['retention_count']}")
    return command


def _dump_command(config: dict, target: Path) -> list[str]:
    database_url = os.getenv("DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+psycopg", "postgresql", 1))
    connection_url = urlunsplit(parsed)
    # Use numeric compression for compatibility with PostgreSQL 17 pg_dump.
    return ["pg_dump", "--format=custom", "--compress=6", "--no-owner", "--dbname", connection_url, "--file", str(target)]


def _cleanup_dumps(config: dict) -> None:
    files = sorted((path for path in dump_path(config).glob("*.dump") if path.is_file()), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[config["retention_count"]:]:
        path.unlink(missing_ok=True)


def _command_detail(result: subprocess.CompletedProcess, fallback: str) -> str:
    output = []
    for value in (result.stdout, result.stderr):
        value = (value or "").strip()
        if value and value not in output:
            output.append(value)
    return "\n".join(output) or fallback


def _ensure_stanza() -> None:
    version = subprocess.run(["pgbackrest", "version"], check=True, capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", version)
    if not match or (int(match.group(1)), int(match.group(2))) < (2, 58):
        raise RuntimeError(f"pgBackRest 2.58 or newer is required for PostgreSQL 17; found {version.strip()}")
    result = subprocess.run(
        ["pgbackrest", "--stanza=hamqtt", "stanza-create"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 25}:
        detail = _command_detail(result, "pgBackRest stanza-create failed")
        raise RuntimeError(f"pgBackRest stanza-create failed with exit status {result.returncode}: {detail}")


def run_backup(backup_type: str, triggered_by: str = "manual", run_id: int | None = None) -> BackupRun:
    with SessionLocal() as session:
        config = get_backup_config(session)
        run = session.get(BackupRun, run_id) if run_id else None
        if not run:
            run = BackupRun(backup_type=backup_type, status="running", triggered_by=triggered_by)
            session.add(run)
        else:
            run.status = "running"
        session.commit()
        session.refresh(run)
        run_id = run.id

    try:
        if config["provider"] != "local":
            raise RuntimeError(f"Backup provider '{config['provider']}' is reserved for a future storage adapter")
        if backup_type == "dump":
            target = dump_path(config)
            target.mkdir(parents=True, exist_ok=True)
            output = target / f"hamqtt-store-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.dump"
            result = subprocess.run(_dump_command(config, output), check=False, capture_output=True, text=True)
            if result.returncode == 0:
                _cleanup_dumps(config)
        else:
            target = repository_path(config)
            target.mkdir(parents=True, exist_ok=True)
            _ensure_stanza()
            result = subprocess.run(_pgbackrest_command(config, backup_type), check=False, capture_output=True, text=True)
        if result.returncode != 0:
            detail = _command_detail(result, "pgBackRest backup failed")
            tool = "pg_dump" if backup_type == "dump" else "pgBackRest"
            raise RuntimeError(f"{tool} backup failed with exit status {result.returncode}: {detail}")
        label = output.name if backup_type == "dump" else None
        if backup_type == "dump":
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            label = f"{output.name} sha256={digest}"
        with SessionLocal() as session:
            run = session.get(BackupRun, run_id)
            run.status = "completed"
            run.completed_at = utcnow()
            run.label = label
            run.size_bytes = output.stat().st_size if backup_type == "dump" else sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
            session.commit()
            return run
    except Exception as exc:
        log.exception("PostgreSQL %s backup failed", backup_type)
        with SessionLocal() as session:
            run = session.get(BackupRun, run_id)
            run.status = "failed"
            run.completed_at = utcnow()
            run.error_message = str(exc)
            session.commit()
            return run


def request_backup(backup_type: str) -> BackupRun:
    """Queue a manual backup for the dedicated backup service."""
    with SessionLocal() as session:
        run = BackupRun(backup_type=backup_type, status="requested", triggered_by="manual")
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


def _run_scheduled_backup(session, config: dict, now: datetime) -> bool:
    if _active_backup(session):
        return False
    latest_full = _latest_completed(session, "full")
    latest_diff = _latest_completed(session, "diff")
    latest_dump = _latest_completed(session, "dump")
    latest_full_attempt = _latest_attempt(session, "full")
    latest_diff_attempt = _latest_attempt(session, "diff")
    latest_dump_attempt = _latest_attempt(session, "dump")
    if due_backup(config, "full", now, latest_full, latest_full_attempt):
        run_backup("full", triggered_by="schedule")
        return True
    if due_backup(config, "diff", now, latest_diff, latest_diff_attempt):
        run_backup("diff", triggered_by="schedule")
        return True
    if config["portable_dump_daily"] and due_backup(
        {**config, "differential_interval_hours": 24},
        "dump",
        now,
        latest_dump,
        latest_dump_attempt,
    ):
        run_backup("dump", triggered_by="schedule")
        return True
    return False


def run_scheduler() -> None:
    while True:
        try:
            wait_while_maintenance()
            with SessionLocal() as session:
                config = get_backup_config(session)
                now = datetime.now(UTC)
                if config["enabled"] and config["provider"] == "local" and not _active_backup(session):
                    requested = session.scalar(
                        select(BackupRun)
                        .where(BackupRun.status == "requested")
                        .order_by(BackupRun.started_at.asc())
                    )
                    if requested:
                        requested.status = "queued"
                        session.commit()
                        run_backup(requested.backup_type, triggered_by=requested.triggered_by, run_id=requested.id)
                        continue
                    _run_scheduled_backup(session, config, now)
        except Exception:
            log.exception("Backup scheduler iteration failed")
        time.sleep(60)


def backup_repository_size(config: dict) -> int:
    path = repository_path(config)
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())