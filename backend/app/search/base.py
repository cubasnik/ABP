"""Общий интерфейс поисковых слоёв."""
from __future__ import annotations

from dataclasses import dataclass, field

FACETS = ("product", "vendor", "domain", "release", "node_type", "interface", "protocol", "topic")


@dataclass
class SearchResult:
    hits: list[dict] = field(default_factory=list)
    facets: dict[str, dict[str, int]] = field(default_factory=dict)
    total: int = 0
    took_ms: int = 0


class SearchBackend:
    name = "base"

    def ping(self) -> bool:
        return True

    def ensure_index(self) -> None: ...

    def index_document(self, doc: dict, sections: list[dict]) -> None: ...

    def delete_document(self, doc_id: str) -> None: ...

    def search(self, q: str, filters: dict[str, str], limit: int = 20) -> SearchResult: ...

    def count(self) -> int:
        return 0
