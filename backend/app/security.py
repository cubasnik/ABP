"""Хэширование паролей (PBKDF2, стандартная библиотека) и подписанные сеансы (JWT)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import jwt

from .config import get_settings

ALGO = "HS256"
ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), ITER).hex()
    return f"pbkdf2${ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


def make_token(username: str, role: str, minutes: int | None = None) -> str:
    """Сеансовый билет. Срок — время бездействия; клиент продлевает его при активности."""
    s = get_settings()
    exp = datetime.utcnow() + timedelta(minutes=minutes or s.access_token_minutes)
    return jwt.encode({"sub": username, "role": role, "exp": exp, "iat": datetime.utcnow()}, s.secret_key, algorithm=ALGO)


def read_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGO])
    except jwt.PyJWTError:
        return None


def random_code(digits: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(digits))
