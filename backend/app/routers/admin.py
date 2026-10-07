"""Мониторинг и управление: состояние, метрики, панели, узкие места, аудит, переиндексация, останов."""
from __future__ import annotations

import logging
import os
import signal
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user, client_ip
from ..metrics import metrics
from ..models import AiLog, AuditLog, Document, User
from ..search.service import search_service

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger("abp.admin")
STATE = {"maintenance": False, "started": datetime.utcnow()}


@router.get("/status")
def status_route(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    s = get_settings()
    return {"version": __version__, "env": s.app_env, "started": STATE["started"], "maintenance": STATE["maintenance"],
            "search_backend": search_service.mode, "search_alive": search_service.backend.ping(),
            "documents": db.scalar(select(func.count(Document.id))) or 0, "chunks_indexed": search_service.backend.count(),
            "users": db.scalar(select(func.count(User.id))) or 0, "ai_provider": s.ai_provider,
            "strict_citations": s.ai_strict_citations}


@router.get("/metrics")
def metrics_route(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    snap = metrics.snapshot()
    search_stats = snap["stages"].get(f"search.{search_service.mode}", {})
    return {"documents": db.scalar(select(func.count(Document.id))) or 0, "search_latency_ms": search_stats,
            "ai_answers": db.scalar(select(func.count(AiLog.id))) or 0,
            "ai_blocked": db.scalar(select(func.count(AiLog.id)).where(AiLog.blocked.is_(True))) or 0, **snap}


@router.get("/monitoring")
def monitoring(_: User = Depends(admin_user)):
    """Панели: ошибки, задержки, пропускная способность — по маршрутам."""
    snap = metrics.snapshot()
    panels = {"errors": {k: v["errors"] for k, v in snap["routes"].items()},
              "latency_p95_ms": {k: v["p95_ms"] for k, v in snap["routes"].items()},
              "throughput_per_min": {k: v["per_minute"] for k, v in snap["routes"].items()}}
    return {"uptime_s": snap["uptime_s"], "requests": snap["requests"], "errors": snap["errors"], "panels": panels}


@router.get("/bottlenecks")
def bottlenecks(_: User = Depends(admin_user)):
    return metrics.snapshot()["bottlenecks"]


@router.get("/audit")
def audit_list(limit: int = Query(default=200, ge=1, le=2000), username: str = "", action: str = "",
               _: User = Depends(admin_user), db: Session = Depends(get_db)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if username:
        q = q.where(AuditLog.username == username)
    if action:
        q = q.where(AuditLog.action == action)
    return [{"id": r.id, "ts": r.ts, "username": r.username, "action": r.action, "target": r.target, "details": r.details, "ip": r.ip}
            for r in db.scalars(q)]


@router.post("/reindex")
def reindex(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    with metrics.timer("admin.reindex"):
        n = search_service.reindex_all(db)
    audit(db, admin.username, "admin.reindex", "", {"documents": n}, client_ip(request))
    return {"reindexed": n, "backend": search_service.mode}


@router.post("/maintenance")
def maintenance(request: Request, on: bool = True, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    STATE["maintenance"] = on
    audit(db, admin.username, "admin.maintenance", "", {"on": on}, client_ip(request))
    return {"maintenance": on}


@router.post("/shutdown")
def shutdown(request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Корректный останов: процесс получает SIGINT/SIGTERM и завершает обработчики."""
    audit(db, admin.username, "admin.shutdown", "", {}, client_ip(request))
    log.warning("останов по команде администратора %s", admin.username)
    sig = signal.SIGINT if os.name == "nt" else signal.SIGTERM
    threading.Timer(0.5, lambda: os.kill(os.getpid(), sig)).start()
    return {"stopping": True}
