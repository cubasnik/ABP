"""Сервис поиска: выбор слоя (OpenSearch или память), дерево документации,
гибридное ранжирование с повторным ранжированием, карточка документа."""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics import metrics
from ..models import Document
from .base import FACETS, SearchBackend, SearchResult
from .memory_backend import MemoryBackend, tokens

log = logging.getLogger("abp.search")


class SearchService:
    def __init__(self) -> None:
        self.backend: SearchBackend = MemoryBackend()
        self.mode = "memory"

    # ── выбор слоя ────────────────────────────────────────────────
    def connect(self) -> str:
        s = get_settings()
        if s.search_backend in ("auto", "opensearch"):
            try:
                from .opensearch_backend import OpenSearchBackend
                osb = OpenSearchBackend()
                if osb.ping():
                    osb.ensure_index()
                    self.backend, self.mode = osb, "opensearch"
                    log.info("поиск: OpenSearch %s, индекс %s", s.opensearch_url, s.opensearch_index)
                    return self.mode
                if s.search_backend == "opensearch":
                    raise RuntimeError("OpenSearch не отвечает на ping")
                log.warning("поиск: OpenSearch недоступен, работаю в памяти (search_backend=auto)")
            except Exception as e:  # noqa: BLE001
                if s.search_backend == "opensearch":
                    raise
                log.warning("поиск: OpenSearch не подключён (%s), работаю в памяти", e)
        self.backend, self.mode = MemoryBackend(), "memory"
        return self.mode

    def warm(self, db: Session) -> int:
        """Поднять индекс в памяти из базы (OpenSearch хранит свой сам)."""
        n = 0
        if self.mode == "memory":
            for d in db.scalars(select(Document)):
                self.backend.index_document(self._doc_dict(d), json.loads(d.sections_json or "[]"))
                n += 1
        return n

    def reindex_all(self, db: Session) -> int:
        n = 0
        for d in db.scalars(select(Document)):
            self.backend.index_document(self._doc_dict(d), json.loads(d.sections_json or "[]"))
            d.indexed = True
            n += 1
        db.commit()
        return n

    @staticmethod
    def _doc_dict(d: Document) -> dict:
        return {"id": d.id, "path": d.path, "title": d.title, **{f: getattr(d, f) for f in FACETS}}

    # ── поиск ─────────────────────────────────────────────────────
    def search(self, q: str, filters: dict[str, str], limit: int = 20) -> SearchResult:
        with metrics.timer(f"search.{self.mode}"):
            res = self.backend.search(q, filters, limit=limit * 2)
        with metrics.timer("search.rerank"):
            res.hits = self._rerank(q, res.hits)[:limit]
        metrics.inc("search.queries")
        return res

    @staticmethod
    def _rerank(q: str, hits: list[dict]) -> list[dict]:
        """Повторное ранжирование: к оценке слоя добавляется совпадение запроса с заголовком
        и точное вхождение фразы в фрагмент — поднимает «тот самый» документ выше похожих."""
        if not q or not hits:
            return hits
        qt = set(tokens(q))
        phrase = q.lower().strip()
        top = max((h["score"] for h in hits), default=1.0) or 1.0
        for h in hits:
            tt = set(tokens(h["title"]))
            overlap = len(qt & tt) / (len(qt) or 1)
            exact = 1.0 if phrase and phrase in (h.get("snippet", "") + " " + h["title"]).lower() else 0.0
            h["score"] = round(h["score"] / top + 0.5 * overlap + 0.3 * exact, 4)
        return sorted(hits, key=lambda h: -h["score"])

    # ── дерево и карточки ─────────────────────────────────────────
    def tree(self, db: Session, release: str = "") -> list[dict]:
        """Продукт → версия → домен → тема → документы."""
        q = select(Document).order_by(Document.product, Document.release, Document.domain, Document.topic, Document.title)
        if release:
            q = q.where(Document.release == release)
        root: dict = {}
        for d in db.scalars(q):
            p = root.setdefault(d.product or "Без продукта", {})
            r = p.setdefault(d.release or "—", {})
            dom = r.setdefault(d.domain or "Общее", {})
            dom.setdefault(d.topic or "Разное", []).append({"id": d.id, "title": d.title, "path": d.path})

        chain = ["product", "release", "domain", "topic"]

        def node(name, children, kind):
            if isinstance(children, list):
                return {"name": name, "kind": kind, "docs": children}
            nk = chain[chain.index(kind) + 1]
            return {"name": name, "kind": kind, "children": [node(k, v, nk) for k, v in children.items()]}
        return [node(k, v, "product") for k, v in root.items()] if root else []

    def releases(self, db: Session) -> list[str]:
        rows = db.execute(select(Document.release).distinct()).scalars().all()
        return sorted([r for r in rows if r], key=_release_key, reverse=True)

    def get_document(self, db: Session, doc_id: str) -> Document | None:
        return db.get(Document, doc_id)


def _release_key(r: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-_ ]", r)]


search_service = SearchService()
