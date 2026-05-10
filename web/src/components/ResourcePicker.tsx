import { useEffect, useMemo, useState } from 'react';
import { ApiError } from '../api/client';
import { repoApi, type RepoResource, type RepoType } from '../api/repo';

export interface ResourcePickerProps {
  /** When set, locks the type filter and switches to single-select (click-to-pick). */
  filterType?: RepoType | null;
  /** When set, types not in this list are hidden from the chip filter. */
  allowedTypes?: RepoType[];
  /** Resource IDs to hide from the list (already attached). */
  excludeIds?: Set<string>;
  /** Heading text shown in the modal header. Defaults derived from filterType. */
  title?: string;
  /** When true (and filterType is set), shows an "upload new" panel that
   *  creates a resource of `filterType` and an initial version. */
  allowUpload?: boolean;
  onPick: (rs: RepoResource[]) => void;
  onClose: () => void;
}

const ALL_TYPE_OPTIONS: RepoType[] = ['document', 'folder', 'skill', 'schema', 'script'];

function parseTags(t: string | null | undefined): string[] {
  if (!t) return [];
  return t.split(',').map((s) => s.trim()).filter(Boolean);
}

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: string } | string | undefined;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.detail === 'string') return d.detail;
    return `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}

export default function ResourcePicker({
  filterType,
  allowedTypes,
  excludeIds,
  title,
  allowUpload,
  onPick,
  onClose,
}: ResourcePickerProps) {
  const multi = !filterType;
  const typeOptions = allowedTypes ?? ALL_TYPE_OPTIONS;
  const PAGE_SIZE = 20;
  const [items, setItems] = useState<RepoResource[]>([]);
  const [q, setQ] = useState('');
  const [type, setType] = useState<RepoType | ''>(filterType ?? '');
  const [tagFilter, setTagFilter] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSlug, setUploadSlug] = useState('');
  const [uploadName, setUploadName] = useState('');
  const [uploading, setUploading] = useState(false);

  const onPickFile = (f: File | null) => {
    setUploadFile(f);
    if (f) {
      const base = f.name.replace(/\.[^.]+$/, '');
      if (!uploadSlug) setUploadSlug(base.replace(/[^a-zA-Z0-9_.-]+/g, '_').toLowerCase());
      if (!uploadName) setUploadName(base);
    }
  };

  const submitUpload = async () => {
    if (!filterType || !uploadFile || !uploadSlug.trim() || !uploadName.trim()) return;
    setUploading(true);
    setErr(null);
    try {
      const created = await repoApi.create({
        slug: uploadSlug.trim(),
        type: filterType,
        display_name: uploadName.trim(),
      });
      if (filterType === 'schema') {
        await repoApi.uploadSchema(created.id, uploadFile, 'initial upload');
      } else {
        await repoApi.uploadVersion(created.id, uploadFile, 'initial upload');
      }
      const fresh = await repoApi.get(created.id);
      onPick([fresh.resource]);
    } catch (e) {
      setErr(errMsg(e, 'upload failed'));
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    repoApi
      .list({ q: q || undefined, type: (type as RepoType) || undefined, limit: 500 })
      .then((p) => { if (!cancelled) setItems(p.items); })
      .catch((e) => { if (!cancelled) { setItems([]); setErr(errMsg(e, 'failed to load resources')); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [q, type]);

  useEffect(() => { setPage(0); }, [q, type, tagFilter]);

  const visible = useMemo(() => {
    let xs = items;
    if (allowedTypes && allowedTypes.length) xs = xs.filter((r) => allowedTypes.includes(r.type));
    if (excludeIds && excludeIds.size) xs = xs.filter((r) => !excludeIds.has(r.id));
    if (tagFilter.size) {
      xs = xs.filter((r) => {
        const tags = parseTags(r.tags);
        for (const t of tagFilter) if (!tags.includes(t)) return false;
        return true;
      });
    }
    return xs;
  }, [items, allowedTypes, excludeIds, tagFilter]);

  const totalPages = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages - 1);
  const pagedItems = visible.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  const tagCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of items) for (const t of parseTags(r.tags)) m.set(t, (m.get(t) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  }, [items]);

  const toggleSel = (id: string) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const toggleTag = (t: string) => {
    setTagFilter((s) => {
      const n = new Set(s);
      if (n.has(t)) n.delete(t); else n.add(t);
      return n;
    });
  };

  const selectAllVisible = () => setSelected(new Set(visible.map((r) => r.id)));
  const clearSelection = () => setSelected(new Set());

  const submit = () => {
    if (multi) {
      const picked = items.filter((r) => selected.has(r.id));
      if (picked.length) onPick(picked);
    }
  };

  const onRowClick = (r: RepoResource) => {
    if (multi) toggleSel(r.id);
    else onPick([r]);
  };

  const heading = title ?? (filterType ? `Pick ${filterType}` : 'Add resources');

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === 'Escape') onClose();
        if (e.key === 'Enter' && multi && selected.size) submit();
      }}
    >
      <div
        style={{
          background: 'var(--bg, #1a1a1a)', borderRadius: 6,
          width: 'min(640px, 92vw)', maxHeight: '80vh',
          display: 'flex', flexDirection: 'column',
          border: '1px solid var(--border, #333)',
          boxSizing: 'border-box', overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            padding: 12, borderBottom: '1px solid var(--border, #333)',
            display: 'flex', flexDirection: 'column', gap: 8,
            background: 'var(--bg, #1a1a1a)',
          }}
        >
          <div className="row between" style={{ alignItems: 'center' }}>
            <h3 style={{ margin: 0, fontSize: 14 }}>{heading}</h3>
            <div className="row" style={{ gap: 6 }}>
              {allowUpload && filterType && (
                <button onClick={() => setShowUpload((v) => !v)} style={{ fontSize: 11 }}>
                  {showUpload ? 'cancel upload' : '+ upload new'}
                </button>
              )}
              <button onClick={onClose} style={{ fontSize: 11 }}>close</button>
            </div>
          </div>

          {showUpload && filterType && (
            <div
              style={{
                border: '1px solid var(--border, #333)', borderRadius: 4,
                padding: 8, display: 'flex', flexDirection: 'column', gap: 6,
                background: 'var(--bg-soft, #111)',
              }}
            >
              <div className="dim" style={{ fontSize: 11 }}>
                Upload a new {filterType}. A slug and display name are required.
              </div>
              <input
                type="file"
                onChange={(e) => onPickFile(e.target.files?.[0] ?? null)}
                style={{ fontSize: 11 }}
              />
              <input
                placeholder="slug (e.g. drafting/output_v3)"
                value={uploadSlug}
                onChange={(e) => setUploadSlug(e.target.value)}
                style={{ padding: '4px 8px', fontSize: 12 }}
              />
              <input
                placeholder="display name"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                style={{ padding: '4px 8px', fontSize: 12 }}
              />
              <div className="row" style={{ justifyContent: 'flex-end' }}>
                <button
                  className="primary"
                  onClick={submitUpload}
                  disabled={!uploadFile || !uploadSlug.trim() || !uploadName.trim() || uploading}
                  style={{ fontSize: 11 }}
                >
                  {uploading ? 'uploading…' : `Create & pick`}
                </button>
              </div>
            </div>
          )}

          <input
            placeholder="search name, slug, tags…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ padding: '6px 10px', width: '100%', boxSizing: 'border-box' }}
            autoFocus
          />

          {!filterType && (
            <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
              <button
                onClick={() => setType('')}
                className={type === '' ? 'primary' : ''}
                style={{ fontSize: 11, padding: '2px 8px' }}
              >
                all
              </button>
              {typeOptions.map((t) => (
                <button
                  key={t}
                  onClick={() => setType(type === t ? '' : t)}
                  className={type === t ? 'primary' : ''}
                  style={{ fontSize: 11, padding: '2px 8px' }}
                >
                  {t}
                </button>
              ))}
            </div>
          )}

          {tagCounts.length > 0 && (
            <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
              {tagCounts.map(([t, n]) => (
                <button
                  key={t}
                  onClick={() => toggleTag(t)}
                  className={tagFilter.has(t) ? 'primary' : ''}
                  style={{ fontSize: 10, padding: '1px 6px' }}
                  title={`${n} resource(s) tagged ${t}`}
                >
                  #{t} <span className="dim">{n}</span>
                </button>
              ))}
              {tagFilter.size > 0 && (
                <button
                  onClick={() => setTagFilter(new Set())}
                  style={{ fontSize: 10, padding: '1px 6px' }}
                >
                  clear tags
                </button>
              )}
            </div>
          )}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {err && <p style={{ color: 'crimson', fontSize: 12, padding: 12 }}>{err}</p>}
          {loading ? (
            <p className="dim" style={{ padding: 12 }}>loading…</p>
          ) : visible.length === 0 ? (
            <p className="dim" style={{ padding: 12 }}>no resources match</p>
          ) : (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {pagedItems.map((r) => {
                const isSelected = selected.has(r.id);
                const name = r.display_name || r.slug || r.id;
                return (
                  <li
                    key={r.id}
                    onClick={() => onRowClick(r)}
                    title={r.slug}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '6px 12px',
                      borderBottom: '1px solid var(--border, #2a2a2a)',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(80,150,255,0.18)' : 'transparent',
                      color: 'var(--fg, #eee)',
                      fontSize: 13,
                    }}
                  >
                    {multi && (
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSel(r.id)}
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          width: 14, height: 14, padding: 0, margin: 0,
                          flexShrink: 0, accentColor: 'var(--accent, #58a6ff)',
                        }}
                      />
                    )}
                    <span
                      style={{
                        fontSize: 10, color: 'var(--fg-muted, #888)',
                        flexShrink: 0, width: 56, textTransform: 'uppercase',
                      }}
                    >
                      {r.type || '?'}
                    </span>
                    <span
                      style={{
                        flex: 1, minWidth: 0, color: 'var(--fg, #eee)',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                    >
                      {name}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {!loading && visible.length > PAGE_SIZE && (
          <div
            style={{
              padding: '6px 12px', borderTop: '1px solid var(--border, #333)',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--bg, #1a1a1a)', fontSize: 11,
            }}
          >
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={currentPage === 0}
              style={{ fontSize: 11 }}
            >
              ← prev
            </button>
            <span className="dim" style={{ flex: 1, textAlign: 'center' }}>
              page {currentPage + 1} of {totalPages} · {visible.length} match{visible.length === 1 ? '' : 'es'}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={currentPage >= totalPages - 1}
              style={{ fontSize: 11 }}
            >
              next →
            </button>
          </div>
        )}

        {multi && (
          <div
            style={{
              padding: 10, borderTop: '1px solid var(--border, #333)',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--bg, #1a1a1a)',
            }}
          >
            <span className="dim" style={{ fontSize: 11, flex: 1 }}>
              {selected.size} selected
              {visible.length > 0 && ` · ${visible.length} match${visible.length === 1 ? '' : 'es'}`}
            </span>
            <button
              onClick={selectAllVisible}
              disabled={visible.length === 0}
              style={{ fontSize: 11 }}
              title="Select all matches across pages"
            >
              select all
            </button>
            <button
              onClick={clearSelection}
              disabled={selected.size === 0}
              style={{ fontSize: 11 }}
            >
              clear
            </button>
            <button
              onClick={submit}
              disabled={selected.size === 0}
              className="primary"
              style={{ fontSize: 11 }}
            >
              Add {selected.size || ''}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
