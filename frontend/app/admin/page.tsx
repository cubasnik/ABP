'use client';
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, API, getToken, getUser, watchIdle } from '@/lib/api';

type User = { id: number; username: string; full_name: string; phone: string; role: string; is_active: boolean; sms_required: boolean; locked_until: string | null; last_login_at: string | null };
type Status = { version: string; search_backend: string; search_alive: boolean; documents: number; chunks_indexed: number; users: number; ai_provider: string; strict_citations: boolean; maintenance: boolean };
type Series = { count: number; errors: number; avg_ms: number; p50_ms: number; p95_ms: number; max_ms: number; per_minute: number };
type Metrics = { documents: number; ai_answers: number; ai_blocked: number; uptime_s: number; requests: number; errors: number; routes: Record<string, Series>; bottlenecks: ({ stage: string } & Series)[] };
type Audit = { id: number; ts: string; username: string; action: string; target: string; details: string; ip: string };
type AiLog = { id: number; ts: string; username: string; mode: string; question: string; blocked: boolean; confidence: number; latency_ms: number; feedback: string };

const TABS = [['status', 'Состояние'], ['users', 'Пользователи'], ['docs', 'Документы'], ['monitor', 'Мониторинг'], ['audit', 'Журнал действий'], ['ai', 'Журнал ИИ']] as const;
const fmt = (s?: string | null) => (s ? new Date(s).toLocaleString('ru-RU') : '—');

