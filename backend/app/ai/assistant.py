"""Ассистент: retrieval-конвейер поверх поискового слоя и ответ с привязкой к источникам.

Режимы: explain — объяснить, compare — сравнить, diagnose — найти причину.
Политика strict-required-citations: каждое утверждение ответа должно ссылаться на
источник вида [n]; ответ без единой цитаты блокируется, а не отдаётся пользователю.
Провайдеры модели: mock (без сети, извлекает ответ из найденных фрагментов),
openai (совместимый API: OpenAI, OpenRouter, Ollama), anthropic.
"""
from __future__ import annotations

import json
import logging
import re
import time

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics import metrics
from ..models import AiLog, Document
from ..search.service import search_service

log = logging.getLogger("abp.ai")
CITE = re.compile(r"\[(\d{1,2})\]")

SYSTEM = {
    "explain": "Ты — ассистент по технической документации телекоммуникационного оборудования. Объясни ответ на вопрос, опираясь ТОЛЬКО на приведённые источники.",
    "compare": "Ты — ассистент по технической документации. Сравни варианты/версии/параметры из вопроса, опираясь ТОЛЬКО на приведённые источники: что общего, в чём различия, что из этого следует.",
    "diagnose": "Ты — ассистент по эксплуатации телекоммуникационного оборудования. По описанию проблемы назови вероятные причины и шаги проверки, опираясь ТОЛЬКО на приведённые источники.",
}
RULES = ("Правила: отвечай по-русски; после каждого утверждения ставь ссылку на источник в виде [n]; "
         "не выдумывай — если в источниках ответа нет, напиши ровно: НЕТ ДАННЫХ В ИСТОЧНИКАХ. Не используй источники, которых нет в списке.")


# ── retrieval ───────────────────────────────────────────────────────
def retrieve(db: Session, question: str, filters: dict[str, str], k: int) -> list[dict]:
    """Найти лучшие разделы: поиск по слою → подтянуть полный текст раздела из базы."""
    with metrics.timer("ai.retrieve"):
        res = search_service.search(question, filters, limit=k)
        out = []
        for n, h in enumerate(res.hits, 1):
            d = db.get(Document, h["id"])
            frag = h.get("snippet", "")
            if d:
                for s in json.loads(d.sections_json or "[]"):
                    if s["anchor"] == h.get("anchor"):
                        frag = s["text"][:1500]
                        break
            out.append({"n": n, "doc_id": h["id"], "title": h["title"], "path": h["path"], "anchor": h.get("anchor", ""),
                        "release": h.get("release", ""), "fragment": frag, "score": float(h["score"])})
        return out


# ── провайдеры ──────────────────────────────────────────────────────
def _mock_answer(question: str, mode: str, sources: list[dict]) -> str:
    """Без модели: извлекаем предложения, пересекающиеся с вопросом, и цитируем источники."""
    from ..search.memory_backend import tokens
    qt = set(tokens(question))
    picked = []
    for s in sources:
        best, best_score = "", 0
        for sent in re.split(r"(?<=[.!?])\s+", s["fragment"]):
            sc = len(qt & set(tokens(sent)))
            if sc > best_score and 20 <= len(sent) <= 400:
                best, best_score = sent.strip(), sc
        if best_score:
            picked.append(f"{best} [{s['n']}]")
        if len(picked) >= 4:
            break
    if not picked:
        return "НЕТ ДАННЫХ В ИСТОЧНИКАХ"
    head = {"explain": "По документации:", "compare": "Сравнение по документации:", "diagnose": "Возможные причины по документации:"}[mode]
    return head + "\n" + "\n".join(f"— {p}" for p in picked)


