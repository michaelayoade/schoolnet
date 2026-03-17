import time
from typing import Any, cast

from celery.beat import ScheduleEntry, Scheduler

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
        raw_schedule = build_beat_schedule()
        # Convert raw dicts to ScheduleEntry objects that Celery expects.
        new_schedule: dict[str, Any] = {}
        for name, entry_dict in raw_schedule.items():
            if name in self.schedule and isinstance(self.schedule[name], ScheduleEntry):
                # Update existing entry in-place to preserve runtime state
                existing = self.schedule[name]
                existing.task = entry_dict["task"]
                existing.schedule = entry_dict["schedule"]
                existing.args = tuple(entry_dict.get("args", ()))
                existing.kwargs = entry_dict.get("kwargs", {})
                new_schedule[name] = existing
            else:
                new_schedule[name] = self.Entry(
                    name=name,
                    task=entry_dict["task"],
                    schedule=entry_dict["schedule"],
                    args=tuple(entry_dict.get("args", ())),
                    kwargs=entry_dict.get("kwargs", {}),
                    app=self.app,
                )
        self.schedule = new_schedule
        self._last_refresh_at = now
