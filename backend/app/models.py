"""Таблицы базы данных: пользователи, коды входа, документы, аудит, журнал ИИ."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="user")          # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sms_required: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SmsCode(Base):
    """Одноразовый код подтверждения входа по СМС."""
    __tablename__ = "sms_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(8))
    ticket: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    tries: Mapped[int] = mapped_column(Integer, default=0)


class QrLogin(Base):
    """Вход по QR-коду: сеанс ждёт подтверждения с уже вошедшего устройства."""
    __tablename__ = "qr_logins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Document(Base):
    """Документ технической документации с метаданными и разделами."""
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)           # sha256(path + release)
    path: Mapped[str] = mapped_column(String(512), index=True)
    title: Mapped[str] = mapped_column(String(300))
    product: Mapped[str] = mapped_column(String(100), default="", index=True)
    vendor: Mapped[str] = mapped_column(String(100), default="", index=True)
    domain: Mapped[str] = mapped_column(String(100), default="", index=True)
    release: Mapped[str] = mapped_column(String(50), default="", index=True)
    node_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    interface: Mapped[str] = mapped_column(String(100), default="", index=True)
    protocol: Mapped[str] = mapped_column(String(100), default="", index=True)
    topic: Mapped[str] = mapped_column(String(200), default="", index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    sections_json: Mapped[str] = mapped_column(Text, default="[]")         # [{anchor, title, text}]
    content_sha: Mapped[str] = mapped_column(String(64), default="")
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditLog(Base):
    """Журнал административных и пользовательских действий."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(300), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")


class AiLog(Base):
    """Журнал ответов искусственного интеллекта и обратной связи по ним."""
    __tablename__ = "ai_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    mode: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    feedback: Mapped[str] = mapped_column(String(8), default="")               # like | dislike
