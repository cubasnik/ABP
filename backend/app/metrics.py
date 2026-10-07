"""Метрики в памяти процесса: запросы, ошибки, задержки по маршрутам и по стадиям обработки.

Хранится скользящее окно последних замеров — достаточно для панелей мониторинга
и списка узких мест без внешних систем.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

WINDOW = 2000


class _Series:
    def __init__(self) -> None:
        self.count = 0
        self.errors = 0
        self.lat = deque(maxlen=WINDOW)       # миллисекунды
        self.stamps = deque(maxlen=WINDOW)    # время окончания, с

    def add(self, ms: float, error: bool = False) -> None:
        self.count += 1
        if error:
            self.errors += 1
        self.lat.append(ms)
        self.stamps.append(time.time())

    def stats(self) -> dict:
        lat = sorted(self.lat)
        n = len(lat)
        pct = lambda p: (lat[min(n - 1, int(n * p))] if n else 0)  # noqa: E731
        now = time.time()
        per_min = sum(1 for t in self.stamps if now - t <= 60)
        return {"count": self.count, "errors": self.errors, "avg_ms": round(sum(lat) / n, 1) if n else 0,
                "p50_ms": round(pct(0.5), 1), "p95_ms": round(pct(0.95), 1), "max_ms": round(lat[-1], 1) if n else 0,
                "per_minute": per_min}


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.routes: dict[str, _Series] = defaultdict(_Series)
        self.stages: dict[str, _Series] = defaultdict(_Series)
        self.started = time.time()
        self.counters: dict[str, int] = defaultdict(int)

    def route(self, name: str, ms: float, error: bool) -> None:
        with self._lock:
            self.routes[name].add(ms, error)

    def stage(self, name: str, ms: float, error: bool = False) -> None:
        with self._lock:
            self.stages[name].add(ms, error)

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] += n

    @contextmanager
    def timer(self, stage: str):
        """Замер стадии: with metrics.timer('search.opensearch'): ..."""
        t0 = time.perf_counter()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            self.stage(stage, (time.perf_counter() - t0) * 1000, not ok)

    def snapshot(self) -> dict:
        with self._lock:
            routes = {k: v.stats() for k, v in self.routes.items()}
            stages = {k: v.stats() for k, v in self.stages.items()}
            counters = dict(self.counters)
        total = sum(r["count"] for r in routes.values())
        errors = sum(r["errors"] for r in routes.values())
        # узкие места — стадии по убыванию p95
        bottlenecks = sorted(({"stage": k, **v} for k, v in stages.items()), key=lambda x: -x["p95_ms"])
        return {"uptime_s": int(time.time() - self.started), "requests": total, "errors": errors,
                "routes": routes, "stages": stages, "bottlenecks": bottlenecks[:20], "counters": counters}


metrics = Metrics()
