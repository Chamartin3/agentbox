import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, AgentDef, RunnerProfile } from '../api/client';
import { AgentSortKey, SortDir } from '../api/enums';

function PromptDrawer({ agent, onClose }: { agent: AgentDef; onClose: () => void }) {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getAgent(agent.id)
      .then((r) => setPrompt(r.prompt || ''))
      .catch(() => setPrompt(''))
      .finally(() => setLoading(false));
  }, [agent.id]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <strong>{agent.id}</strong>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--fg-muted)' }}>✕</button>
        </div>
        {agent.description && (
          <p className="dim" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>{agent.description}</p>
        )}
        <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
          <span className="tag">{agent.runner.kind}</span>
          {agent.runner.model && <span className="tag">{agent.runner.model}</span>}
          {agent.workspace && <span className="tag">{agent.workspace}</span>}
        </div>
        <div className="code-block">
          <div className="code-block-bar">
            <span className="dim" style={{ fontSize: 11 }}>system prompt</span>
            {agent.prompt_path && (
              <span className="dim" style={{ fontSize: 11 }}>{agent.prompt_path}</span>
            )}
          </div>
          {loading
            ? <pre style={{ padding: '12px 14px', margin: 0, color: 'var(--fg-muted)', fontSize: 12 }}>loading…</pre>
            : prompt
              ? <pre style={{ padding: '12px 14px', margin: 0, whiteSpace: 'pre', wordBreak: 'normal', fontSize: 12, maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>{prompt}</pre>
              : <pre style={{ padding: '12px 14px', margin: 0, color: 'var(--fg-muted)', fontSize: 12 }}>no prompt</pre>
          }
        </div>
        <div style={{ marginTop: 14, textAlign: 'right' }}>
          <Link to={`/agents/${agent.id}`} style={{ fontSize: 13 }}>open full detail →</Link>
        </div>
      </div>
    </div>
  );
}

type SortKey = Exclude<AgentSortKey, 'last_run'>;

const PAGE_SIZE = 20;

