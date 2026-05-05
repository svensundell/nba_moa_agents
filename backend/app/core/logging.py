"""Loguru setup — JSON-friendly logs with optional pretty colorisation."""

from __future__ import annotations

import sys

from loguru import logger

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        backtrace=False,
        diagnose=False,
        enqueue=False,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "| <level>{level:<8}</level> "
            "| <cyan>{extra[agent]:<10}</cyan> "
            "| <level>{message}</level>"
        ),
    )
    logger.configure(extra={"agent": "-"})


def agent_logger(name: str):
    """Return a logger bound to a specific agent name (shows up in the prefix)."""
    return logger.bind(agent=name)
