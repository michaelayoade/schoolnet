import time
from typing import Any, cast

from celery.beat import Scheduler

from app.services.scheduler_config import build_beat_schedule


class DbScheduler(Scheduler):
    schedule: dict[str, Any]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_refresh_at = 0.0
        # Celery's stubs are incomplete; normalize to a plain mapping for our use.
        self.schedule = cast(dict[str, Any], getattr(self, "schedule", {}))

    def setup_schedule(self) -> None:
        self._refresh_schedule()

    def tick(self) -> float:
        self._refresh_schedule()
        return cast(float, super().tick())

    def _refresh_schedule(self) -> None:
        refresh_seconds = int(self.app.conf.get("beat_refresh_seconds", 30))
        now = time.monotonic()
        if now - self._last_refresh_at < max(refresh_seconds, 1):
            return
        schedule = build_beat_schedule()
        if schedule != self.schedule:
            self.schedule = schedule
        self._last_refresh_at = now