function formatUpdated(s?: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [profiles, setProfiles] = useState<RunnerProfile[]>([]);
  const [savingProfile, setSavingProfile] = useState<string | null>(null);
  const [selected, setSelected] = useState<AgentDef | null>(null);
  const [query, setQuery] = useState('');
  const [runnerFilter, setRunnerFilter] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>(AgentSortKey.UpdatedAt);
  const [sortDir, setSortDir] = useState<SortDir>(SortDir.Desc);
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.listAgents().then(setAgents).catch(console.error);
    api.listRunnerProfiles().then(setProfiles).catch(console.error);
  }, []);

  const onChangeProfile = async (agentId: string, profileId: string) => {
    setSavingProfile(agentId);
    try {
      if (profileId) {
        await api.setAgentRunnerProfile(agentId, profileId);
      } else {
        await api.clearAgentRunnerProfile(agentId);
      }
      setAgents((prev) =>
        prev.map((a) =>
          a.id === agentId ? { ...a, runner_profile_id: profileId || null } : a,
        ),
      );
    } catch (e) {
      console.error(e);
    } finally {
      setSavingProfile(null);
    }
  };

  const runnerKinds = Array.from(new Set(agents.map((a) => a.runner.kind))).sort();

  const filtered = agents.filter((a) => {
    if (runnerFilter && a.runner.kind !== runnerFilter) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      a.id.toLowerCase().includes(q) ||
      (a.description || '').toLowerCase().includes(q) ||
      (a.runner.model || '').toLowerCase().includes(q) ||
      (a.tags || []).some((t) => t.toLowerCase().includes(q))
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    const dir = sortDir === SortDir.Asc ? 1 : -1;
    const pick = (x: AgentDef): string | null =>
      sortKey === AgentSortKey.Id ? x.id
      : sortKey === AgentSortKey.Runner ? x.runner.kind
      : sortKey === AgentSortKey.Model ? (x.runner.model || null)
      : (x.last_activity_at || x.updated_at || null);
    const av = pick(a);
    const bv = pick(b);
    if (av == null && bv == null) return a.id.localeCompare(b.id);
    if (av == null) return 1;
    if (bv == null) return -1;
    return av < bv ? -dir : av > bv ? dir : a.id.localeCompare(b.id);
  });

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function toggleSort(k: SortKey) {
    if (sortKey === k) setSortDir(sortDir === SortDir.Asc ? SortDir.Desc : SortDir.Asc);
    else { setSortKey(k); setSortDir(k === AgentSortKey.UpdatedAt ? SortDir.Desc : SortDir.Asc); }
    setPage(1);
  }

  const ind = (k: SortKey) => sortKey === k ? (sortDir === SortDir.Asc ? ' ▲' : ' ▼') : '';

  return (
    <div className="stack">
      <h1>Agents</h1>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="search id, description, model, tag…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPage(1); }}
          style={{ flex: '1 1 260px', padding: '6px 10px', fontSize: 13 }}
        />
        <select
          value={runnerFilter}
          onChange={(e) => { setRunnerFilter(e.target.value); setPage(1); }}
          style={{ padding: '6px 10px', fontSize: 13 }}
        >
          <option value="">all runners</option>
          {runnerKinds.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <span className="dim" style={{ fontSize: 12 }}>{sorted.length} of {agents.length}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort(AgentSortKey.Id)}>ID{ind(AgentSortKey.Id)}</th>
            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort(AgentSortKey.Runner)}>Runner{ind(AgentSortKey.Runner)}</th>
            <th>Profile</th>
            <th>Session</th>
            <th>Workspace</th>
            <th>Description</th>
            <th>v</th>
            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort(AgentSortKey.UpdatedAt)}>Last activity{ind(AgentSortKey.UpdatedAt)}</th>
            <th>Runs</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((a) => (
            <tr
              key={a.id}
              style={{ cursor: 'pointer' }}
              onClick={() => setSelected(a)}
            >
              <td onClick={(e) => e.stopPropagation()}>
                <Link to={`/agents/${a.id}`}><strong>{a.id}</strong></Link>
              </td>
              <td><span className="tag">{a.runner.kind}</span></td>
              <td onClick={(e) => e.stopPropagation()}>
                <select
                  value={a.runner_profile_id || ''}
                  disabled={savingProfile === a.id}
                  onChange={(e) => void onChangeProfile(a.id, e.target.value)}
                  style={{ fontSize: 12, maxWidth: 220 }}
                  title={a.runner_profile_id || 'system default'}
                >
                  <option value="">— system default —</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}{p.model ? ` · ${p.model}` : ''}
                    </option>
                  ))}
                </select>
              </td>
              <td className="dim">{a.session_mode}</td>
              <td className="dim">
                {a.workspace === '<ephemeral>'
                  ? <span className="pill eph">ephemeral</span>
                  : (a.workspace || <span className="dim">auto</span>)}
              </td>
              <td>{a.description}</td>
              <td onClick={(e) => e.stopPropagation()} className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                {a.version != null ? (
                  <Link to={`/agents/${a.id}/versions`} title="prompt versions">v{a.version}</Link>
                ) : '—'}
              </td>
              <td className="dim" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>
                {formatUpdated(a.last_activity_at || a.updated_at)}
              </td>
              <td onClick={(e) => e.stopPropagation()} style={{ textAlign: 'right' }}>
                <Link to={`/runs?agent=${encodeURIComponent(a.id)}`} title="view runs">
                  {a.run_count ?? 0}
                </Link>
              </td>
            </tr>
          ))}
          {pageRows.length === 0 && (
            <tr><td colSpan={9} className="dim" style={{ textAlign: 'center', padding: 24 }}>no agents match</td></tr>
          )}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
          <button onClick={() => setPage(Math.max(1, safePage - 1))} disabled={safePage === 1}>← prev</button>
          <span className="dim" style={{ fontSize: 12 }}>page {safePage} / {totalPages}</span>
          <button onClick={() => setPage(Math.min(totalPages, safePage + 1))} disabled={safePage === totalPages}>next →</button>
        </div>
      )}

      {selected && (
        <PromptDrawer agent={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
