# ============================================================================
# celery_app.py — Celery application instance
# Defined at backend/ root so `celery -A celery_app worker` works
# (Full task registration happens in Step 5)
# ============================================================================
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "trading_engine",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],  # tasks package will be created in Step 5
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_track_started=True,
    task_time_limit=60 * 60,         # hard kill at 1h
    task_soft_time_limit=55 * 60,    # soft warning at 55min
    worker_prefetch_multiplier=1,    # long-running tasks: don't prefetch
    worker_max_tasks_per_child=50,   # recycle workers to release memory
)