export default function Admin() {
  const router = useRouter();
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('status');
  const [status, setStatus] = useState<Status | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [ai, setAi] = useState<AiLog[]>([]);
  const [msg, setMsg] = useState('');
  const [nu, setNu] = useState({ username: '', password: '', full_name: '', phone: '', role: 'user', sms_required: false });
  const [meta, setMeta] = useState({ product: '', vendor: '', domain: '', release: '', node_type: '', interface: '', protocol: '', topic: '' });

  const load = useCallback(async () => {
    try {
      if (tab === 'status') setStatus(await api<Status>('/api/admin/status'));
      if (tab === 'monitor') setMetrics(await api<Metrics>('/api/admin/metrics'));
      if (tab === 'users') setUsers(await api<User[]>('/api/users'));
      if (tab === 'audit') setAudit(await api<Audit[]>('/api/admin/audit?limit=300'));
      if (tab === 'ai') setAi(await api<AiLog[]>('/api/ai/log?limit=200'));
    } catch (e) { setMsg((e as Error).message); }
  }, [tab]);

  useEffect(() => {
    if (!getToken()) { router.replace('/login'); return; }
    if (getUser()?.role !== 'admin') { router.replace('/'); return; }
    return watchIdle(() => router.replace('/login?expired=1'));
  }, [router]);
  useEffect(() => { load(); }, [load]);

  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); setMsg(ok); load(); } catch (e) { setMsg((e as Error).message); }
  }
  async function upload(file: File) {
    const fd = new FormData(); fd.append('file', file);
    Object.entries(meta).forEach(([k, v]) => { if (v) fd.append(k, v); });
    const r = await fetch(`${API}/api/docs/upload`, { method: 'POST', body: fd, headers: { Authorization: `Bearer ${getToken()}` } });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || 'Ошибка загрузки');
    setMsg(`Документ «${j.title}»: ${({ created: 'добавлен', updated: 'обновлён', unchanged: 'уже был без изменений' } as Record<string, string>)[j.status] || j.status}`);
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">⚙ Администрирование</span>
        <span style={{ flex: 1 }} />
        <a className="btn" href="/">← К документации</a>
      </header>
      <div className="col" style={{ maxWidth: 1200, width: '100%', margin: '0 auto' }}>
        <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={'btn small' + (tab === k ? ' on' : '')} onClick={() => setTab(k)}>{l}</button>)}</div>
        {msg && <div className="card" style={{ marginBottom: 10 }}>{msg} <button className="btn small" onClick={() => setMsg('')}>×</button></div>}

        {tab === 'status' && status && (
          <div className="grid2">
            <div className="card"><div className="muted">Версия ПО</div><div className="kpi">{status.version}</div></div>
            <div className="card"><div className="muted">Поиск</div><div className="kpi">{status.search_backend}</div><span className={'badge ' + (status.search_alive ? 'green' : 'red')}>{status.search_alive ? 'работает' : 'недоступен'}</span></div>
            <div className="card"><div className="muted">Документов / фрагментов</div><div className="kpi">{status.documents} / {status.chunks_indexed}</div></div>
            <div className="card"><div className="muted">Пользователей</div><div className="kpi">{status.users}</div></div>
            <div className="card"><div className="muted">ИИ</div><div className="kpi">{status.ai_provider}</div><span className="badge">{status.strict_citations ? 'цитаты обязательны' : 'цитаты не обязательны'}</span></div>
            <div className="card">
              <div className="muted">Управление</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                <button className="btn small" onClick={() => act(() => api('/api/admin/reindex', { method: 'POST' }), 'Переиндексация выполнена')}>🔄 Переиндексировать</button>
                <button className="btn small" onClick={() => act(() => api(`/api/admin/maintenance?on=${!status.maintenance}`, { method: 'POST' }), status.maintenance ? 'Режим обслуживания выключен' : 'Режим обслуживания включён')}>{status.maintenance ? '▶ Снять обслуживание' : '⏸ Обслуживание'}</button>
                <button className="btn small danger" onClick={() => { if (confirm('Остановить сервер? Клиенты потеряют соединение.')) act(() => api('/api/admin/shutdown', { method: 'POST' }), 'Сервер останавливается'); }}>⏻ Остановить сервер</button>
              </div>
            </div>
          </div>
        )}

        {tab === 'users' && (<>
          <div className="card" style={{ marginBottom: 12 }}>
            <b>Новый пользователь</b>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, marginTop: 8 }}>
              <input className="input" placeholder="Логин" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} />
              <input className="input" placeholder="Пароль (от 8 знаков)" type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} />
              <input className="input" placeholder="Имя" value={nu.full_name} onChange={(e) => setNu({ ...nu, full_name: e.target.value })} />
              <input className="input" placeholder="Телефон" value={nu.phone} onChange={(e) => setNu({ ...nu, phone: e.target.value })} />
              <select className="input" value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}><option value="user">пользователь</option><option value="admin">администратор</option></select>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}><input type="checkbox" checked={nu.sms_required} onChange={(e) => setNu({ ...nu, sms_required: e.target.checked })} /> СМС-код при входе</label>
              <button className="btn primary" onClick={() => act(() => api('/api/users', { method: 'POST', json: nu }), 'Пользователь создан')}>Создать</button>
            </div>
          </div>
          <table className="tbl"><thead><tr><th>№</th><th>Логин</th><th>Имя</th><th>Роль</th><th>Состояние</th><th>Последний вход</th><th></th></tr></thead><tbody>
            {users.map((u, i) => (
              <tr key={u.id}><td>{i + 1}</td><td>{u.username}</td><td>{u.full_name}<div className="muted" style={{ fontSize: '.78rem' }}>{u.phone}</div></td>
                <td><select className="input" value={u.role} onChange={(e) => act(() => api(`/api/users/${u.id}`, { method: 'PUT', json: { role: e.target.value } }), 'Роль изменена')}><option value="user">пользователь</option><option value="admin">администратор</option></select></td>
                <td>{u.locked_until && new Date(u.locked_until) > new Date() ? <span className="badge red">заблокирован</span> : u.is_active ? <span className="badge green">активен</span> : <span className="badge yellow">отключён</span>}{u.sms_required && <span className="badge" style={{ marginLeft: 4 }}>СМС</span>}</td>
                <td>{fmt(u.last_login_at)}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="btn small" onClick={() => act(() => api(`/api/users/${u.id}`, { method: 'PUT', json: { unlock: true } }), 'Разблокирован')}>🔓</button>{' '}
                  <button className="btn small" onClick={() => act(() => api(`/api/users/${u.id}`, { method: 'PUT', json: { is_active: !u.is_active } }), u.is_active ? 'Отключён' : 'Включён')}>{u.is_active ? '⏸' : '▶'}</button>{' '}
                  <button className="btn small" onClick={() => { const p = prompt('Новый пароль (от 8 знаков)'); if (p) act(() => api(`/api/users/${u.id}`, { method: 'PUT', json: { password: p } }), 'Пароль изменён'); }}>🔑</button>{' '}
                  <button className="btn small danger" onClick={() => { if (confirm(`Удалить ${u.username}?`)) act(() => api(`/api/users/${u.id}`, { method: 'DELETE' }), 'Удалён'); }}>🗑</button>
                </td></tr>
            ))}
          </tbody></table>
        </>)}

        {tab === 'docs' && (
          <div className="card">
            <b>Загрузка документа</b>
            <div className="muted" style={{ fontSize: '.85rem' }}>Принимаются .md, .html, .txt. Метаданные можно задать в заголовке файла (front-matter) или ниже. Повторная загрузка того же файла ничего не дублирует.</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, margin: '10px 0' }}>
              {Object.keys(meta).map((k) => <input key={k} className="input" placeholder={k} value={meta[k as keyof typeof meta]} onChange={(e) => setMeta({ ...meta, [k]: e.target.value })} />)}
            </div>
            <input type="file" accept=".md,.markdown,.html,.htm,.txt" onChange={(e) => { const f = e.target.files?.[0]; if (f) act(() => upload(f), 'Загружено'); e.target.value = ''; }} />
            <div style={{ marginTop: 12 }}>
              <button className="btn small" onClick={() => act(() => api('/api/docs/ingest-dir', { method: 'POST' }), 'Папка загружена')}>📂 Загрузить папку DOCS_DIR с сервера</button>
            </div>
          </div>
        )}

        {tab === 'monitor' && metrics && (<>
          <div className="grid2" style={{ marginBottom: 12 }}>
            <div className="card"><div className="muted">Запросов / ошибок</div><div className="kpi">{metrics.requests} / {metrics.errors}</div></div>
            <div className="card"><div className="muted">Документов</div><div className="kpi">{metrics.documents}</div></div>
            <div className="card"><div className="muted">Ответов ИИ / заблокировано</div><div className="kpi">{metrics.ai_answers} / {metrics.ai_blocked}</div></div>
            <div className="card"><div className="muted">Время работы</div><div className="kpi">{Math.floor(metrics.uptime_s / 3600)} ч {Math.floor((metrics.uptime_s % 3600) / 60)} мин</div></div>
          </div>
          <div className="card" style={{ marginBottom: 12 }}><b>Узкие места по стадиям</b>
            <table className="tbl"><thead><tr><th>№</th><th>Стадия</th><th>Вызовов</th><th>Ошибок</th><th>Среднее, мс</th><th>p95, мс</th><th>Макс, мс</th></tr></thead><tbody>
              {metrics.bottlenecks.map((b, i) => <tr key={b.stage}><td>{i + 1}</td><td>{b.stage}</td><td>{b.count}</td><td>{b.errors}</td><td>{b.avg_ms}</td><td>{b.p95_ms}</td><td>{b.max_ms}</td></tr>)}
            </tbody></table></div>
          <div className="card"><b>Маршруты: ошибки, задержки, пропускная способность</b>
            <table className="tbl"><thead><tr><th>№</th><th>Маршрут</th><th>Запросов</th><th>Ошибок</th><th>p95, мс</th><th>В минуту</th></tr></thead><tbody>
              {Object.entries(metrics.routes).sort((a, b) => b[1].count - a[1].count).map(([r, s], i) => <tr key={r}><td>{i + 1}</td><td>{r}</td><td>{s.count}</td><td>{s.errors}</td><td>{s.p95_ms}</td><td>{s.per_minute}</td></tr>)}
            </tbody></table></div>
        </>)}

        {tab === 'audit' && (
          <table className="tbl"><thead><tr><th>№</th><th>Время</th><th>Кто</th><th>Действие</th><th>Объект</th><th>Подробности</th><th>IP</th></tr></thead><tbody>
            {audit.map((a, i) => <tr key={a.id}><td>{i + 1}</td><td>{fmt(a.ts)}</td><td>{a.username}</td><td>{a.action}</td><td>{a.target}</td><td style={{ fontSize: '.78rem' }}>{a.details}</td><td>{a.ip}</td></tr>)}
          </tbody></table>
        )}

        {tab === 'ai' && (
          <table className="tbl"><thead><tr><th>№</th><th>Время</th><th>Кто</th><th>Режим</th><th>Вопрос</th><th>Итог</th><th>Уверенность</th><th>мс</th><th>Оценка</th></tr></thead><tbody>
            {ai.map((a, i) => <tr key={a.id}><td>{i + 1}</td><td>{fmt(a.ts)}</td><td>{a.username}</td><td>{a.mode}</td><td>{a.question}</td><td>{a.blocked ? <span className="badge red">заблокирован</span> : <span className="badge green">ответ</span>}</td><td>{a.confidence}%</td><td>{a.latency_ms}</td><td>{a.feedback === 'like' ? '👍' : a.feedback === 'dislike' ? '👎' : ''}</td></tr>)}
          </tbody></table>
        )}
      </div>
    </div>
  );
}
