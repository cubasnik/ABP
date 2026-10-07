"""Запись действий в журнал аудита."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from .models import AuditLog

log = logging.getLogger("abp.audit")


def audit(db: Session, username: str, action: str, target: str = "", details: dict | str | None = None, ip: str = "") -> None:
    """Сохранить событие. Ошибка записи аудита не должна ломать основное действие."""
    try:
        text = details if isinstance(details, str) else json.dumps(details or {}, ensure_ascii=False)
        db.add(AuditLog(username=username or "", action=action, target=target[:300], details=text[:4000], ip=ip[:64]))
        db.commit()
        log.info("аудит: %s %s %s", username, action, target)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        log.error("аудит не записан: %s", e)
