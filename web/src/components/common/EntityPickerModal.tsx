import { useMemo, useState } from 'react';
import Modal from './Modal';

export interface PickItem {
  id: string;
  name: string;
  description?: string | null;
}

// Search-and-pick list in a modal. Used to add skills / subagents to a
// workspace from the full catalog.
export default function EntityPickerModal({
  title,
  items,
  onPick,
  onClose,
}: {
  title: string;
  items: PickItem[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const [q, setQ] = useState('');
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return items;
    return items.filter(
      (i) =>
        i.name.toLowerCase().includes(s) ||
        (i.description ?? '').toLowerCase().includes(s),
    );
  }, [items, q]);

  return (
    <Modal title={title} onClose={onClose} wide>
      <input
        autoFocus
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search…"
        style={{ width: '100%', marginBottom: 10 }}
      />
      {filtered.length === 0 ? (
        <p className="dim">{items.length === 0 ? 'Nothing available to add.' : 'No matches.'}</p>
      ) : (
        <div className="stack" style={{ gap: 6 }}>
          {filtered.map((i) => (
            <button
              key={i.id}
              onClick={() => onPick(i.id)}
              style={{
                textAlign: 'left',
                padding: '8px 10px',
                border: '1px solid var(--border)',
                borderRadius: 6,
                background: 'transparent',
                cursor: 'pointer',
              }}
            >
              <div style={{ fontWeight: 500, fontSize: 13 }}>{i.name}</div>
              {i.description && (
                <div className="dim" style={{ fontSize: 12, marginTop: 2 }}>{i.description}</div>
              )}
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
