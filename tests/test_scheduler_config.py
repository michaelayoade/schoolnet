from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from app.models.domain_settings import SettingDomain
from app.models.scheduler import ScheduleType
from app.services import scheduler_config


@pytest.fixture
def session_mock() -> MagicMock:
    return MagicMock(name="scheduler_session")


@pytest.fixture
def clear_scheduler_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = (
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "CELERY_TIMEZONE",
        "CELERY_BEAT_MAX_LOOP_INTERVAL",
        "CELERY_BEAT_REFRESH_SECONDS",
        "REDIS_URL",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def make_task():
    def _make_task(**overrides: object) -> SimpleNamespace:
        task = SimpleNamespace(
            id=uuid.uuid4(),
            task_name="app.tasks.sync",
            schedule_type=ScheduleType.interval,
            interval_seconds=60,
            args_json=["sample"],
            kwargs_json={"source": "seed"},
            enabled=True,
        )
        for field, value in overrides.items():
            setattr(task, field, value)
        return task

    return _make_task


def test_get_celery_config_uses_effective_values(
    session_mock: MagicMock, clear_scheduler_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fallback.example:6379/9")
    with (
        patch.object(scheduler_config, "SessionLocal", return_value=session_mock),
        patch.object(
            scheduler_config,
            "_effective_str",
            side_effect=[
                "redis://broker.example:6379/2",
                "redis://backend.example:6379/3",
                "Africa/Lagos",
            ],
        ) as effective_str_mock,
        patch.object(
            scheduler_config, "_effective_int", side_effect=[11, 45]
        ) as effective_int_mock,
    ):
        config = scheduler_config.get_celery_config()

    assert config["broker_url"] == "redis://broker.example:6379/2"
    assert config["result_backend"] == "redis://backend.example:6379/3"
    assert config["timezone"] == "Africa/Lagos"
    assert config["beat_max_loop_interval"] == 11
    assert config["beat_refresh_seconds"] == 45
    effective_str_mock.assert_has_calls(
        [
            call(
                session_mock,
                SettingDomain.scheduler,
                "broker_url",
                "CELERY_BROKER_URL",
                None,
            ),
            call(
                session_mock,
                SettingDomain.scheduler,
                "result_backend",
                "CELERY_RESULT_BACKEND",
                None,
            ),
            call(
                session_mock,
                SettingDomain.scheduler,
                "timezone",
                "CELERY_TIMEZONE",
                None,
            ),
        ]
    )
    effective_int_mock.assert_has_calls(
        [
            call(
                session_mock,
                SettingDomain.scheduler,
                "beat_max_loop_interval",
                "CELERY_BEAT_MAX_LOOP_INTERVAL",
                5,
            ),
            call(
                session_mock,
                SettingDomain.scheduler,
                "beat_refresh_seconds",
                "CELERY_BEAT_REFRESH_SECONDS",
                30,
            ),
        ]
    )
    session_mock.close.assert_called_once()


def test_get_celery_config_falls_back_to_redis(
    session_mock: MagicMock, clear_scheduler_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://shared.example:6379/5")
    with (
        patch.object(scheduler_config, "SessionLocal", return_value=session_mock),
        patch.object(
            scheduler_config, "_effective_str", side_effect=[None, None, None]
        ),
        patch.object(scheduler_config, "_effective_int", side_effect=[9, 77]),
    ):
        config = scheduler_config.get_celery_config()

    assert config == {
        "broker_url": "redis://shared.example:6379/5",
        "result_backend": "redis://shared.example:6379/5",
        "timezone": "UTC",
        "beat_max_loop_interval": 9,
        "beat_refresh_seconds": 77,
    }
    session_mock.close.assert_called_once()


def test_get_celery_config_uses_local_defaults_on_failure(
    session_mock: MagicMock, clear_scheduler_env: None
) -> None:
    with (
        patch.object(scheduler_config, "SessionLocal", return_value=session_mock),
        patch.object(
            scheduler_config, "_effective_str", side_effect=RuntimeError("boom")
        ),
        patch.object(scheduler_config.logger, "exception") as logger_mock,
    ):
        config = scheduler_config.get_celery_config()

    assert config == {
        "broker_url": "redis://localhost:6379/0",
        "result_backend": "redis://localhost:6379/1",
        "timezone": "UTC",
        "beat_max_loop_interval": 5,
        "beat_refresh_seconds": 30,
    }
    logger_mock.assert_called_once_with("Failed to load scheduler settings from database.")
    session_mock.close.assert_called_once()


def test_build_beat_schedule_builds_interval_entries(
    session_mock: MagicMock, make_task
) -> None:
    interval_task = make_task(
        task_name="app.tasks.sync_schools",
        interval_seconds=120,
        args_json=["a", "b"],
        kwargs_json={"dry_run": True},
    )
    zero_interval_task = make_task(
        task_name="app.tasks.ensure_min_interval",
        interval_seconds=0,
        args_json=None,
        kwargs_json=None,
    )
    non_interval_task = make_task(
        schedule_type="cron",
        task_name="app.tasks.cron_style",
    )
    query_mock = session_mock.query.return_value
    query_mock.filter.return_value.all.return_value = [
        interval_task,
        zero_interval_task,
        non_interval_task,
    ]

    with patch.object(scheduler_config, "SessionLocal", return_value=session_mock):
        schedule = scheduler_config.build_beat_schedule()

    first_key = f"scheduled_task_{interval_task.id}"
    second_key = f"scheduled_task_{zero_interval_task.id}"
    assert set(schedule.keys()) == {first_key, second_key}
    assert schedule[first_key]["task"] == "app.tasks.sync_schools"
    assert schedule[first_key]["schedule"] == timedelta(seconds=120)
    assert schedule[first_key]["args"] == ["a", "b"]
    assert schedule[first_key]["kwargs"] == {"dry_run": True}
    assert schedule[second_key]["schedule"] == timedelta(seconds=1)
    assert schedule[second_key]["args"] == []
    assert schedule[second_key]["kwargs"] == {}
    session_mock.close.assert_called_once()


def test_build_beat_schedule_returns_empty_on_exception(session_mock: MagicMock) -> None:
    session_mock.query.side_effect = RuntimeError("db down")
    with (
        patch.object(scheduler_config, "SessionLocal", return_value=session_mock),
        patch.object(scheduler_config.logger, "exception") as logger_mock,
    ):
        schedule = scheduler_config.build_beat_schedule()

    assert schedule == {}
    logger_mock.assert_called_once_with("Failed to build Celery beat schedule.")
    session_mock.close.assert_called_once()
