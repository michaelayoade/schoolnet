from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role
from app.schemas.common import ListResponse
from app.schemas.scheduler import (
    ScheduledTaskCreate,
    ScheduledTaskRead,
    ScheduledTaskUpdate,
)
from app.services import scheduler as scheduler_service

router = APIRouter(prefix="/scheduler", tags=["scheduler"], dependencies=[Depends(require_role("admin"))])


@router.get("/tasks", response_model=ListResponse[ScheduledTaskRead])
def list_scheduled_tasks(
    enabled: bool | None = None,
    order_by: str = Query(default="created_at"),
    order_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        return scheduler_service.scheduled_tasks.list_response(
            db, enabled, order_by, order_dir, limit, offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/tasks",
    response_model=ScheduledTaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scheduled_task(payload: ScheduledTaskCreate, db: Session = Depends(get_db)):
    try:
        task = scheduler_service.scheduled_tasks.create(db, payload)
        db.commit()
        return task
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=ScheduledTaskRead)
def get_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    try:
        return scheduler_service.scheduled_tasks.get(db, task_id)
    except scheduler_service.ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}", response_model=ScheduledTaskRead)
def update_scheduled_task(
    task_id: str, payload: ScheduledTaskUpdate, db: Session = Depends(get_db)
):
    try:
        task = scheduler_service.scheduled_tasks.update(db, task_id, payload)
        db.commit()
        return task
    except scheduler_service.ScheduledTaskNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    try:
        scheduler_service.scheduled_tasks.delete(db, task_id)
        db.commit()
    except scheduler_service.ScheduledTaskNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/refresh", status_code=status.HTTP_200_OK)
def refresh_schedule():
    return scheduler_service.refresh_schedule()


@router.post("/tasks/{task_id}/enqueue", status_code=status.HTTP_202_ACCEPTED)
def enqueue_scheduled_task(task_id: str, db: Session = Depends(get_db)):
    try:
        task = scheduler_service.scheduled_tasks.get(db, task_id)
    except scheduler_service.ScheduledTaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return scheduler_service.enqueue_task(
            task.task_name, task.args_json or [], task.kwargs_json or {}
        )
    except scheduler_service.TaskEnqueueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
