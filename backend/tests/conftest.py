"""Общая настройка тестов: временная база, поиск в памяти, ИИ без сети, образец документации."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.update({
    "DATABASE_URL": "sqlite:///./data/test.db",
    "SEARCH_BACKEND": "memory",
    "AI_PROVIDER": "mock",
    "SMS_PROVIDER": "console",
    "DOCS_DIR": str(ROOT.parent / "sample-docs"),
    "LOG_FILE": "",
    "SECRET_KEY": "test-secret-key-for-automated-tests-0123456789",
    "ALLOW_REGISTRATION": "true",
})

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    db = ROOT / "data" / "test.db"
    for p in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        if p.exists():
            p.unlink()
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    r = client.post("/api/auth/register", json={"username": "admin1", "password": "Secret12345", "full_name": "Админ"})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
