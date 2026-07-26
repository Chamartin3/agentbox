import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, AgentDef } from '../../api/client';
import { subagentsApi, WorkspaceSubagent } from '../../api/repo';
import EntityPickerModal from '../common/EntityPickerModal';

interface Row {
  agent_id: string;
  alias: string;
  name: string | null;
  description: string | null;
}

function defaultAlias(agentId: string, taken: Set<string>): string {
  const base = agentId.replace(/[^a-zA-Z0-9_-]/g, '_');
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}

// Subagents assigned to this workspace, shown as cards (mirrors Skills).
// Add/remove persists immediately; alias edits persist on blur.
export default function SubagentsEditor({ workspaceId }: { workspaceId: string }) {
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [all, current] = await Promise.all([
        api.listAgents(),
        subagentsApi.list(workspaceId),
      ]);
      setAgents(all);
      setRows(
        current.items
          .slice()
          .sort((a: WorkspaceSubagent, b: WorkspaceSubagent) => a.display_order - b.display_order)
          .map((s) => ({
            agent_id: s.agent_id,
            alias: s.alias,
            name: s.agent_name ?? null,
            description: s.agent_description ?? null,
          })),
      );
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [workspaceId]);

  const persist = async (next: Row[]) => {
    setBusy(true);
    try {
      await subagentsApi.replace(
        workspaceId,
        next.map((r, idx) => ({ agent_id: r.agent_id, alias: r.alias.trim(), display_order: idx })),
      );
      await load();
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy(false);
    }
  };

  const add = (agentId: string) => {
    setAdding(false);
    if (rows.some((r) => r.agent_id === agentId)) return;
    const taken = new Set(rows.map((r) => r.alias));
    const agent = agents.find((a) => a.id === agentId);
    void persist([
      ...rows,
      { agent_id: agentId, alias: defaultAlias(agentId, taken), name: agentId, description: agent?.description ?? null },
    ]);
  };

  const remove = (agentId: string) => void persist(rows.filter((r) => r.agent_id !== agentId));

  const commitAlias = (agentId: string, alias: string) => {
    const trimmed = alias.trim();
    const row = rows.find((r) => r.agent_id === agentId);
    if (!row || row.alias === trimmed) return;
    if (!trimmed) { void load(); return; } // revert empty
    if (rows.some((r) => r.agent_id !== agentId && r.alias === trimmed)) {
      alert('Aliases must be unique within the workspace.');
      void load();
      return;
    }
    void persist(rows.map((r) => (r.agent_id === agentId ? { ...r, alias: trimmed } : r)));
  };

  if (loading) return <section className="section"><p className="dim">loading subagents…</p></section>;

  const assignedIds = new Set(rows.map((r) => r.agent_id));
  const available = agents.filter((a) => !assignedIds.has(a.id));

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Subagents ({rows.length})</h3>
        <button onClick={() => setAdding(true)} disabled={busy}>+ add subagent</button>
      </div>

      {error && <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>}

      {rows.length === 0 ? (
        <p className="dim">No subagents assigned.</p>
      ) : (
        <div className="entity-grid">
          {rows.map((r) => (
            <div key={r.agent_id} className="entity-card">
              <div className="row between" style={{ gap: 8 }}>
                <Link to={`/agents/${encodeURIComponent(r.agent_id)}`} className="entity-card-name">
                  {r.name || r.agent_id}
                </Link>
                <button
                  className="link-btn"
                  style={{ color: 'crimson', fontSize: 11 }}
                  onClick={() => remove(r.agent_id)}
                  disabled={busy}
                >
                  remove
                </button>
              </div>
              {r.description && <div className="dim entity-card-desc">{r.description}</div>}
              <label className="row" style={{ gap: 6, marginTop: 6, fontSize: 11 }}>
                <span className="dim">alias</span>
                <input
                  type="text"
                  defaultValue={r.alias}
                  onBlur={(e) => commitAlias(r.agent_id, e.target.value)}
                  style={{ padding: '2px 6px', fontSize: 11, flex: 1 }}
                />
              </label>
            </div>
          ))}
        </div>
      )}

      {adding && (
        <EntityPickerModal
          title="Add subagent"
          items={available.map((a) => ({ id: a.id, name: a.id, description: a.description }))}
          onPick={add}
          onClose={() => setAdding(false)}
        />
      )}
    </section>
  );
}
