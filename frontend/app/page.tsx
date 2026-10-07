'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Tree, { TreeNode } from '@/components/Tree';
import Facets from '@/components/Facets';
import Reader, { Doc } from '@/components/Reader';
import AiPanel from '@/components/AiPanel';
import { api, getToken, getUser, logout, watchIdle } from '@/lib/api';
import { saveRelease, saveSearch, savedRelease, savedSearches, removeSearch, SavedSearch } from '@/lib/storage';

type Hit = { id: string; title: string; path: string; anchor: string; snippet: string; score: number; release: string; product: string; domain: string };
type SearchOut = { total: number; took_ms: number; backend: string; hits: Hit[]; facets: Record<string, Record<string, number>> };

export default function Home() {
  const router = useRouter();
  const [user, setUser] = useState(getUser());
  const [releases, setReleases] = useState<string[]>([]);
  const [release, setRelease] = useState('');
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [q, setQ] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [res, setRes] = useState<SearchOut | null>(null);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [anchor, setAnchor] = useState('');
  const [saved, setSaved] = useState<SavedSearch[]>([]);
  const [tab, setTab] = useState<'left' | 'center' | 'right'>('center');
  const [err, setErr] = useState('');

  useEffect(() => {
    if (!getToken()) { router.replace('/login'); return; }
    setUser(getUser());
    setRelease(savedRelease());
    setSaved(savedSearches());
    return watchIdle(() => router.replace('/login?expired=1'));
  }, [router]);

  const loadTree = useCallback(async (rel: string) => {
    try {
      const t = await api<{ releases: string[]; tree: TreeNode[] }>(`/api/docs/tree?release=${encodeURIComponent(rel)}`);
      setReleases(t.releases); setTree(t.tree);
    } catch (e) { setErr((e as Error).message); }
  }, []);
  useEffect(() => { if (getToken()) loadTree(release); }, [release, loadTree]);

  async function openDoc(id: string, a = '') {
    try { setDoc(await api<Doc>(`/api/docs/${id}`)); setAnchor(a); setTab('center'); } catch (e) { setErr((e as Error).message); }
  }

  async function search(query = q, f = filters) {
    const params = new URLSearchParams({ q: query, ...(release ? { release } : {}), ...f });
    try {
      setRes(await api<SearchOut>(`/api/docs/search?${params}`));
      if (query.trim()) { saveSearch(query.trim(), f); setSaved(savedSearches()); }
      setDoc(null); setTab('center');
    } catch (e) { setErr((e as Error).message); }
  }
  function toggleFacet(field: string, value: string) {
    const f = { ...filters };
    if (f[field] === value) delete f[field]; else f[field] = value;
    setFilters(f); search(q, f);
  }
  function changeRelease(r: string) { setRelease(r); saveRelease(r); setRes(null); }

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">📚 Обозреватель документации</span>
        <div className="search">
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Глобальный поиск по документации…"
                 onKeyDown={(e) => { if (e.key === 'Enter') search(); }} />
          <button className="btn primary" onClick={() => search()}>Найти</button>
        </div>
        <select className="input" style={{ width: 150 }} value={release} onChange={(e) => changeRelease(e.target.value)} title="Версия релиза">
          <option value="">Все версии</option>
          {releases.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        {user?.role === 'admin' && <a className="btn" href="/admin">⚙ Администрирование</a>}
        <button className="btn" title="Выйти из программы" onClick={async () => { await logout(); router.replace('/login'); }}>👤 {user?.full_name || user?.username} · Выйти</button>
      </header>
      <div className="mobile-tabs">
        <button className={'btn small' + (tab === 'left' ? ' primary' : '')} onClick={() => setTab('left')}>Дерево</button>
        <button className={'btn small' + (tab === 'center' ? ' primary' : '')} onClick={() => setTab('center')}>Документ</button>
        <button className={'btn small' + (tab === 'right' ? ' primary' : '')} onClick={() => setTab('right')}>Ассистент</button>
      </div>
      <div className="cols">
        <aside className={'col left' + (tab === 'left' ? ' show' : '')}>
          <Tree tree={tree} activeId={doc?.id || ''} onOpen={(id) => openDoc(id)} />
          {saved.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="muted" style={{ fontSize: '.8rem', marginBottom: 4 }}>Сохранённые поиски</div>
              {saved.map((s) => (
                <div key={s.at} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: '.85rem' }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); setQ(s.q); setFilters(s.filters); search(s.q, s.filters); }}>🔎 {s.q}</a>
                  <button className="btn small" onClick={() => { removeSearch(s.at); setSaved(savedSearches()); }} title="Убрать">×</button>
                </div>
              ))}
            </div>
          )}
        </aside>
        <main className={'col' + (tab === 'center' ? ' show' : '')}>
          {err && <div className="blocked" style={{ marginBottom: 10 }}>{err} <button className="btn small" onClick={() => setErr('')}>×</button></div>}
          {res && !doc && (
            <div>
              <div className="muted" style={{ fontSize: '.82rem' }}>Найдено {res.total} · {res.took_ms} мс · поиск: {res.backend}</div>
              <Facets facets={res.facets} active={filters} onToggle={toggleFacet} />
              {res.hits.map((h) => (
                <div key={h.id} className="hit" onClick={() => openDoc(h.id, h.anchor)}>
                  <b>{h.title}</b> <span className="muted" style={{ fontSize: '.78rem' }}>› {h.anchor}</span>
                  <div dangerouslySetInnerHTML={{ __html: h.snippet.replace(/</g, '&lt;').replace(/\*\*(.+?)\*\*/g, '<mark>$1</mark>') }} />
                  <div className="meta">{[h.product, h.release && `версия ${h.release}`, h.domain].filter(Boolean).join(' · ')} · {h.path}</div>
                </div>
              ))}
              {!res.hits.length && <div className="muted">Ничего не найдено. Попробуйте другие слова или снимите фильтры.</div>}
            </div>
          )}
          {(doc || !res) && <Reader doc={doc} anchor={anchor} />}
        </main>
        <aside className={'col right' + (tab === 'right' ? ' show' : '')}>
          <AiPanel release={release} onOpenSource={(id, a) => openDoc(id, a)} />
        </aside>
      </div>
    </div>
  );
}
