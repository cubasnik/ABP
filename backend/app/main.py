"""Точка входа сервера: запуск и останов, конфигурация из .env, журнал, метрики, маршруты.

Запуск: uvicorn app.main:app --host 0.0.0.0 --port 8000   (или python -m app)
Останов: Ctrl+C / SIGTERM — соединения закрываются, индекс и база остаются согласованными.
"""
from __future__ import annotations

import logging
import signal
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import get_settings
from .db import SessionLocal, init_db
from .ingest.loader import ingest_dir
from .logging_conf import setup_logging
from .metrics import metrics
from .routers import admin, ai, auth, docs, users
from .search.service import search_service

log = logging.getLogger("abp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging()
    log.info("запуск %s v%s (%s)", s.app_name, __version__, s.app_env)
    init_db()
    mode = search_service.connect()
    db = SessionLocal()
    try:
        n = search_service.warm(db)
        if n:
            log.info("поиск: в памяти %d документов", n)
        docs_dir = Path(s.docs_dir) if Path(s.docs_dir).is_absolute() else Path(__file__).resolve().parents[1] / s.docs_dir
        if docs_dir.exists():
            res = ingest_dir(db, docs_dir)
            log.info("документы из %s: %s", docs_dir, res)
    finally:
        db.close()
    log.info("готов: поиск=%s, ИИ=%s, порт %d", mode, s.ai_provider, s.port)
    _install_signal_logging()
    yield
    log.info("останов: освобождаю ресурсы")
    try:
        client = getattr(search_service.backend, "client", None)
        if client is not None:
            client.close()
    except Exception as e:  # noqa: BLE001
        log.debug("закрытие OpenSearch: %s", e)
    log.info("остановлен")


def _install_signal_logging() -> None:
    """Сигналы ОС: uvicorn сам останавливает сервер, мы лишь пишем это в журнал."""
    def handler(signum, _frame):  # noqa: ANN001
        log.warning("получен сигнал %s — завершаю работу", signal.Signals(signum).name)
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass   # не главный поток (тесты) — пропускаем


app = FastAPI(title="Обозреватель технической документации", version=__version__, lifespan=lifespan,
              docs_url="/api/docs-ui", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def observe(request: Request, call_next):
    """Метрики по маршрутам и режим обслуживания."""
    if admin.STATE["maintenance"] and not request.url.path.startswith(("/api/admin", "/api/auth", "/api/health")):
        return JSONResponse({"detail": "Идут регламентные работы — попробуйте позже"}, status_code=503)
    t0 = time.perf_counter()
    err = False
    try:
        resp = await call_next(request)
        err = resp.status_code >= 500
        return resp
    except Exception:
        err = True
        raise
    finally:
        route = request.scope.get("route")
        name = f"{request.method} {getattr(route, 'path', request.url.path)}"
        metrics.route(name, (time.perf_counter() - t0) * 1000, err)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("необработанная ошибка на %s: %s", request.url.path, exc)
    return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)


@app.get("/api/health", tags=["service"])
def health():
    return {"status": "ok", "version": __version__, "search": search_service.mode, "search_alive": search_service.backend.ping()}


for r in (auth.router, users.router, docs.router, ai.router, admin.router):
    app.include_router(r)
