"""Регистрация, вход, блокировка, СМС-код, QR-код, роли."""
from __future__ import annotations

import re

from sqlalchemy import select


def test_first_user_is_admin(client, auth):
    r = client.get("/api/auth/me", headers=auth)
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_login_and_lockout(client, auth):
    r = client.post("/api/users", json={"username": "ivan", "password": "Password123", "full_name": "Иван"}, headers=auth)
    assert r.status_code == 201
    assert client.post("/api/auth/login", json={"username": "ivan", "password": "Password123"}).json()["status"] == "ok"
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "ivan", "password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "ivan", "password": "Password123"})
    assert r.status_code == 423, "после 5 неудач учётная запись блокируется"
    # разблокировка администратором
    uid = next(u["id"] for u in client.get("/api/users", headers=auth).json() if u["username"] == "ivan")
    assert client.put(f"/api/users/{uid}", json={"unlock": True}, headers=auth).status_code == 200
    assert client.post("/api/auth/login", json={"username": "ivan", "password": "Password123"}).status_code == 200


def test_sms_flow(client, auth, caplog):
    r = client.post("/api/users", json={"username": "sms_user", "password": "Password123", "phone": "+79990001122", "sms_required": True}, headers=auth)
    assert r.status_code == 201
    with caplog.at_level("INFO", logger="abp.auth"):
        r = client.post("/api/auth/login", json={"username": "sms_user", "password": "Password123"})
    body = r.json()
    assert body["status"] == "sms_required" and body["ticket"]
    code = re.search(r"код (\d{6})", caplog.text).group(1)
    assert client.post("/api/auth/sms/confirm", json={"ticket": body["ticket"], "code": "000000"}).status_code == 401
    r = client.post("/api/auth/sms/confirm", json={"ticket": body["ticket"], "code": code})
    assert r.status_code == 200 and r.json()["username"] == "sms_user"


def test_qr_flow(client, auth):
    q = client.post("/api/auth/qr/new").json()
    assert q["svg"].startswith("<svg") and q["token"]
    assert client.get(f"/api/auth/qr/poll/{q['token']}").json()["status"] == "waiting"
    assert client.post("/api/auth/qr/confirm", json={"token": q["token"]}, headers=auth).status_code == 200
    r = client.get(f"/api/auth/qr/poll/{q['token']}").json()
    assert r["status"] == "ok" and r["token"]["username"] == "admin1"
    assert client.get(f"/api/auth/qr/poll/{q['token']}").json()["status"] == "waiting", "билет выдаётся один раз"


def test_user_role_forbidden(client):
    tok = client.post("/api/auth/login", json={"username": "ivan", "password": "Password123"}).json()["token"]["access_token"]
    assert client.get("/api/users", headers={"Authorization": f"Bearer {tok}"}).status_code == 403
    assert client.get("/api/admin/metrics", headers={"Authorization": f"Bearer {tok}"}).status_code == 403


def test_audit_written(client, auth):
    rows = client.get("/api/admin/audit", headers=auth).json()
    actions = {r["action"] for r in rows}
    assert {"register", "user.create", "lockout", "login"} <= actions


def test_refresh_and_bad_token(client, auth):
    assert client.post("/api/auth/refresh", headers=auth).status_code == 200
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer broken"}).status_code == 401


def test_models_imported():
    from app.models import User
    assert select(User) is not None
