"""
celery_app.py — Celery application instance.
Run worker:  celery -A celery_app worker --loglevel=info
Run beat:    celery -A celery_app beat --loglevel=info
Run flower:  celery -A celery_app flower --port=5555
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "trading_engine",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.backtest_tasks",
        "app.tasks.portfolio_backtest_tasks",
        "app.tasks.live_trading_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_track_started=True,
    # Long-running live trading: keep tasks alive
    task_time_limit=None,             # no hard kill (live loop is supervised)
    task_soft_time_limit=None,
    worker_prefetch_multiplier=1,     # don't prefetch — long-running tasks
    worker_max_tasks_per_child=20,    # recycle workers periodically
    task_acks_late=True,              # ack only after task body completes
    task_reject_on_worker_lost=True,  # re-queue if worker dies
    result_expires=60 * 60 * 24,      # results kept 24h
    broker_connection_retry_on_startup=True,
)


# Auto-discover any tasks defined under app.tasks
celery_app.autodiscover_tasks(["app.tasks"])
