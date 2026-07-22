import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AgentDef, type RunnerProfile } from '../api/client';
import { AgentSortKey, SortDir } from '../api/enums';
import { useAgent, useAgents, useAgentActions } from '../hooks/agents';
import { useRunnerProfiles } from '../hooks/runnerProfiles';
import RunnerProfilePickerModal from '../components/runner/RunnerProfilePickerModal';
import { ProfileDisplay } from '../components/runner/ProfileDisplay';

function PromptDrawer({ agent, onClose }: { agent: AgentDef; onClose: () => void }) {
  const { data, loading } = useAgent(agent.id);
  const prompt = data?.prompt ?? '';

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
          {agent.model && <span className="tag">{agent.model}</span>}
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
  const [query, setQuery] = useState('');
  const [runnerFilter, setRunnerFilter] = useState('');
  const [includeDisabled, setIncludeDisabled] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>(AgentSortKey.UpdatedAt);
  const [sortDir, setSortDir] = useState<SortDir>(SortDir.Desc);
  const [page, setPage] = useState(1);
  const [savingProfile, setSavingProfile] = useState<string | null>(null);
  const [togglingDisabled, setTogglingDisabled] = useState<string | null>(null);
  const [selected, setSelected] = useState<AgentDef | null>(null);
  const [profileModalAgent, setProfileModalAgent] = useState<AgentDef | null>(null);

  const agentsQ = useAgents({ includeDisabled });
  const profilesQ = useRunnerProfiles();
  const agents = agentsQ.data ?? [];
  const profiles = profilesQ.data ?? [];
  const actions = useAgentActions();

  const onToggleDisabled = async (a: AgentDef) => {
    setTogglingDisabled(a.id);
    try {
      if (a.disabled_at) await actions.enable(a.id);
      else await actions.disable(a.id);
      await agentsQ.refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setTogglingDisabled(null);
    }
  };

  const onChangeProfile = async (agentId: string, profileId: string) => {
    setSavingProfile(agentId);
    try {
      if (profileId) await actions.setRunnerProfile(agentId, profileId);
      else await actions.clearRunnerProfile(agentId);
      await agentsQ.refresh();
      setProfileModalAgent(null);
    } catch (e) {
      console.error(e);
    } finally {
      setSavingProfile(null);
    }
  };

  const profileById = (id: string | null | undefined): RunnerProfile | undefined =>
    id ? profiles.find((p) => p.id === id) : undefined;

  const runnerKinds = Array.from(new Set(agents.map((a) => a.runner.kind))).sort();

  const filtered = agents.filter((a) => {
    if (runnerFilter && a.runner.kind !== runnerFilter) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      a.id.toLowerCase().includes(q) ||
      (a.description || '').toLowerCase().includes(q) ||
      (a.model || '').toLowerCase().includes(q) ||
      (a.tags || []).some((t) => t.toLowerCase().includes(q))
    );
  });

  const sorted = [...filtered].sort((a, b) => {
    const dir = sortDir === SortDir.Asc ? 1 : -1;
    const pick = (x: AgentDef): string | null =>
      sortKey === AgentSortKey.Id ? x.id
      : sortKey === AgentSortKey.Runner ? x.runner.kind
      : sortKey === AgentSortKey.Model ? (x.model || null)
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
        <label style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 12 }}>
          <input
            type="checkbox"
            checked={includeDisabled}
            onChange={(e) => { setIncludeDisabled(e.target.checked); setPage(1); }}
          />
          include disabled
        </label>
        <span className="dim" style={{ fontSize: 12 }}>{sorted.length} of {agents.length}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort(AgentSortKey.Id)}>ID{ind(AgentSortKey.Id)}</th>
            <th>Runner profile</th>
            <th>Workspace</th>
            <th>Description</th>
            <th>v</th>
            <th style={{ cursor: 'pointer' }} onClick={() => toggleSort(AgentSortKey.UpdatedAt)}>Last activity{ind(AgentSortKey.UpdatedAt)}</th>
            <th>Runs</th>
            <th></th>
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
                {a.disabled_at && (
                  <span
                    className="pill"
                    title={`disabled at ${a.disabled_at}`}
                    style={{ marginLeft: 6, background: '#c0392b', color: '#fff', fontSize: 10 }}
                  >
                    disabled
                  </span>
                )}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                <button
                  className="profile-trigger"
                  disabled={savingProfile === a.id}
                  onClick={() => setProfileModalAgent(a)}
                  title="Change runner profile"
                >
                  <ProfileDisplay profile={profileById(a.runner_profile_id)} fallbackKind={a.runner.kind} compact />
                  <span className="profile-trigger-edit">✎</span>
                </button>
              </td>
              <td className="dim">
                {a.workspace && a.workspace !== '<ephemeral>'
                  ? a.workspace
                  : <span className="dim">default</span>}
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
              <td onClick={(e) => e.stopPropagation()} style={{ textAlign: 'right' }}>
                <button
                  onClick={() => void onToggleDisabled(a)}
                  disabled={togglingDisabled === a.id}
                  style={{ fontSize: 11 }}
                  title={a.disabled_at ? 'Re-enable agent' : 'Disable — prevents new runs'}
                >
                  {a.disabled_at ? 'Enable' : 'Disable'}
                </button>
              </td>
            </tr>
          ))}
          {pageRows.length === 0 && (
            <tr><td colSpan={8} className="dim" style={{ textAlign: 'center', padding: 24 }}>no agents match</td></tr>
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

      {profileModalAgent && (
        <RunnerProfilePickerModal
          boundId={profileModalAgent.runner_profile_id ?? null}
          busy={savingProfile === profileModalAgent.id}
          onPick={(id) => void onChangeProfile(profileModalAgent.id, id)}
          onCreated={(p) => void onChangeProfile(profileModalAgent.id, p.id)}
          onClose={() => setProfileModalAgent(null)}
        />
      )}
    </div>
  );
}
