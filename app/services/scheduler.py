import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.scheduler import ScheduledTask, ScheduleType
from app.schemas.scheduler import ScheduledTaskCreate, ScheduledTaskUpdate
from app.services.common import coerce_uuid
from app.services.response import ListResponseMixin

logger = logging.getLogger(__name__)


class ScheduledTaskNotFoundError(ValueError):
    pass


class TaskEnqueueError(RuntimeError):
    pass


def _validate_schedule_type(value):
    if value is None:
        return None
    if isinstance(value, ScheduleType):
        return value
    try:
        return ScheduleType(value)
    except ValueError as exc:
        raise ValueError("Invalid schedule_type") from exc


class ScheduledTasks(ListResponseMixin):
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _apply_ordering(stmt, order_by: str, order_dir: str):
        allowed_columns = {
            "created_at": ScheduledTask.created_at,
            "name": ScheduledTask.name,
        }
        column = allowed_columns.get(order_by)
        if column is None:
            raise ValueError(
                f"Invalid order_by. Allowed: {', '.join(sorted(allowed_columns))}"
            )
        if order_dir == "desc":
            return stmt.order_by(column.desc())
        return stmt.order_by(column.asc())

    def create(self, payload: ScheduledTaskCreate):
        if payload.interval_seconds < 1:
            raise ValueError("interval_seconds must be >= 1")
        task = ScheduledTask(**payload.model_dump())
        self.db.add(task)
        self.db.flush()
        self.db.refresh(task)
        return task

    def get(self, task_id: str):
        task = self.db.get(ScheduledTask, coerce_uuid(task_id))
        if not task:
            raise ScheduledTaskNotFoundError("Scheduled task not found")
        return task

    def list(
        self,
        enabled: bool | None,
        order_by: str,
        order_dir: str,
        limit: int,
        offset: int,
    ):
        stmt = select(ScheduledTask)
        if enabled is not None:
            stmt = stmt.where(ScheduledTask.enabled == enabled)

        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = self.db.scalar(count_stmt) or 0

        stmt = ScheduledTasks._apply_ordering(stmt, order_by, order_dir)
        stmt = stmt.limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).all())
        return items, total

    def update(self, task_id: str, payload: ScheduledTaskUpdate):
        task = self.db.get(ScheduledTask, coerce_uuid(task_id))
        if not task:
            raise ScheduledTaskNotFoundError("Scheduled task not found")
        data = payload.model_dump(exclude_unset=True)
        if "schedule_type" in data:
            data["schedule_type"] = _validate_schedule_type(data["schedule_type"])
        if "interval_seconds" in data and data["interval_seconds"] is not None:
            if data["interval_seconds"] < 1:
                raise ValueError("interval_seconds must be >= 1")
        for key, value in data.items():
            setattr(task, key, value)
        self.db.flush()
        self.db.refresh(task)
        return task

    def delete(self, task_id: str):
        task = self.db.get(ScheduledTask, coerce_uuid(task_id))
        if not task:
            raise ScheduledTaskNotFoundError("Scheduled task not found")
        self.db.delete(task)
        self.db.flush()


def refresh_schedule() -> dict:
    return {"detail": "Celery beat refreshes schedules automatically."}


def enqueue_task(task_name: str, args: list | None, kwargs: dict | None) -> dict:
    from app.celery_app import celery_app

    try:
        async_result = celery_app.send_task(
            task_name,
            args=args or [],
            kwargs=kwargs or {},
            retry=False,
            ignore_result=True,
        )
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        raise TaskEnqueueError("Failed to enqueue task") from exc

    return {"queued": True, "task_id": str(async_result.id)}
