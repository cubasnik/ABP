"""Запасной поисковый слой в памяти процесса (BM25) — для разработки, тестов и
работы без OpenSearch. Индекс строится из таблицы documents при старте."""
from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict

from .base import FACETS, SearchBackend, SearchResult

TOKEN = re.compile(r"[A-Za-zА-Яа-яЁё0-9_\-\.]+")


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(text.lower()):
        t = t.strip(".-_")
        if len(t) < 2:
            continue
        # грубая нормализация окончаний (русский/английский): достаточно для запасного режима
        out.append(t[:6] if len(t) > 7 else t)
    return out


class MemoryBackend(SearchBackend):
    name = "memory"

    def __init__(self) -> None:
        self.chunks: dict[str, dict] = {}            # chunk_id -> запись
        self.tf: dict[str, Counter] = {}
        self.df: Counter = Counter()
        self.len: dict[str, int] = {}

    def _remove(self, doc_id: str) -> None:
        for cid in [c for c, r in self.chunks.items() if r["doc_id"] == doc_id]:
            for term in self.tf[cid]:
                self.df[term] -= 1
                if self.df[term] <= 0:
                    del self.df[term]
            del self.tf[cid], self.len[cid], self.chunks[cid]

    def index_document(self, doc: dict, sections: list[dict]) -> None:
        self._remove(doc["id"])
        meta = {f: doc.get(f, "") for f in FACETS}
        for sec in sections:
            cid = f"{doc['id']}#{sec['anchor']}"
            toks = tokens(doc["title"] + " " + doc["title"] + " " + sec["title"] + " " + sec["title"] + " " + sec["text"])
            self.chunks[cid] = {"doc_id": doc["id"], "anchor": sec["anchor"], "path": doc["path"], "title": doc["title"],
                                "section_title": sec["title"], "text": sec["text"], **meta}
            self.tf[cid] = Counter(toks)
            self.len[cid] = len(toks)
            for term in self.tf[cid]:
                self.df[term] += 1

    def delete_document(self, doc_id: str) -> None:
        self._remove(doc_id)

    def _score(self, q: list[str], cid: str, avg: float) -> float:
        k1, b = 1.5, 0.75
        n = len(self.chunks)
        tf = self.tf[cid]
        s = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
            f = tf[term]
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * self.len[cid] / (avg or 1)))
        return s

    def search(self, q: str, filters: dict[str, str], limit: int = 20) -> SearchResult:
        t0 = time.perf_counter()
        qt = tokens(q)
        avg = (sum(self.len.values()) / len(self.len)) if self.len else 1.0
        pool = [cid for cid, r in self.chunks.items() if all(r.get(k) == v for k, v in filters.items() if v)]
        scored = []
        for cid in pool:
            s = self._score(qt, cid, avg) if qt else 1.0
            if s > 0:
                scored.append((s, cid))
        scored.sort(key=lambda x: -x[0])
        hits, seen = [], set()
        facets: dict[str, Counter] = defaultdict(Counter)
        for s, cid in scored:
            r = self.chunks[cid]
            if r["doc_id"] in seen:
                continue
            seen.add(r["doc_id"])
            for f in FACETS:
                if r.get(f):
                    facets[f][r[f]] += 1
            if len(hits) < limit:
                hits.append({"id": r["doc_id"], "anchor": r["anchor"], "path": r["path"], "title": r["title"],
                             "score": round(s, 3), "snippet": self._snippet(r["text"], qt), **{f: r.get(f, "") for f in FACETS}})
        return SearchResult(hits=hits, facets={f: dict(c) for f, c in facets.items()}, total=len(seen),
                            took_ms=int((time.perf_counter() - t0) * 1000))

    @staticmethod
    def _snippet(text: str, qt: list[str]) -> str:
        low = text.lower()
        pos = min((low.find(t) for t in qt if low.find(t) >= 0), default=0)
        start = max(0, pos - 60)
        frag = text[start:start + 180].strip()
        for t in qt:
            frag = re.sub(f"(?i)({re.escape(t)})", r"**\1**", frag, count=1)
        return ("…" if start else "") + frag + ("…" if start + 180 < len(text) else "")

    def count(self) -> int:
        return len(self.chunks)
