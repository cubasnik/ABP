"""Управление пользователями (только администратор): список, создание, изменение, удаление."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import admin_user, client_ip
from ..models import User
from ..schemas import UserCreateIn, UserOut, UserUpdateIn
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    if body.role not in ("user", "admin"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Роль: user или admin")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Такой логин уже занят")
    u = User(username=body.username, full_name=body.full_name[:200], phone=body.phone[:32], role=body.role,
             sms_required=body.sms_required, password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    audit(db, admin.username, "user.create", u.username, {"role": u.role}, client_ip(request))
    return u


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdateIn, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    changes: dict = {}
    for f in ("full_name", "phone", "role", "is_active", "sms_required"):
        v = getattr(body, f)
        if v is not None:
            if f == "role" and v not in ("user", "admin"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Роль: user или admin")
            if f == "is_active" and u.id == admin.id and not v:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя отключить самого себя")
            setattr(u, f, v)
            changes[f] = v
    if body.password:
        u.password_hash = hash_password(body.password)
        changes["password"] = "изменён"
    if body.unlock:
        u.locked_until, u.failed_logins = None, 0
        changes["unlock"] = True
    db.commit()
    audit(db, admin.username, "user.update", u.username, changes, client_ip(request))
    return u


@router.delete("/{user_id}")
def delete_user(user_id: int, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден")
    if u.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя удалить самого себя")
    name = u.username
    db.delete(u)
    db.commit()
    audit(db, admin.username, "user.delete", name, {}, client_ip(request))
    return {"ok": True}
