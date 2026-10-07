"""Документация: дерево, версии, поиск с фасетами, карточка документа, загрузка файлов."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db
from ..deps import admin_user, client_ip, current_user
from ..ingest.loader import ingest_dir, ingest_text
from ..models import Document, User
from ..schemas import DocumentOut, SearchOut
from ..search.base import FACETS
from ..search.service import search_service

router = APIRouter(prefix="/api/docs", tags=["docs"])


@router.get("/tree")
def tree(release: str = "", _: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"releases": search_service.releases(db), "tree": search_service.tree(db, release)}


@router.get("/search", response_model=SearchOut)
def search(q: str = Query(default="", max_length=300), limit: int = Query(default=20, ge=1, le=100),
           product: str = "", vendor: str = "", domain: str = "", release: str = "", node_type: str = "",
           interface: str = "", protocol: str = "", topic: str = "", _: User = Depends(current_user)):
    filters = {k: v for k, v in locals().items() if k in FACETS and v}
    res = search_service.search(q.strip(), filters, limit=limit)
    return {"total": res.total, "took_ms": res.took_ms, "backend": search_service.mode, "hits": res.hits, "facets": res.facets}


@router.get("/facets")
def facets(_: User = Depends(current_user)):
    return {"fields": list(FACETS), "values": search_service.search("", {}, limit=1).facets}


@router.get("/{doc_id}", response_model=DocumentOut)
def get_doc(doc_id: str, _: User = Depends(current_user), db: Session = Depends(get_db)):
    d = search_service.get_document(db, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    return {"id": d.id, "path": d.path, "title": d.title, **{f: getattr(d, f) for f in FACETS},
            "sections": json.loads(d.sections_json or "[]"), "updated_at": d.updated_at}


@router.post("/upload", status_code=201)
async def upload(request: Request, file: UploadFile = File(...), product: str = Form(""), vendor: str = Form(""),
                 domain: str = Form(""), release: str = Form(""), node_type: str = Form(""), interface: str = Form(""),
                 protocol: str = Form(""), topic: str = Form(""), admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Загрузка документа администратором. Повторная загрузка того же файла ничего не дублирует."""
    name = file.filename or "document.md"
    if not name.lower().endswith((".md", ".markdown", ".html", ".htm", ".txt")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Принимаются .md, .html и .txt")
    raw = (await file.read()).decode("utf-8", errors="replace")
    if not raw.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    overrides = {k: v for k, v in {"product": product, "vendor": vendor, "domain": domain, "release": release,
                                   "node_type": node_type, "interface": interface, "protocol": protocol, "topic": topic}.items() if v}
    d, st = ingest_text(db, raw, name, overrides)
    audit(db, admin.username, "doc.upload", d.path, {"status": st, "id": d.id}, client_ip(request))
    return {"id": d.id, "status": st, "title": d.title}


@router.post("/ingest-dir")
def ingest_folder(request: Request, path: str = "", admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    """Загрузить папку с сервера (по умолчанию DOCS_DIR из .env)."""
    folder = path or get_settings().docs_dir
    out = ingest_dir(db, folder)
    audit(db, admin.username, "doc.ingest_dir", folder, out, client_ip(request))
    return {"folder": folder, **out}


@router.delete("/{doc_id}")
def delete_doc(doc_id: str, request: Request, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    d = db.get(Document, doc_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Документ не найден")
    search_service.backend.delete_document(doc_id)
    db.delete(d)
    db.commit()
    audit(db, admin.username, "doc.delete", d.path, {"id": doc_id}, client_ip(request))
    return {"ok": True}
