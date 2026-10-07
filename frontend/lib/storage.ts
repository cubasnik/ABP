/** Локальные настройки пользователя: сохранённые поиски, закреплённые разделы, версия. */
const SEARCHES = 'abp.savedSearches';
const PINS = 'abp.pins';
const RELEASE = 'abp.release';

function read<T>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try { return JSON.parse(localStorage.getItem(key) || '') as T; } catch { return fallback; }
}
function write(key: string, value: unknown) { localStorage.setItem(key, JSON.stringify(value)); }

export type SavedSearch = { q: string; filters: Record<string, string>; at: number };

export function savedSearches(): SavedSearch[] { return read<SavedSearch[]>(SEARCHES, []); }
export function saveSearch(q: string, filters: Record<string, string>) {
  const list = savedSearches().filter((s) => s.q !== q || JSON.stringify(s.filters) !== JSON.stringify(filters));
  list.unshift({ q, filters, at: Date.now() });
  write(SEARCHES, list.slice(0, 20));
}
export function removeSearch(at: number) { write(SEARCHES, savedSearches().filter((s) => s.at !== at)); }

/** Закреплённые якоря: docId → список anchor. */
export function pins(docId: string): string[] { return read<Record<string, string[]>>(PINS, {})[docId] || []; }
export function togglePin(docId: string, anchor: string): string[] {
  const all = read<Record<string, string[]>>(PINS, {});
  const cur = new Set(all[docId] || []);
  if (cur.has(anchor)) cur.delete(anchor); else cur.add(anchor);
  all[docId] = [...cur];
  write(PINS, all);
  return all[docId];
}

export function savedRelease(): string { return read<string>(RELEASE, ''); }
export function saveRelease(r: string) { write(RELEASE, r); }
