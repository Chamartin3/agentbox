import { useEffect, useMemo, useState } from 'react';
import { apiRequest as api } from '../../api/http';

interface SkillRow {
  id: string;
  slug: string;
  display_name: string;
  description: string | null;
  bound: boolean;
}

interface Props {
  workspaceId: string;
}

export default function WorkspaceSkillsEditor({ workspaceId }: Props) {
  const [items, setItems] = useState<SkillRow[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{ items: SkillRow[] }>(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/skill-bindings`,
      );
      setItems(data.items);
      setSelected(new Set(data.items.filter((r) => r.bound).map((r) => r.id)));
      setDirty(false);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setDirty(true);
  };

  const save = async () => {
    setBusy(true);
    try {
      await api(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/skill-bindings`,
        {
          method: 'PUT',
          body: JSON.stringify({ skill_resource_ids: Array.from(selected) }),
        },
      );
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (r) =>
        r.slug.toLowerCase().includes(q) ||
        r.display_name.toLowerCase().includes(q) ||
        (r.description ?? '').toLowerCase().includes(q),
    );
  }, [items, filter]);

  const boundCount = selected.size;
  const totalCount = items.length;

  if (loading) return <p className="dim">loading skills…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 2 }}>Skills</h3>
          <p className="dim" style={{ fontSize: 12, margin: 0 }}>
            Toggle skills to bind. Materialized into
            <code> .claude/skills/&lt;name&gt;/SKILL.md</code> on save.
          </p>
        </div>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span className="dim" style={{ fontSize: 11 }}>
            {boundCount} / {totalCount} bound
            {dirty && <span className="dirty"> · unsaved</span>}
          </span>
          <button
            onClick={() => void save()}
            disabled={!dirty || busy}
            className="primary"
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter skills…"
        style={{ width: '100%', marginBottom: 8 }}
      />

      {filtered.length === 0 ? (
        <p className="dim">
          {totalCount === 0
            ? 'No skill resources in the catalog. Import some via the resources page.'
            : 'No skills match the filter.'}
        </p>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 6,
            maxHeight: 360,
            overflow: 'auto',
          }}
        >
          {filtered.map((r) => {
            const checked = selected.has(r.id);
            return (
              <label
                key={r.id}
                className="row"
                style={{
                  gap: 8,
                  alignItems: 'flex-start',
                  padding: '6px 8px',
                  border: '1px solid var(--border)',
                  borderRadius: 4,
                  background: checked ? 'var(--bg-elevated)' : 'transparent',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(r.id)}
                  style={{ marginTop: 2 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 12 }}>
                    {r.display_name}
                  </div>
                  <div
                    className="dim"
                    style={{ fontSize: 10, wordBreak: 'break-all' }}
                  >
                    {r.slug}
                  </div>
                  {r.description && (
                    <div
                      className="dim"
                      style={{
                        fontSize: 11,
                        marginTop: 2,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                      }}
                    >
                      {r.description}
                    </div>
                  )}
                </div>
              </label>
            );
          })}
        </div>
      )}
    </section>
  );
}
