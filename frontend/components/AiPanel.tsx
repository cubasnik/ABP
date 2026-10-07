'use client';
import { useState } from 'react';
import { api } from '@/lib/api';

type Source = { n: number; doc_id: string; title: string; path: string; anchor: string; release: string; fragment: string; score: number };
type Answer = { id: number; mode: string; answer: string; blocked: boolean; reason: string; confidence: number; sources: Source[]; latency_ms: number; stages_ms: Record<string, number> };
const MODES: [string, string, string][] = [['explain', 'Объяснить', 'что это и как работает'], ['compare', 'Сравнить', 'версии, параметры, варианты'], ['diagnose', 'Диагностика', 'причины и шаги проверки']];

/** Правая панель: ассистент с ответами, привязанными к источникам. */
export default function AiPanel({ release, onOpenSource }: { release: string; onOpenSource: (docId: string, anchor: string) => void }) {
  const [mode, setMode] = useState('explain');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [ans, setAns] = useState<Answer | null>(null);
  const [err, setErr] = useState('');
  const [fb, setFb] = useState('');

  async function ask() {
    if (q.trim().length < 3 || busy) return;
    setBusy(true); setErr(''); setFb('');
    try { setAns(await api<Answer>('/api/ai/ask', { method: 'POST', json: { question: q.trim(), mode, release } })); }
    catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }
  async function feedback(value: 'like' | 'dislike') {
    if (!ans) return;
    try { await api('/api/ai/feedback', { method: 'POST', json: { answer_id: ans.id, value } }); setFb(value); } catch (e) { setErr((e as Error).message); }
  }
  const rendered = ans?.answer.split(/(\[\d{1,2}\])/g).map((part, i) => {
    const m = /^\[(\d{1,2})\]$/.exec(part);
    if (!m) return <span key={i}>{part}</span>;
    const s = ans.sources.find((x) => x.n === Number(m[1]));
    return <a key={i} href="#" title={s ? s.title : ''} onClick={(e) => { e.preventDefault(); if (s) onOpenSource(s.doc_id, s.anchor); }}
              style={{ color: '#0f766e', fontWeight: 700, textDecoration: 'none' }}>{part}</a>;
  });

  return (
    <div className="ai">
      <h3 style={{ margin: '0 0 8px' }}>🤖 Ассистент</h3>
      <div className="modes">
        {MODES.map(([k, l, t]) => <button key={k} className={'btn small' + (mode === k ? ' on' : '')} title={t} onClick={() => setMode(k)}>{l}</button>)}
      </div>
      <textarea className="input" rows={3} value={q} onChange={(e) => setQ(e.target.value)} placeholder={release ? `Вопрос по версии ${release}…` : 'Вопрос по документации…'}
                onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask(); }} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0' }}>
        <button className="btn primary" onClick={ask} disabled={busy}>{busy ? '⏳ Ищу в источниках…' : 'Спросить'}</button>
        <span className="muted" style={{ fontSize: '.78rem' }}>Ctrl+Enter · ответ только со ссылками на документы</span>
      </div>
      {err && <div className="blocked">{err}</div>}
      {ans && ans.blocked && (
        <div className="blocked"><b>Ответ заблокирован.</b> {ans.reason}
          <div className="muted" style={{ fontSize: '.8rem', marginTop: 4 }}>Политика strict-required-citations: без цитат из документации ответ не выдаётся. Уточните вопрос или смените версию.</div>
        </div>
      )}
      {ans && !ans.blocked && (
        <div className="card">
          <div className="answer">{rendered}</div>
          <div style={{ margin: '10px 0 4px', fontSize: '.8rem' }} className="muted">Уверенность: {ans.confidence}% · {ans.latency_ms} мс
            {Object.entries(ans.stages_ms).map(([k, v]) => ` · ${k} ${v}`).join('')}</div>
          <div className="conf"><i style={{ width: `${ans.confidence}%` }} /></div>
          <div style={{ marginTop: 10, fontWeight: 600, fontSize: '.85rem' }}>Источники</div>
          {ans.sources.map((s) => (
            <div key={s.n} className="src" onClick={() => onOpenSource(s.doc_id, s.anchor)} title="Открыть раздел документа">
              <b>[{s.n}]</b> {s.title} › {s.anchor}{s.release ? ` · ${s.release}` : ''}
              <div className="muted" style={{ fontSize: '.78rem' }}>{s.fragment.slice(0, 160)}{s.fragment.length > 160 ? '…' : ''}</div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            <button className={'btn small' + (fb === 'like' ? ' primary' : '')} onClick={() => feedback('like')}>👍 Полезно</button>
            <button className={'btn small' + (fb === 'dislike' ? ' danger' : '')} onClick={() => feedback('dislike')}>👎 Нет</button>
          </div>
        </div>
      )}
    </div>
  );
}
