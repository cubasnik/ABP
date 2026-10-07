"""Журнал событий: консоль и файл с ротацией. Формат единый для всех модулей."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import get_settings

FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging() -> logging.Logger:
    """Настроить корневой журнал один раз; повторный вызов безопасен."""
    s = get_settings()
    root = logging.getLogger()
    if getattr(root, "_abp_configured", False):
        return root
    root.setLevel(getattr(logging, s.log_level.upper(), logging.INFO))
    fmt = logging.Formatter(FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    if s.log_file:
        path = Path(s.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    root._abp_configured = True  # type: ignore[attr-defined]
    return root
