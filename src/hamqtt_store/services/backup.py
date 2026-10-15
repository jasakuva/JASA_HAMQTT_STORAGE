"""Scheduled PostgreSQL backups using pgBackRest."""

import logging
import os
import re
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from ..db import BackupRun, SessionLocal, SystemSetting, utcnow

log = logging.getLogger(__name__)

SETTING_KEY = "backup"
DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "local",
    "repository_subdirectory": "hamqtt",
    "full_interval_days": 7,
    "differential_interval_hours": 24,
    "retention_full_count": 4,
    "retention_diff_count": 14,
    "encryption_passphrase": "",
}
SUPPORTED_PROVIDERS = {"local", "s3", "sftp", "rclone"}


def get_backup_config(session) -> dict:
    setting = session.scalar(select(SystemSetting).where(SystemSetting.setting_key == SETTING_KEY))
    config = dict(DEFAULT_CONFIG)
    if setting and isinstance(setting.setting_value, dict):
        config.update(setting.setting_value)
    return config


def normalize_config(values: dict) -> dict:
    config = dict(DEFAULT_CONFIG)
    config["enabled"] = bool(values.get("enabled"))
    config["provider"] = values.get("provider", "local") if values.get("provider") in SUPPORTED_PROVIDERS else "local"
    config["repository_subdirectory"] = (values.get("repository_subdirectory") or "hamqtt").strip().replace("\\", "/").strip("/") or "hamqtt"
    for key, minimum, maximum in (
        ("full_interval_days", 1, 3650),
        ("differential_interval_hours", 1, 720),
        ("retention_full_count", 1, 100),
        ("retention_diff_count", 0, 1000),
    ):
        try:
            value = int(values.get(key, DEFAULT_CONFIG[key]))
        except (TypeError, ValueError):
            value = DEFAULT_CONFIG[key]
        config[key] = max(minimum, min(value, maximum))
    config["encryption_passphrase"] = values.get("encryption_passphrase", "").strip()
    return config


def repository_path(config: dict) -> Path:
    root = Path(os.getenv("BACKUP_REPOSITORY_PATH", "/var/lib/pgbackrest"))
    return root / config["repository_subdirectory"]


def _latest_completed(session, backup_type: str):
    return session.scalar(
        select(BackupRun)
        .where(BackupRun.backup_type == backup_type, BackupRun.status == "completed")
        .order_by(BackupRun.completed_at.desc())
    )


def due_backup(config: dict, backup_type: str, now: datetime, latest: BackupRun | None) -> bool:
    if latest is None:
        return True
    reference = latest.completed_at or latest.started_at
    interval = timedelta(days=config["full_interval_days"] if backup_type == "full" else config["differential_interval_hours"] / 24)
    return now >= reference + interval


def _pgbackrest_command(config: dict, backup_type: str) -> list[str]:
    command = ["pgbackrest", "--stanza=hamqtt", "--repo=1", "backup", f"--type={backup_type}"]
    command.append(f"--repo1-retention-full={config['retention_full_count']}")
    if config["retention_diff_count"]:
        command.append(f"--repo1-retention-diff={config['retention_diff_count']}")
    return command


def _ensure_stanza() -> None:
    version = subprocess.run(["pgbackrest", "version"], check=True, capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", version)
    if not match or (int(match.group(1)), int(match.group(2))) < (2, 58):
        raise RuntimeError(f"pgBackRest 2.58 or newer is required for PostgreSQL 17; found {version.strip()}")
    result = subprocess.run(
        ["pgbackrest", "--stanza=hamqtt", "stanza-create"],
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 25}:
        detail = (result.stderr or result.stdout or "pgBackRest stanza-create failed").strip()
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
        target = repository_path(config)
        target.mkdir(parents=True, exist_ok=True)
        _ensure_stanza()
        result = subprocess.run(_pgbackrest_command(config, backup_type), check=False, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "pgBackRest backup failed").strip()
            raise RuntimeError(f"pgBackRest backup failed with exit status {result.returncode}: {detail}")
        label = None
        with SessionLocal() as session:
            run = session.get(BackupRun, run_id)
            run.status = "completed"
            run.completed_at = utcnow()
            run.label = label
            run.size_bytes = sum(path.stat().st_size for path in target.rglob("*") if path.is_file())
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
        active = session.scalar(
            select(BackupRun).where(BackupRun.status.in_(["requested", "running"])).order_by(BackupRun.started_at.desc())
        )
        if active:
            return active
        run = BackupRun(backup_type=backup_type, status="requested", triggered_by="manual")
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


def run_scheduler() -> None:
    while True:
        try:
            with SessionLocal() as session:
                config = get_backup_config(session)
                now = datetime.now(UTC)
                if config["enabled"] and config["provider"] == "local":
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
                    latest_full = _latest_completed(session, "full")
                    latest_diff = _latest_completed(session, "diff")
                    if due_backup(config, "full", now, latest_full):
                        run_backup("full")
                    elif due_backup(config, "diff", now, latest_diff):
                        run_backup("diff")
        except Exception:
            log.exception("Backup scheduler iteration failed")
        time.sleep(60)


def backup_repository_size(config: dict) -> int:
    path = repository_path(config)
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())