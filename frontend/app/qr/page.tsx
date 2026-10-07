'use client';
import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, getToken } from '@/lib/api';

/** Страница, которую открывает сканер QR на устройстве, где вход уже выполнен: подтверждает вход на новом устройстве. */
function QrConfirm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get('token') || '';
  const [state, setState] = useState<'ask' | 'done' | 'error'>('ask');
  const [err, setErr] = useState('');

  useEffect(() => { if (!getToken()) router.replace(`/login?next=/qr?token=${token}`); }, [router, token]);

  async function confirm() {
    try { await api('/api/auth/qr/confirm', { method: 'POST', json: { token } }); setState('done'); }
    catch (e) { setErr((e as Error).message); setState('error'); }
  }

  return (
    <div className="login">
      <div className="card">
        <h3 style={{ marginTop: 0 }}>Подтверждение входа по QR-коду</h3>
        {state === 'ask' && (<>
          <p>Кто-то входит в «Обозреватель документации» на другом устройстве под вашей учётной записью. Подтвердить?</p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn primary" onClick={confirm}>Да, это я</button>
            <button className="btn" onClick={() => router.replace('/')}>Отмена</button>
          </div>
        </>)}
        {state === 'done' && <p>✅ Вход подтверждён. Можно закрыть эту страницу.</p>}
        {state === 'error' && <div className="blocked">{err}</div>}
      </div>
    </div>
  );
}

export default function QrPage() {
  return <Suspense><QrConfirm /></Suspense>;
}
