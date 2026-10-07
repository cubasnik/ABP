"""Загрузка папки документов из командной строки (без запуска сервера).

Использование:  python scripts/ingest.py [папка]   (по умолчанию DOCS_DIR из .env)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.ingest.loader import ingest_dir  # noqa: E402
from app.logging_conf import setup_logging  # noqa: E402
from app.search.service import search_service  # noqa: E402


def main() -> int:
    setup_logging()
    init_db()
    mode = search_service.connect()
    folder = sys.argv[1] if len(sys.argv) > 1 else get_settings().docs_dir
    db = SessionLocal()
    try:
        search_service.warm(db)
        res = ingest_dir(db, folder)
    finally:
        db.close()
    print(f"поиск: {mode}; папка {folder}: {res}")
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
