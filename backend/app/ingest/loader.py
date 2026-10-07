"""Загрузка и индексация документов.

Принимаются Markdown, HTML и текст. Метаданные — в заголовке файла (front-matter):
---
title: Настройка S1
product: Baseband
vendor: Ericsson
domain: RAN
release: 24.Q3
node_type: eNodeB
interface: S1
protocol: SCTP
topic: Интеграция
---
Документ режется на разделы по заголовкам; у каждого раздела — якорь для ссылки.
Загрузка идемпотентна: идентификатор = sha256(путь + версия), повтор того же
содержимого ничего не меняет, изменённый файл перезаписывает старую запись.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..metrics import metrics
from ..models import Document
from ..search.base import FACETS
from ..search.service import search_service

log = logging.getLogger("abp.ingest")
FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
HEADING_MD = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
TAG = re.compile(r"<[^>]+>")


def slug(text: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", text.lower(), flags=re.U).strip().replace(" ", "-")
    return re.sub(r"-+", "-", s)[:80] or "section"


def parse(raw: str, filename: str) -> tuple[dict, list[dict], str]:
    """Вернуть (метаданные, разделы, чистый текст)."""
    meta: dict = {}
    m = FRONT.match(raw)
    body = raw
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        body = raw[m.end():]
    if filename.lower().endswith((".html", ".htm")):
        body = re.sub(r"<(h[1-4])[^>]*>(.*?)</\1>", lambda x: "\n" + "#" * int(x.group(1)[1]) + " " + TAG.sub("", x.group(2)) + "\n", body, flags=re.S | re.I)
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
        body = re.sub(r"</(p|div|li|tr|br)>", "\n", body, flags=re.I)
        body = TAG.sub("", body)
    title = meta.get("title") or next((h.group(2) for h in HEADING_MD.finditer(body) if len(h.group(1)) == 1), None) \
        or Path(filename).stem.replace("_", " ")
    sections: list[dict] = []
    pos = 0
    cur_title = "Введение"
    used: set[str] = set()
    for h in HEADING_MD.finditer(body):
        text = body[pos:h.start()].strip()
        if text:
            sections.append(_section(cur_title, text, used))
        cur_title = h.group(2).strip()
        pos = h.end()
    tail = body[pos:].strip()
    if tail or not sections:
        sections.append(_section(cur_title, tail, used))
    plain = "\n\n".join(s["text"] for s in sections)
    meta["title"] = title
    return meta, sections, plain


def _section(title: str, text: str, used: set[str]) -> dict:
    a = slug(title)
    base, n = a, 2
    while a in used:
        a = f"{base}-{n}"
        n += 1
    used.add(a)
    return {"anchor": a, "title": title, "text": text}


def doc_id(path: str, release: str) -> str:
    return hashlib.sha256(f"{path}|{release}".encode()).hexdigest()[:40]


def ingest_text(db: Session, raw: str, path: str, overrides: dict | None = None) -> tuple[Document, str]:
    """Загрузить один документ. Возвращает (документ, 'created'|'updated'|'unchanged')."""
    with metrics.timer("ingest.parse"):
        meta, sections, plain = parse(raw, path)
    meta.update({k: v for k, v in (overrides or {}).items() if v})
    did = doc_id(path, meta.get("release", ""))
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    d = db.get(Document, did)
    status = "updated"
    if d and d.content_sha == sha and d.indexed:
        return d, "unchanged"
    if not d:
        d = Document(id=did, path=path)
        db.add(d)
        status = "created"
    d.title = meta["title"][:300]
    for f in FACETS:
        setattr(d, f, str(meta.get(f, ""))[:200])
    d.content = plain
    d.sections_json = json.dumps(sections, ensure_ascii=False)
    d.content_sha = sha
    d.updated_at = datetime.utcnow()
    db.commit()
    with metrics.timer("ingest.index"):
        search_service.backend.index_document(search_service._doc_dict(d), sections)
    d.indexed = True
    db.commit()
    metrics.inc(f"ingest.{status}")
    log.info("документ %s: %s (%s)", status, d.title, d.path)
    return d, status


def ingest_dir(db: Session, folder: str | Path) -> dict[str, int]:
    """Загрузить все .md/.html/.txt из папки (рекурсивно)."""
    root = Path(folder)
    out = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0}
    if not root.exists():
        log.warning("папка документов не найдена: %s", root)
        return out
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() not in (".md", ".markdown", ".html", ".htm", ".txt"):
            continue
        try:
            _, status = ingest_text(db, p.read_text(encoding="utf-8", errors="replace"), str(p.relative_to(root)).replace("\\", "/"))
            out[status] += 1
        except Exception as e:  # noqa: BLE001
            out["errors"] += 1
            log.error("не загружен %s: %s", p, e)
    return out
