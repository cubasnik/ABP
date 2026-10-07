/** Обёртка над REST API: билет сеанса, продление при активности, автозавершение через 30 минут. */
export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'abp.token';
const USER_KEY = 'abp.user';
const IDLE_MINUTES = 30;

export type SessionUser = { username: string; role: string; full_name?: string };

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): SessionUser | null {
  if (typeof window === 'undefined') return null;
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; }
}

export function saveSession(token: string, user: SessionUser) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  touch();
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem('abp.lastActive');
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = init.body;
  if (init.json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(init.json); }
  const r = await fetch(`${API}${path}`, { ...init, headers, body });
  if (r.status === 401 && token) { clearSession(); if (typeof window !== 'undefined') window.location.href = '/login?expired=1'; }
  if (!r.ok) {
    let msg = `Ошибка ${r.status}`;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* нет тела */ }
    throw new ApiError(r.status, msg);
  }
  touch();
  return r.status === 204 ? (undefined as T) : r.json();
}

/** Активность пользователя: отметка времени и продление билета не чаще раза в 5 минут. */
let lastRefresh = 0;
export function touch() {
  if (typeof window === 'undefined') return;
  localStorage.setItem('abp.lastActive', String(Date.now()));
  if (getToken() && Date.now() - lastRefresh > 5 * 60 * 1000) {
    lastRefresh = Date.now();
    fetch(`${API}/api/auth/refresh`, { method: 'POST', headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.access_token) localStorage.setItem(TOKEN_KEY, j.access_token); })
      .catch(() => undefined);
  }
}

/** Слежение за бездействием: без действий 30 минут — выход. Вернуть функцию остановки. */
export function watchIdle(onLogout: () => void): () => void {
  const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
  const mark = () => localStorage.setItem('abp.lastActive', String(Date.now()));
  events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
  const timer = window.setInterval(() => {
    const last = Number(localStorage.getItem('abp.lastActive') || Date.now());
    if (Date.now() - last > IDLE_MINUTES * 60 * 1000) { clearSession(); onLogout(); }
  }, 15000);
  return () => { events.forEach((e) => window.removeEventListener(e, mark)); window.clearInterval(timer); };
}

export async function logout() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch { /* сеанс мог истечь */ }
  clearSession();
}
