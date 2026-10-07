"""Схемы запросов и ответов REST API (Pydantic)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""
    phone: str = ""


class LoginIn(BaseModel):
    username: str
    password: str


class SmsConfirmIn(BaseModel):
    ticket: str
    code: str


class QrConfirmIn(BaseModel):
    token: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in_minutes: int


class LoginOut(BaseModel):
    """Либо сразу билет, либо запрос кода из СМС."""
    status: str                                  # ok | sms_required
    token: TokenOut | None = None
    ticket: str | None = None
    phone_hint: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    phone: str
    role: str
    is_active: bool
    sms_required: bool
    locked_until: datetime | None
    created_at: datetime
    last_login_at: datetime | None


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = ""
    phone: str = ""
    role: str = "user"
    sms_required: bool = False


class UserUpdateIn(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    role: str | None = None
    is_active: bool | None = None
    sms_required: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    unlock: bool | None = None


class SearchHit(BaseModel):
    id: str
    title: str
    path: str
    product: str
    vendor: str
    domain: str
    release: str
    node_type: str
    interface: str
    protocol: str
    topic: str
    score: float
    snippet: str
    anchor: str = ""


class SearchOut(BaseModel):
    total: int
    took_ms: int
    backend: str
    hits: list[SearchHit]
    facets: dict[str, dict[str, int]]


class Section(BaseModel):
    anchor: str
    title: str
    text: str


class DocumentOut(BaseModel):
    id: str
    path: str
    title: str
    product: str
    vendor: str
    domain: str
    release: str
    node_type: str
    interface: str
    protocol: str
    topic: str
    sections: list[Section]
    updated_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode: str = Field(default="explain", pattern=r"^(explain|compare|diagnose)$")
    release: str = ""
    product: str = ""
    domain: str = ""


class SourceOut(BaseModel):
    n: int
    doc_id: str
    title: str
    path: str
    anchor: str
    release: str
    fragment: str
    score: float


class AskOut(BaseModel):
    id: int
    mode: str
    answer: str
    blocked: bool
    reason: str = ""
    confidence: int
    sources: list[SourceOut]
    latency_ms: int
    stages_ms: dict[str, int]


class FeedbackIn(BaseModel):
    answer_id: int
    value: str = Field(pattern=r"^(like|dislike)$")
