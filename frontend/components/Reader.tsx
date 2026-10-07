'use client';
import { useEffect, useState } from 'react';
import { pins, togglePin } from '@/lib/storage';

export type Doc = {
  id: string; path: string; title: string; product: string; vendor: string; domain: string; release: string;
  node_type: string; interface: string; protocol: string; topic: string; updated_at: string;
  sections: { anchor: string; title: string; text: string }[];
};

/** Центральная область: чтение документа с якорями по разделам и закреплёнными разделами. */
export default function Reader({ doc, anchor }: { doc: Doc | null; anchor?: string }) {
  const [pinned, setPinned] = useState<string[]>([]);
  useEffect(() => { if (doc) setPinned(pins(doc.id)); }, [doc]);
  useEffect(() => {
    if (!doc || !anchor) return;
    const el = document.getElementById(anchor);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [doc, anchor]);

  if (!doc) return <div className="muted" style={{ padding: 20 }}>Выберите документ в дереве слева или найдите его через поиск.</div>;
  const meta = [doc.product, doc.release && `версия ${doc.release}`, doc.domain, doc.node_type, doc.interface, doc.protocol].filter(Boolean);
  const order = [...doc.sections].sort((a, b) => Number(pinned.includes(b.anchor)) - Number(pinned.includes(a.anchor)));
  return (
    <article className="reader card">
      <h1>{doc.title}</h1>
      <div className="muted" style={{ fontSize: '.82rem' }}>{meta.join(' · ')} · {doc.path}</div>
      <div className="anchors">
        {order.map((s) => (
          <a key={s.anchor} href={`#${s.anchor}`} className={pinned.includes(s.anchor) ? 'pinned' : ''}
             onClick={(e) => { e.preventDefault(); document.getElementById(s.anchor)?.scrollIntoView({ behavior: 'smooth' }); }}>
            {pinned.includes(s.anchor) ? '📌 ' : ''}{s.title}
          </a>
        ))}
      </div>
      {doc.sections.map((s) => (
        <section key={s.anchor} className="section">
          <h2 id={s.anchor}>{s.title}</h2>
          <button className="btn small pin" title={pinned.includes(s.anchor) ? 'Открепить раздел' : 'Закрепить раздел'}
                  onClick={() => setPinned(togglePin(doc.id, s.anchor))}>{pinned.includes(s.anchor) ? '📌' : '📍'}</button>
          <p>{s.text}</p>
        </section>
      ))}
    </article>
  );
}
