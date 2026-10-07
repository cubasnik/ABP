'use client';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, API, getToken, saveSession } from '@/lib/api';

type TokenOut = { access_token: string; username: string; role: string };
type LoginOut = { status: 'ok' | 'sms_required'; token?: TokenOut; ticket?: string; phone_hint?: string };

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [tab, setTab] = useState<'password' | 'qr' | 'register'>('password');
  const [u, setU] = useState(''); const [p, setP] = useState(''); const [name, setName] = useState(''); const [phone, setPhone] = useState('');
  const [ticket, setTicket] = useState(''); const [hint, setHint] = useState(''); const [code, setCode] = useState('');
  const [qr, setQr] = useState<{ token: string; svg: string } | null>(null);
  const [err, setErr] = useState(params.get('expired') ? 'Сеанс завершён после 30 минут без активности — войдите снова.' : '');
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (getToken()) router.replace('/'); }, [router]);

  // вход по QR: показать код и ждать подтверждения с другого устройства
  useEffect(() => {
    if (tab !== 'qr') { setQr(null); return; }
    let stop = false;
    let timer: number | undefined;
    (async () => {
      try {
        const q = await api<{ token: string; svg: string }>('/api/auth/qr/new', { method: 'POST' });
        if (stop) return;
        setQr(q);
        const poll = async () => {
          const r = await fetch(`${API}/api/auth/qr/poll/${q.token}`).then((x) => x.json());
          if (stop) return;
          if (r.status === 'ok') { saveSession(r.token.access_token, { username: r.token.username, role: r.token.role }); router.replace('/'); return; }
          if (r.status === 'expired') { setErr('QR-код устарел — откройте вкладку заново'); return; }
          timer = window.setTimeout(poll, 2000);
        };
        timer = window.setTimeout(poll, 2000);
      } catch (e) { setErr((e as Error).message); }
    })();
    return () => { stop = true; if (timer) window.clearTimeout(timer); };
  }, [tab, router]);

  async function submit() {
    setBusy(true); setErr('');
    try {
      if (tab === 'register') {
        const t = await api<TokenOut>('/api/auth/register', { method: 'POST', json: { username: u, password: p, full_name: name, phone } });
        saveSession(t.access_token, { username: t.username, role: t.role, full_name: name }); router.replace('/'); return;
      }
      if (ticket) {
        const t = await api<TokenOut>('/api/auth/sms/confirm', { method: 'POST', json: { ticket, code } });
        saveSession(t.access_token, { username: t.username, role: t.role }); router.replace('/'); return;
      }
      const r = await api<LoginOut>('/api/auth/login', { method: 'POST', json: { username: u, password: p } });
      if (r.status === 'sms_required') { setTicket(r.ticket || ''); setHint(r.phone_hint || ''); return; }
      if (r.token) { saveSession(r.token.access_token, { username: r.token.username, role: r.token.role }); router.replace('/'); }
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="login">
      <div className="card">
        <h2 style={{ margin: '0 0 4px' }}>📚 Обозреватель технической документации</h2>
        <div className="muted" style={{ marginBottom: 12 }}>Вход в программу</div>
        <div className="tabs">
          <button className={'btn small' + (tab === 'password' ? ' on' : '')} onClick={() => { setTab('password'); setTicket(''); }}>Пароль</button>
          <button className={'btn small' + (tab === 'qr' ? ' on' : '')} onClick={() => setTab('qr')}>QR-код</button>
          <button className={'btn small' + (tab === 'register' ? ' on' : '')} onClick={() => setTab('register')}>Регистрация</button>
        </div>
        {err && <div className="blocked" style={{ marginBottom: 10 }}>{err}</div>}
        {tab === 'qr' ? (
          <div className="qr">
            {qr ? <div dangerouslySetInnerHTML={{ __html: qr.svg }} /> : <div className="muted">Готовлю код…</div>}
            <div className="muted" style={{ fontSize: '.85rem', textAlign: 'center' }}>Отсканируйте код устройством, где вы уже вошли, и подтвердите вход.</div>
          </div>
        ) : ticket ? (
          <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <div className="muted" style={{ marginBottom: 8 }}>Код отправлен по СМС на номер {hint}</div>
            <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Код из СМС" inputMode="numeric" autoFocus />
            <button className="btn primary" style={{ marginTop: 10, width: '100%' }} disabled={busy}>Подтвердить</button>
          </form>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
            <input className="input" value={u} onChange={(e) => setU(e.target.value)} placeholder="Логин" autoComplete="username" autoFocus />
            <input className="input" style={{ marginTop: 8 }} type="password" value={p} onChange={(e) => setP(e.target.value)} placeholder="Пароль" autoComplete="current-password" />
            {tab === 'register' && (<>
              <input className="input" style={{ marginTop: 8 }} value={name} onChange={(e) => setName(e.target.value)} placeholder="Имя и фамилия" />
              <input className="input" style={{ marginTop: 8 }} value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Телефон (для СМС-кода, необязательно)" />
            </>)}
            <button className="btn primary" style={{ marginTop: 10, width: '100%' }} disabled={busy}>{tab === 'register' ? 'Зарегистрироваться' : 'Войти'}</button>
          </form>
        )}
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
