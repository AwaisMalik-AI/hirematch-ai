"""Celery application (broker/backend from settings)."""

from celery import Celery

from app.core.config import get_settings


def _build_celery() -> Celery:
    s = get_settings()
    app = Celery(
        "hirematch",
        broker=str(s.celery_broker_url),
        backend=str(s.celery_result_backend),
        include=["app.tasks.processing_tasks"],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=60 * 30,
    )
    return app


celery_app = _build_celery()
