'use client';

const LABEL: Record<string, string> = {
  product: 'Продукт', vendor: 'Производитель', domain: 'Домен', release: 'Версия', node_type: 'Тип узла',
  interface: 'Интерфейс', protocol: 'Протокол', topic: 'Тема',
};

/** Фасетные фильтры: значение → число документов; щелчок включает или снимает фильтр. */
export default function Facets({ facets, active, onToggle }: {
  facets: Record<string, Record<string, number>>; active: Record<string, string>; onToggle: (field: string, value: string) => void;
}) {
  const fields = Object.keys(facets).filter((f) => Object.keys(facets[f] || {}).length);
  if (!fields.length) return null;
  return (
    <div>
      {fields.map((f) => (
        <div key={f} style={{ marginBottom: 6 }}>
          <span className="muted" style={{ fontSize: '.78rem' }}>{LABEL[f] || f}: </span>
          <span className="facets" style={{ display: 'inline-flex', margin: 0 }}>
            {Object.entries(facets[f]).sort((a, b) => b[1] - a[1]).slice(0, 12).map(([v, n]) => (
              <button key={v} className={'chip' + (active[f] === v ? ' on' : '')} onClick={() => onToggle(f, v)}>{v} · {n}</button>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}
