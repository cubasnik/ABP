'use client';
import { useState } from 'react';

export type TreeNode = { name: string; kind: string; children?: TreeNode[]; docs?: { id: string; title: string; path: string }[] };

const KIND_RU: Record<string, string> = { product: 'продукт', release: 'версия', domain: 'домен', topic: 'тема' };

function Node({ node, activeId, onOpen, depth }: { node: TreeNode; activeId: string; onOpen: (id: string) => void; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  return (
    <li>
      <div className="node" onClick={() => setOpen(!open)}>
        <span>{open ? '▾' : '▸'}</span>
        <span>{node.name}</span>
        <span className="kind">{KIND_RU[node.kind] || ''}</span>
      </div>
      {open && (
        <ul>
          {node.children?.map((c) => <Node key={c.kind + c.name} node={c} activeId={activeId} onOpen={onOpen} depth={depth + 1} />)}
          {node.docs?.map((d) => (
            <li key={d.id}>
              <div className={'node doc' + (d.id === activeId ? ' active' : '')} onClick={() => onOpen(d.id)} title={d.path}>
                <span>📄</span><span>{d.title}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Левая панель: дерево продукт → версия → домен → тема → документы. */
export default function Tree({ tree, activeId, onOpen }: { tree: TreeNode[]; activeId: string; onOpen: (id: string) => void }) {
  if (!tree.length) return <div className="muted">Документов пока нет. Администратор может загрузить их в разделе «Администрирование».</div>;
  return (
    <div className="tree">
      <ul>{tree.map((n) => <Node key={n.name} node={n} activeId={activeId} onOpen={onOpen} depth={0} />)}</ul>
    </div>
  );
}
