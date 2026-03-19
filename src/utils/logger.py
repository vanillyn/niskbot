from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_log_dir = Path("logs")
_fmt = logging.Formatter(
    fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _make_handler_file(name: str) -> TimedRotatingFileHandler:
    _log_dir.mkdir(exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=_log_dir / f"{name}.log",
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    handler.setFormatter(_fmt)
    return handler


def _make_handler_console() -> logging.StreamHandler[object]:
    handler: logging.StreamHandler[object] = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_fmt)
    return handler


def get_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    logger.addHandler(_make_handler_console())
    logger.addHandler(_make_handler_file(name))
    logger.propagate = False
    return logger


def setup_discord_logging(*, level: int = logging.WARNING) -> None:
    discord_log = logging.getLogger("discord")
    if discord_log.handlers:
        return
    discord_log.setLevel(level)
    discord_log.addHandler(_make_handler_console())
    discord_log.addHandler(_make_handler_file("discord"))
    discord_log.propagate = False
