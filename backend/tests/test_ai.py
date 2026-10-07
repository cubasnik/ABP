"""Ассистент: ответ с источниками, блокировка без цитат, режимы, обратная связь, журнал."""
from __future__ import annotations


def test_ask_explain_has_sources(client, auth):
    r = client.post("/api/ai/ask", json={"question": "Что задаёт параметр rtoMin для SCTP?", "mode": "explain"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body["blocked"], body["reason"]
    assert "[1]" in body["answer"] or "[2]" in body["answer"]
    assert body["sources"] and body["sources"][0]["anchor"]
    assert 0 < body["confidence"] <= 100
    assert set(body["stages_ms"]) >= {"retrieve", "generate", "verify"}


def test_ask_blocked_without_citations(client, auth):
    r = client.post("/api/ai/ask", json={"question": "кхмлптр зщшгн ъъъ", "mode": "diagnose"}, headers=auth)
    body = r.json()
    assert body["blocked"] and body["answer"] == "" and body["confidence"] == 0


def test_modes_and_filters(client, auth):
    for mode in ("explain", "compare", "diagnose"):
        r = client.post("/api/ai/ask", json={"question": "состояние ассоциаций SCTP", "mode": mode, "release": "99.Q9"}, headers=auth)
        assert r.status_code == 200 and r.json()["mode"] == mode
    assert client.post("/api/ai/ask", json={"question": "что-то", "mode": "wrong"}, headers=auth).status_code == 422


def test_feedback_and_logs(client, auth):
    rid = client.post("/api/ai/ask", json={"question": "rtoMin SCTP", "mode": "explain"}, headers=auth).json()["id"]
    assert client.post("/api/ai/feedback", json={"answer_id": rid, "value": "like"}, headers=auth).status_code == 200
    hist = client.get("/api/ai/history", headers=auth).json()
    assert any(h["id"] == rid and h["feedback"] == "like" for h in hist)
    log = client.get("/api/ai/log", headers=auth).json()
    assert any(x["id"] == rid for x in log)
