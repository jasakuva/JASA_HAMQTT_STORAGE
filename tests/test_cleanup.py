from datetime import UTC, datetime, timedelta

from hamqtt_store.services.cleanup import (
    DEFAULT_HISTORY_DAYS,
    _next_cleanup_at,
    history_retention_days,
)


def test_history_retention_defaults_and_clamps():
    assert history_retention_days(None) == DEFAULT_HISTORY_DAYS
    assert history_retention_days("invalid") == DEFAULT_HISTORY_DAYS
    assert history_retention_days(0) == 1
    assert history_retention_days(99999) == 3650


def test_next_cleanup_is_next_day_after_scheduled_time():
    now = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)
    result = _next_cleanup_at(now, 2, 0)
    assert result == now.replace(hour=2) + timedelta(days=1)


def test_next_cleanup_is_same_day_before_scheduled_time():
    now = datetime(2026, 10, 11, 1, 30, tzinfo=UTC)
    result = _next_cleanup_at(now, 2, 0)
    assert result == now.replace(hour=2, minute=0)