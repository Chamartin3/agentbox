import { useEffect, useState } from 'react';
import { api, AgentDef } from '../../api/client';
import { subagentsApi, WorkspaceSubagent } from '../../api/repo';

interface Row {
  agent_id: string;
  alias: string;
}

function defaultAlias(agentId: string, taken: Set<string>): string {
  const base = agentId.replace(/[^a-zA-Z0-9_-]/g, '_');
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}_${n}`)) n += 1;
  return `${base}_${n}`;
}

export default function SubagentsEditor({ workspaceId }: { workspaceId: string }) {
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState('');

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
          .map((s) => ({ agent_id: s.agent_id, alias: s.alias })),
      );
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [workspaceId]);

  const addRow = () => {
    if (!picker) return;
    if (rows.some((r) => r.agent_id === picker)) return;
    const taken = new Set(rows.map((r) => r.alias));
    setRows([...rows, { agent_id: picker, alias: defaultAlias(picker, taken) }]);
    setPicker('');
  };

  const removeRow = (i: number) => setRows(rows.filter((_, idx) => idx !== i));

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= rows.length) return;
    const next = rows.slice();
    [next[i], next[j]] = [next[j], next[i]];
    setRows(next);
  };

  const updateAlias = (i: number, alias: string) => {
    const next = rows.slice();
    next[i] = { ...next[i], alias };
    setRows(next);
  };

  const save = async () => {
    const aliases = rows.map((r) => r.alias.trim());
    if (aliases.some((a) => !a)) {
      alert('Every alias must be non-empty.');
      return;
    }
    if (new Set(aliases).size !== aliases.length) {
      alert('Aliases must be unique within the workspace.');
      return;
    }
    setBusy(true);
    try {
      await subagentsApi.replace(
        workspaceId,
        rows.map((r, idx) => ({ agent_id: r.agent_id, alias: r.alias.trim(), display_order: idx })),
      );
      await load();
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <section className="section"><p className="dim">loading subagents…</p></section>;

  const assignedIds = new Set(rows.map((r) => r.agent_id));
  const available = agents.filter((a) => !assignedIds.has(a.id));

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Subagents ({rows.length})</h3>
        <button onClick={save} disabled={busy} className="primary">
          {busy ? 'saving…' : 'save subagents'}
        </button>
      </div>
      <p className="dim" style={{ fontSize: 11, marginTop: 0 }}>
        Composed agents rendered into <code>.claude/agents/</code>, <code>.opencode/agents/</code>, and <code>.codex/agents/</code> on next config generation.
      </p>

      {error && <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>}

      {rows.length === 0 ? (
        <p className="dim">No subagents assigned.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Order</th>
              <th style={{ textAlign: 'left' }}>Agent</th>
              <th style={{ textAlign: 'left' }}>Alias</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.agent_id}>
                <td style={{ width: 80 }}>
                  <div className="row" style={{ gap: 2 }}>
                    <button onClick={() => move(i, -1)} disabled={i === 0} title="up">↑</button>
                    <button onClick={() => move(i, 1)} disabled={i === rows.length - 1} title="down">↓</button>
                  </div>
                </td>
                <td><code>{r.agent_id}</code></td>
                <td>
                  <input
                    type="text"
                    value={r.alias}
                    onChange={(e) => updateAlias(i, e.target.value)}
                    style={{ padding: '4px 8px', fontSize: 12, width: '100%' }}
                  />
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button onClick={() => removeRow(i)} style={{ color: 'crimson', fontSize: 11 }}>remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="row" style={{ gap: 8, marginTop: 12, alignItems: 'center' }}>
        <select
          value={picker}
          onChange={(e) => setPicker(e.target.value)}
          style={{ padding: '6px 10px', fontSize: 12, flex: '1 1 240px' }}
        >
          <option value="">+ add agent…</option>
          {available.map((a) => (
            <option key={a.id} value={a.id}>{a.id}</option>
          ))}
        </select>
        <button onClick={addRow} disabled={!picker}>add</button>
      </div>
    </section>
  );
}
