import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest as api } from '../../api/http';
import EntityPickerModal from '../common/EntityPickerModal';

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

// Skills bound to this workspace, shown as cards. Add/remove persists
// immediately (the PUT takes the full id set).
export default function WorkspaceSkillsEditor({ workspaceId }: Props) {
  const [items, setItems] = useState<SkillRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const url = `/api/workspaces/${encodeURIComponent(workspaceId)}/skill-bindings`;

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{ items: SkillRow[] }>(url);
      setItems(data.items);
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

  const bound = items.filter((r) => r.bound);
  const available = items.filter((r) => !r.bound);

  const persist = async (ids: string[]) => {
    setBusy(true);
    try {
      await api(url, { method: 'PUT', body: JSON.stringify({ skill_resource_ids: ids }) });
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const add = (id: string) => {
    setAdding(false);
    void persist([...bound.map((r) => r.id), id]);
  };
  const remove = (id: string) => void persist(bound.filter((r) => r.id !== id).map((r) => r.id));

  if (loading) return <section className="section"><p className="dim">loading skills…</p></section>;

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Skills ({bound.length})</h3>
        <button onClick={() => setAdding(true)} disabled={busy}>+ add skill</button>
      </div>

      {error && <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>}

      {bound.length === 0 ? (
        <p className="dim">No skills added.</p>
      ) : (
        <div className="entity-grid">
          {bound.map((r) => (
            <div key={r.id} className="entity-card">
              <div className="row between" style={{ gap: 8 }}>
                <Link to={`/workspaces/resources/${r.id}`} className="entity-card-name">
                  {r.display_name}
                </Link>
                <button
                  className="link-btn"
                  style={{ color: 'crimson', fontSize: 11 }}
                  onClick={() => remove(r.id)}
                  disabled={busy}
                >
                  remove
                </button>
              </div>
              {r.description && <div className="dim entity-card-desc">{r.description}</div>}
            </div>
          ))}
        </div>
      )}

      {adding && (
        <EntityPickerModal
          title="Add skill"
          items={available.map((r) => ({ id: r.id, name: r.display_name, description: r.description }))}
          onPick={add}
          onClose={() => setAdding(false)}
        />
      )}
    </section>
  );
}
