"""Поисковый слой на OpenSearch: индекс с фасетами, повторные попытки при временных сбоях."""
from __future__ import annotations

import logging
import time

from opensearchpy import ConnectionError as OsConnError
from opensearchpy import OpenSearch, TransportError

from ..config import get_settings
from .base import FACETS, SearchBackend, SearchResult

log = logging.getLogger("abp.search.opensearch")

MAPPING = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0},
                 "analysis": {"analyzer": {"ru_en": {"type": "custom", "tokenizer": "standard",
                                                      "filter": ["lowercase", "russian_stemmer", "english_stemmer"]}},
                              "filter": {"russian_stemmer": {"type": "stemmer", "language": "russian"},
                                         "english_stemmer": {"type": "stemmer", "language": "english"}}}},
    "mappings": {"properties": {
        "doc_id": {"type": "keyword"}, "anchor": {"type": "keyword"}, "path": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "ru_en", "fields": {"raw": {"type": "keyword"}}},
        "section_title": {"type": "text", "analyzer": "ru_en"},
        "text": {"type": "text", "analyzer": "ru_en"},
        **{f: {"type": "keyword"} for f in FACETS},
    }},
}


class OpenSearchBackend(SearchBackend):
    name = "opensearch"

    def __init__(self) -> None:
        s = get_settings()
        auth = (s.opensearch_user, s.opensearch_password) if s.opensearch_user else None
        self.index = s.opensearch_index
        self.retries = max(1, s.opensearch_retries)
        self.client = OpenSearch(hosts=[s.opensearch_url], http_auth=auth, verify_certs=s.opensearch_verify_certs,
                                 ssl_show_warn=False, timeout=10)

    # ── повторные попытки: сеть и 5xx OpenSearch считаем временными ──
    def _retry(self, fn, *a, **kw):
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return fn(*a, **kw)
            except (OsConnError, TransportError) as e:
                status = getattr(e, "status_code", None)
                if isinstance(e, TransportError) and isinstance(status, int) and status < 500:
                    raise
                last = e
                log.warning("OpenSearch: попытка %d/%d не удалась: %s", attempt, self.retries, e)
                time.sleep(0.3 * attempt)
        raise RuntimeError(f"OpenSearch недоступен: {last}")

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:  # noqa: BLE001
            return False

    def ensure_index(self) -> None:
        if not self._retry(self.client.indices.exists, index=self.index):
            self._retry(self.client.indices.create, index=self.index, body=MAPPING)
            log.info("OpenSearch: индекс %s создан", self.index)

    def index_document(self, doc: dict, sections: list[dict]) -> None:
        """Идемпотентно: идентификатор чанка = doc_id + anchor, повторная загрузка перезаписывает."""
        self.ensure_index()
        self._retry(self.client.delete_by_query, index=self.index, body={"query": {"term": {"doc_id": doc["id"]}}},
                    refresh=True, conflicts="proceed")
        meta = {f: doc.get(f, "") for f in FACETS}
        for sec in sections:
            body = {"doc_id": doc["id"], "anchor": sec["anchor"], "path": doc["path"], "title": doc["title"],
                    "section_title": sec["title"], "text": sec["text"], **meta}
            self._retry(self.client.index, index=self.index, id=f"{doc['id']}#{sec['anchor']}", body=body)
        self._retry(self.client.indices.refresh, index=self.index)

    def delete_document(self, doc_id: str) -> None:
        self._retry(self.client.delete_by_query, index=self.index, body={"query": {"term": {"doc_id": doc_id}}},
                    refresh=True, conflicts="proceed")

    def search(self, q: str, filters: dict[str, str], limit: int = 20) -> SearchResult:
        must = [{"multi_match": {"query": q, "fields": ["title^3", "section_title^2", "text"], "type": "best_fields",
                                 "fuzziness": "AUTO", "operator": "or"}}] if q else [{"match_all": {}}]
        flt = [{"term": {k: v}} for k, v in filters.items() if v]
        body = {"size": limit * 3, "query": {"bool": {"must": must, "filter": flt}},
                "highlight": {"fields": {"text": {"fragment_size": 180, "number_of_fragments": 1}}},
                "aggs": {f: {"terms": {"field": f, "size": 50}} for f in FACETS},
                "_source": ["doc_id", "anchor", "path", "title", "section_title", "text", *FACETS]}
        t0 = time.perf_counter()
        res = self._retry(self.client.search, index=self.index, body=body)
        hits = []
        seen: set[str] = set()
        for h in res["hits"]["hits"]:
            src = h["_source"]
            if src["doc_id"] in seen:          # один результат на документ (лучший чанк)
                continue
            seen.add(src["doc_id"])
            frag = (h.get("highlight", {}).get("text") or [src["text"][:180]])[0]
            hits.append({"id": src["doc_id"], "anchor": src["anchor"], "path": src["path"], "title": src["title"],
                         "score": float(h["_score"] or 0), "snippet": frag.replace("<em>", "**").replace("</em>", "**"),
                         **{f: src.get(f, "") for f in FACETS}})
            if len(hits) >= limit:
                break
        facets = {f: {b["key"]: b["doc_count"] for b in res["aggregations"][f]["buckets"]} for f in FACETS}
        total = res["hits"]["total"]["value"] if isinstance(res["hits"]["total"], dict) else res["hits"]["total"]
        return SearchResult(hits=hits, facets=facets, total=int(total), took_ms=int((time.perf_counter() - t0) * 1000))

    def count(self) -> int:
        try:
            return int(self._retry(self.client.count, index=self.index)["count"])
        except Exception:  # noqa: BLE001
            return 0
