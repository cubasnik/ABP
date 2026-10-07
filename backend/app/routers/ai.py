"""Ассистент: вопрос → ответ с источниками; обратная связь; журнал ответов."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.assistant import ask
from ..audit import audit
from ..db import get_db
from ..deps import admin_user, client_ip, current_user
from ..models import AiLog, User
from ..schemas import AskIn, AskOut, FeedbackIn

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/ask", response_model=AskOut)
def ask_route(body: AskIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    filters = {k: v for k, v in {"release": body.release, "product": body.product, "domain": body.domain}.items() if v}
    return ask(db, user.username, body.question.strip(), body.mode, filters)


@router.post("/feedback")
def feedback(body: FeedbackIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.get(AiLog, body.answer_id)
    if not row or row.username != user.username:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ответ не найден")
    row.feedback = body.value
    db.commit()
    audit(db, user.username, "ai.feedback", str(row.id), {"value": body.value}, client_ip(request))
    return {"ok": True}


@router.get("/history")
def history(limit: int = Query(default=20, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AiLog).where(AiLog.username == user.username).order_by(AiLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "ts": r.ts, "mode": r.mode, "question": r.question, "blocked": r.blocked,
             "confidence": r.confidence, "feedback": r.feedback} for r in rows]


@router.get("/log")
def ai_log(limit: int = Query(default=100, ge=1, le=1000), _: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AiLog).order_by(AiLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "ts": r.ts, "username": r.username, "mode": r.mode, "question": r.question, "answer": r.answer,
             "blocked": r.blocked, "confidence": r.confidence, "latency_ms": r.latency_ms, "feedback": r.feedback} for r in rows]
