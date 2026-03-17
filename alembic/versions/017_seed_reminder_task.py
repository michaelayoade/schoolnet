"""Seed ScheduledTask for daily admissions reminders.

Revision ID: 015_seed_admissions_reminder_task
Revises: 014_proximity_and_exam_checklist
Create Date: 2026-03-17
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "017_seed_reminder_task"
down_revision = "016_proximity_checklist"
branch_labels = None
depends_on = None

TASK_NAME = "app.tasks.admissions_reminders.send_daily_admissions_reminders_task"


def upgrade() -> None:
    conn = op.get_bind()
    # Only insert if not already present
    existing = conn.execute(
        sa.text("SELECT id FROM scheduled_tasks WHERE task_name = :tn"),
        {"tn": TASK_NAME},
    ).fetchone()
    if existing:
        return

    conn.execute(
        sa.text(
            "INSERT INTO scheduled_tasks "
            "(id, name, task_name, schedule_type, interval_seconds, enabled, "
            " created_at, updated_at) "
            "VALUES (:id, :name, :task_name, :schedule_type, :interval_seconds, "
            " :enabled, now(), now())"
        ),
        {
            "id": str(uuid.uuid4()),
            "name": "Daily Admissions Reminders",
            "task_name": TASK_NAME,
            "schedule_type": "interval",
            "interval_seconds": 86400,
            "enabled": True,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM scheduled_tasks WHERE task_name = :tn"),
        {"tn": TASK_NAME},
    )
