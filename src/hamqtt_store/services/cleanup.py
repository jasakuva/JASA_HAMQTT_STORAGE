"""Scheduled retention cleanup for diagnostic and historical data."""

import logging
import os
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from ..db import (
    ApplicationLog,
    HAStateHistory,
    MQTTMessage,
    SessionLocal,
    SystemSetting,
)
from .recovery import wait_while_maintenance

log = logging.getLogger(__name__)

DEFAULT_HISTORY_DAYS = 365
MIN_HISTORY_DAYS = 1
MAX_HISTORY_DAYS = 3650
DEFAULT_CLEANUP_HOUR_UTC = 2
DEFAULT_CLEANUP_MINUTE_UTC = 0


def history_retention_days(value) -> int:
    """Return a safe history retention value in the supported range."""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HISTORY_DAYS
    return max(MIN_HISTORY_DAYS, min(days, MAX_HISTORY_DAYS))


def get_history_retention_days(session) -> int:
    setting = session.scalar(
        select(SystemSetting).where(SystemSetting.setting_key == "retention")
    )
    value = setting.setting_value if setting else {}
    return history_retention_days((value or {}).get("history_days"))


def run_cleanup(now: datetime | None = None) -> dict[str, int]:
    """Delete expired logs and historical rows, returning direct delete counts."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    with SessionLocal() as session:
        history_days = get_history_retention_days(session)
        log_cutoff = now - timedelta(days=3)
        error_log_cutoff = now - timedelta(days=7)
        history_cutoff = now - timedelta(days=history_days)

        log_result = session.execute(
            delete(ApplicationLog).where(
                ((ApplicationLog.level.in_(["ERROR", "CRITICAL"])) &
                 (ApplicationLog.created_at < error_log_cutoff)) |
                ((~ApplicationLog.level.in_(["ERROR", "CRITICAL"])) &
                 (ApplicationLog.created_at < log_cutoff))
            )
        )
        ha_result = session.execute(
            delete(HAStateHistory).where(HAStateHistory.observed_at < history_cutoff)
        )
        mqtt_result = session.execute(
            delete(MQTTMessage).where(MQTTMessage.received_at < history_cutoff)
        )
        session.commit()

    result = {
        "application_logs_deleted": log_result.rowcount or 0,
        "ha_state_history_deleted": ha_result.rowcount or 0,
        "mqtt_messages_deleted": mqtt_result.rowcount or 0,
        "history_days": history_days,
    }
    log.info("Retention cleanup completed: %s", result)
    return result


def _next_cleanup_at(now: datetime, hour: int, minute: int) -> datetime:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def run_scheduler() -> None:
    """Run retention cleanup once per night at the configured UTC time."""
    try:
        hour = max(0, min(int(os.getenv("CLEANUP_HOUR_UTC", DEFAULT_CLEANUP_HOUR_UTC)), 23))
    except ValueError:
        hour = DEFAULT_CLEANUP_HOUR_UTC
    try:
        minute = max(0, min(int(os.getenv("CLEANUP_MINUTE_UTC", DEFAULT_CLEANUP_MINUTE_UTC)), 59))
    except ValueError:
        minute = DEFAULT_CLEANUP_MINUTE_UTC

    while True:
        now = datetime.now(UTC)
        next_run = _next_cleanup_at(now, hour, minute)
        delay = max(1, (next_run - now).total_seconds())
        log.info("Next retention cleanup scheduled for %s", next_run.isoformat())
        time.sleep(delay)
        try:
            wait_while_maintenance()
            run_cleanup()
        except Exception:
            log.exception("Retention cleanup failed")