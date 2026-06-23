"""
app.core.logging
----------------
Loguru-based structured logger. Replaces stdlib logging globally.
"""
import logging
import sys

from loguru import logger

from app.core.config import settings


class InterceptHandler(logging.Handler):
    """Intercepts stdlib logging and forwards to loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    """Configure loguru sinks and intercept stdlib loggers (uvicorn, sqlalchemy)."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        colorize=True,
        backtrace=True,
        diagnose=(settings.APP_ENV == "development"),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # Also persist to file
    logger.add(
        "logs/trading_{time:YYYYMMDD}.log",
        rotation="00:00",
        retention="14 days",
        compression="zip",
        level=settings.LOG_LEVEL,
        enqueue=True,  # thread-safe
    )

    # Intercept stdlib
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine", "celery"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
