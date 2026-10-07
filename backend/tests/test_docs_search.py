"""Загрузка документов, идемпотентность, дерево, поиск с фасетами, карточка с якорями."""
from __future__ import annotations

DOC = """---
title: Тестовый документ S1
product: Baseband
vendor: Ericsson
domain: RAN
release: 99.Q9
node_type: eNodeB
interface: S1
protocol: SCTP
topic: Интеграция
---
# Тестовый документ S1

## Настройка SCTP
Параметр rtoMin задаёт минимальный таймаут повторной передачи SCTP для интерфейса S1.

## Проверка связи
Команда st sctp показывает состояние ассоциаций.
"""


def test_sample_docs_loaded(client, auth):
    r = client.get("/api/docs/tree", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["tree"], "образцы из sample-docs подхвачены при старте"
    assert body["releases"]


def test_upload_idempotent(client, auth):
    files = {"file": ("s1-test.md", DOC.encode("utf-8"), "text/markdown")}
    r1 = client.post("/api/docs/upload", files=files, headers=auth)
    assert r1.status_code == 201 and r1.json()["status"] == "created"
    r2 = client.post("/api/docs/upload", files={"file": ("s1-test.md", DOC.encode("utf-8"), "text/markdown")}, headers=auth)
    assert r2.json()["status"] == "unchanged" and r2.json()["id"] == r1.json()["id"]
    r3 = client.post("/api/docs/upload", files={"file": ("s1-test.md", (DOC + "\nДополнение.").encode("utf-8"), "text/markdown")}, headers=auth)
    assert r3.json()["status"] == "updated" and r3.json()["id"] == r1.json()["id"]


def test_search_with_facets(client, auth):
    r = client.get("/api/docs/search", params={"q": "rtoMin SCTP", "release": "99.Q9"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "memory" and body["total"] >= 1
    hit = body["hits"][0]
    assert hit["title"] == "Тестовый документ S1" and hit["anchor"] == "настройка-sctp"
    assert "**" in hit["snippet"], "фрагмент с подсветкой"
    assert body["facets"]["interface"].get("S1") >= 1
    # фильтр по фасету отсекает чужие документы
    r = client.get("/api/docs/search", params={"q": "SCTP", "release": "00.X0"}, headers=auth)
    assert r.json()["total"] == 0


def test_document_card_anchors(client, auth):
    hit = client.get("/api/docs/search", params={"q": "ассоциаций", "release": "99.Q9"}, headers=auth).json()["hits"][0]
    d = client.get(f"/api/docs/{hit['id']}", headers=auth).json()
    anchors = [s["anchor"] for s in d["sections"]]
    assert "проверка-связи" in anchors and d["protocol"] == "SCTP"


def test_tree_filtered_by_release(client, auth):
    body = client.get("/api/docs/tree", params={"release": "99.Q9"}, headers=auth).json()
    assert body["tree"][0]["name"] == "Baseband"
    rel = body["tree"][0]["children"][0]
    assert rel["name"] == "99.Q9" and rel["kind"] == "release"


def test_status_and_reindex(client, auth):
    st = client.get("/api/admin/status", headers=auth).json()
    assert st["search_backend"] == "memory" and st["documents"] >= 1
    r = client.post("/api/admin/reindex", headers=auth).json()
    assert r["reindexed"] == st["documents"]
    m = client.get("/api/admin/metrics", headers=auth).json()
    assert "search.memory" in m["stages"] and m["bottlenecks"]
