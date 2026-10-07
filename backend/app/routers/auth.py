"""Регистрация и вход: пароль, подтверждение по СМС, вход по QR-коду, продление сеанса."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

import httpx
import segno
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, current_user
from ..metrics import metrics
from ..models import QrLogin, SmsCode, User
from ..schemas import LoginIn, LoginOut, QrConfirmIn, RegisterIn, SmsConfirmIn, TokenOut
from ..security import hash_password, make_token, random_code, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("abp.auth")


def _token(user: User) -> TokenOut:
    s = get_settings()
    return TokenOut(access_token=make_token(user.username, user.role), username=user.username, role=user.role,
                    expires_in_minutes=s.access_token_minutes)


def send_sms(phone: str, code: str) -> None:
    """Отправить код: в режиме console — в журнал (разработка), в режиме http — на шлюз."""
    s = get_settings()
    if s.sms_provider == "http" and s.sms_gateway_url:
        try:
            httpx.post(s.sms_gateway_url, json={"phone": phone, "text": f"Код входа: {code}"},
                       headers={"Authorization": f"Bearer {s.sms_gateway_token}"} if s.sms_gateway_token else {}, timeout=10).raise_for_status()
            return
        except Exception as e:  # noqa: BLE001
            log.error("СМС-шлюз: %s", e)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "СМС-шлюз недоступен") from e
    log.info("СМС (console) на %s: код %s", phone, code)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Самостоятельная регистрация отключена — обратитесь к администратору")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой логин уже занят")
    first = db.scalar(select(User)) is None
    user = User(username=body.username, full_name=body.full_name[:200], phone=body.phone[:32],
                password_hash=hash_password(body.password), role="admin" if first else "user")
    db.add(user)
    db.commit()
    audit(db, user.username, "register", user.username, {"role": user.role}, client_ip(request))
    return _token(user)


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    user = db.scalar(select(User).where(User.username == body.username))
    ip = client_ip(request)
    if not user or not user.is_active:
        metrics.inc("auth.failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    if user.locked_until and user.locked_until > datetime.utcnow():
        left = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        raise HTTPException(status.HTTP_423_LOCKED, f"Учётная запись заблокирована на {left} мин после неудачных попыток входа")
    if not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= s.max_login_failures:
            user.locked_until = datetime.utcnow() + timedelta(minutes=s.lockout_minutes)
            user.failed_logins = 0
            audit(db, user.username, "lockout", user.username, {"minutes": s.lockout_minutes}, ip)
        db.commit()
        metrics.inc("auth.failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    user.failed_logins = 0
    user.locked_until = None
    if user.sms_required and user.phone:
        code = random_code()
        ticket = secrets.token_urlsafe(24)
        db.add(SmsCode(user_id=user.id, code=code, ticket=ticket, expires_at=datetime.utcnow() + timedelta(minutes=s.sms_code_minutes)))
        db.commit()
        send_sms(user.phone, code)
        audit(db, user.username, "login.sms_sent", user.username, {}, ip)
        return LoginOut(status="sms_required", ticket=ticket, phone_hint="…" + user.phone[-4:])
    user.last_login_at = datetime.utcnow()
    db.commit()
    audit(db, user.username, "login", user.username, {}, ip)
    metrics.inc("auth.login")
    return LoginOut(status="ok", token=_token(user))


@router.post("/sms/confirm", response_model=TokenOut)
def sms_confirm(body: SmsConfirmIn, request: Request, db: Session = Depends(get_db)):
    sc = db.scalar(select(SmsCode).where(SmsCode.ticket == body.ticket))
    if not sc or sc.used or sc.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код устарел — войдите заново")
    sc.tries += 1
    if sc.code != body.code.strip():
        if sc.tries >= 5:
            sc.used = True
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код")
    sc.used = True
    user = db.get(User, sc.user_id)
    user.last_login_at = datetime.utcnow()
    db.commit()
    audit(db, user.username, "login.sms", user.username, {}, client_ip(request))
    metrics.inc("auth.login")
    return _token(user)


# ── QR: новое устройство показывает код, вошедшее — подтверждает ──
@router.post("/qr/new")
def qr_new(db: Session = Depends(get_db)):
    s = get_settings()
    token = secrets.token_urlsafe(24)
    db.add(QrLogin(token=token, expires_at=datetime.utcnow() + timedelta(minutes=3)))
    db.commit()
    url = f"{s.frontend_url.rstrip('/')}/qr?token={token}"
    svg = segno.make(url, error="m").svg_inline(scale=5, dark="#0f172a")
    return {"token": token, "url": url, "svg": svg, "expires_in": 180}


@router.get("/qr/poll/{token}")
def qr_poll(token: str, request: Request, db: Session = Depends(get_db)):
    q = db.scalar(select(QrLogin).where(QrLogin.token == token))
    if not q or q.expires_at < datetime.utcnow():
        return {"status": "expired"}
    if not q.approved or q.consumed:
        return {"status": "waiting"}
    q.consumed = True
    user = db.get(User, q.user_id)
    user.last_login_at = datetime.utcnow()
    db.commit()
    audit(db, user.username, "login.qr", user.username, {}, client_ip(request))
    metrics.inc("auth.login")
    return {"status": "ok", "token": _token(user).model_dump()}


@router.post("/qr/confirm")
def qr_confirm(body: QrConfirmIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = db.scalar(select(QrLogin).where(QrLogin.token == body.token))
    if not q or q.expires_at < datetime.utcnow() or q.consumed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "QR-код устарел")
    q.approved, q.user_id = True, user.id
    db.commit()
    audit(db, user.username, "qr.confirm", user.username, {}, client_ip(request))
    return {"ok": True}


@router.post("/refresh", response_model=TokenOut)
def refresh(user: User = Depends(current_user)):
    """Продление сеанса при активности пользователя; без активности 30 мин сеанс истекает."""
    return _token(user)


@router.post("/logout")
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user.username, "logout", user.username, {}, client_ip(request))
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username, "full_name": user.full_name, "role": user.role, "phone": user.phone}
