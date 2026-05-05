"""Настройка корневого логирования приложения."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import LogConfig


def setup_logging(config: LogConfig) -> None:
    """Инициализирует логирование в файл и stdout с ротацией."""
    Path(config.log_dir).mkdir(parents=True, exist_ok=True)
    log_path = Path(config.log_dir) / config.log_name
    log_level = logging.DEBUG if config.loglevel == "debug" else logging.INFO

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=config.max_log_size,
        backupCount=config.max_log_files,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

