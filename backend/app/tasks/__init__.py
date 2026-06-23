"""
app.tasks
---------
Celery task package. Importing this module registers all tasks with celery_app.

Run worker with:
    celery -A celery_app worker --loglevel=info
"""
from app.tasks.backtest_tasks import task_run_backtest
from app.tasks.live_trading_tasks import task_start_live_trading, task_stop_trading

__all__ = ["task_run_backtest", "task_start_live_trading", "task_stop_trading"]
