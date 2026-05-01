import { useEffect, useRef, useState } from 'react';
import { api, ResourceKind, SharedResource, SharedRef } from '../api/client';

interface Props {
  kind: ResourceKind | ResourceKind[];
  onPick: (ref: SharedRef) => void;
  selected?: SharedRef;
  placeholder?: string;
}

export default function SharedResourcePicker({ kind, onPick, selected, placeholder }: Props) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<SharedResource[]>([]);
  const [loading, setLoading] = useState(false);
  const [pinVersion, setPinVersion] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      api
        .listResources({ kind, q: q || undefined, limit: 30 })
        .then((res) => setItems(res.items))
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [open, q, kind]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const pick = (item: SharedResource) => {
    const ref: SharedRef = pinVersion
      ? { shared: item.id, version: item.version }
      : { shared: item.id };
    onPick(ref);
    setOpen(false);
    setQ('');
  };

  const selectedLabel = selected ? selected.shared + (selected.version != null ? ` @v${selected.version}` : '') : '';

  return (
    <div ref={containerRef} style={{ position: 'relative', display: 'inline-block', width: '100%' }}>
      <div
        style={{
          display: 'flex',
          gap: 6,
          alignItems: 'center',
          border: '1px solid var(--border)',
          borderRadius: 5,
          padding: '4px 8px',
          background: 'var(--bg-elevated)',
          cursor: 'pointer',
          minHeight: 30,
        }}
        onClick={() => setOpen((v) => !v)}
      >
        <span style={{ flex: 1, color: selectedLabel ? 'var(--fg)' : 'var(--fg-muted)', fontSize: 12 }}>
          {selectedLabel || placeholder || 'pick a shared resource…'}
        </span>
        <span className="dim" style={{ fontSize: 10 }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            zIndex: 200,
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            marginTop: 2,
            maxHeight: 320,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              autoFocus
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="search by name or tag…"
              style={{ flex: 1, fontSize: 12, padding: '4px 8px' }}
            />
            <label style={{ fontSize: 11, color: 'var(--fg-muted)', display: 'flex', gap: 4, alignItems: 'center', whiteSpace: 'nowrap' }}>
              <input
                type="checkbox"
                checked={pinVersion}
                onChange={(e) => setPinVersion(e.target.checked)}
                style={{ width: 'auto', padding: 0 }}
              />
              pin version
            </label>
          </div>

          <div style={{ overflowY: 'auto', flex: 1 }}>
            {loading && (
              <div className="dim" style={{ padding: '12px 14px', fontSize: 12 }}>loading…</div>
            )}
            {!loading && items.length === 0 && (
              <div className="dim" style={{ padding: '12px 14px', fontSize: 12 }}>no resources found</div>
            )}
            {!loading && items.map((item) => (
              <div
                key={`${item.id}@${item.version}`}
                onClick={() => pick(item)}
                style={{
                  padding: '8px 14px',
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 2,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-elevated)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = '')}
              >
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--fg)' }}>{item.name}</span>
                  <span className="pill" style={{ fontSize: 10, padding: '1px 6px' }}>{item.kind}</span>
                  <span className="dim" style={{ fontSize: 10, marginLeft: 'auto' }}>v{item.version}</span>
                </div>
                {item.description && (
                  <span className="dim" style={{ fontSize: 11 }}>{item.description}</span>
                )}
                {item.tags.length > 0 && (
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {item.tags.map((t) => (
                      <span key={t} className="tag">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