def _openai_answer(messages: list[dict]) -> str:
    s = get_settings()
    base = (s.ai_base_url or "https://api.openai.com/v1").rstrip("/")
    r = httpx.post(f"{base}/chat/completions", timeout=s.ai_timeout_seconds,
                   headers={"Authorization": f"Bearer {s.ai_api_key}", "Content-Type": "application/json"},
                   json={"model": s.ai_model or "gpt-4o-mini", "messages": messages, "temperature": 0.1})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _anthropic_answer(messages: list[dict]) -> str:
    s = get_settings()
    base = (s.ai_base_url or "https://api.anthropic.com").rstrip("/")
    system = "\n".join(m["content"] for m in messages if m["role"] == "system")
    user = [m for m in messages if m["role"] != "system"]
    r = httpx.post(f"{base}/v1/messages", timeout=s.ai_timeout_seconds,
                   headers={"x-api-key": s.ai_api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                   json={"model": s.ai_model or "claude-sonnet-5-5", "max_tokens": 1200, "system": system, "messages": user})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def _complete(messages: list[dict], question: str, mode: str, sources: list[dict]) -> str:
    p = get_settings().ai_provider
    with metrics.timer(f"ai.llm.{p}"):
        if p == "openai":
            return _openai_answer(messages)
        if p == "anthropic":
            return _anthropic_answer(messages)
        return _mock_answer(question, mode, sources)


# ── ответ ───────────────────────────────────────────────────────────
def ask(db: Session, username: str, question: str, mode: str, filters: dict[str, str]) -> dict:
    s = get_settings()
    t0 = time.perf_counter()
    stages: dict[str, int] = {}
    t = time.perf_counter()
    sources = retrieve(db, question, filters, s.ai_top_k)
    stages["retrieve"] = int((time.perf_counter() - t) * 1000)

    answer, blocked, reason = "", False, ""
    if not sources:
        blocked, reason = True, "Источники не найдены — ответ без цитат запрещён политикой strict-required-citations"
    else:
        ctx = "\n\n".join(f"[{x['n']}] {x['title']} › {x['anchor']} (версия {x['release'] or '—'})\n{x['fragment']}" for x in sources)
        messages = [{"role": "system", "content": SYSTEM[mode] + " " + RULES},
                    {"role": "user", "content": f"Источники:\n{ctx}\n\nВопрос: {question}"}]
        t = time.perf_counter()
        try:
            answer = _complete(messages, question, mode, sources).strip()
        except Exception as e:  # noqa: BLE001
            log.error("модель не ответила: %s", e)
            blocked, reason = True, f"Модель недоступна: {e}"
        stages["generate"] = int((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    cited = sorted({int(n) for n in CITE.findall(answer) if 1 <= int(n) <= len(sources)}) if answer else []
    if not blocked:
        if "НЕТ ДАННЫХ В ИСТОЧНИКАХ" in answer:
            blocked, reason = True, "В найденных источниках нет ответа на вопрос"
        elif s.ai_strict_citations and not cited:
            blocked, reason = True, "Ответ не содержит ссылок на источники — заблокирован политикой strict-required-citations"
    used = [x for x in sources if x["n"] in cited] if cited else sources
    confidence = _confidence(sources, cited, blocked)
    stages["verify"] = int((time.perf_counter() - t) * 1000)

    latency = int((time.perf_counter() - t0) * 1000)
    row = AiLog(username=username, mode=mode, question=question, answer="" if blocked else answer,
                sources_json=json.dumps(used, ensure_ascii=False), confidence=confidence, blocked=blocked, latency_ms=latency)
    db.add(row)
    db.commit()
    metrics.inc("ai.blocked" if blocked else "ai.answered")
    return {"id": row.id, "mode": mode, "answer": "" if blocked else answer, "blocked": blocked, "reason": reason,
            "confidence": confidence, "sources": used, "latency_ms": latency, "stages_ms": stages}


def _confidence(sources: list[dict], cited: list[int], blocked: bool) -> int:
    """0–100: сила совпадения лучших источников и доля процитированных."""
    if blocked or not sources:
        return 0
    top = max(x["score"] for x in sources)
    strength = min(1.0, top / 1.5)
    share = len(cited) / min(3, len(sources))
    return int(round(100 * (0.6 * strength + 0.4 * min(1.0, share))))
