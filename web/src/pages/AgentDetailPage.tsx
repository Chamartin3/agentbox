import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  api,
  AgentDef,
  ApiError,
  PromptVersionSummary,
  RunRecord,
} from '../api/client';
import MarkdownEditor from '../components/MarkdownEditor';
import ManifestEditor from '../components/ManifestEditor';
import AgentToolsEditor from '../components/AgentToolsEditor';
import Toast from '../components/Toast';
import { activityApi, AgentRun } from '../api/activity';

export default function AgentDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [agentLoaded, setAgentLoaded] = useState(false);
  const [prompt, setPrompt] = useState<string>('');
  const [promptDirty, setPromptDirty] = useState(false);
  const [versions, setVersions] = useState<PromptVersionSummary[]>([]);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [changelog, setChangelog] = useState('');
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [activityRuns, setActivityRuns] = useState<AgentRun[]>([]);

  const flash = (kind: 'ok' | 'error', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  const loadAgent = async () => {
    try {
      const list = await api.listAgents();
      const a = list.find((x) => x.id === id) || null;
      setAgent(a);
    } catch (e) {
      console.error(e);
    } finally {
      setAgentLoaded(true);
    }
  };

  const loadPrompt = async () => {
    if (!id) return;
    setLoadingPrompt(true);
    try {
      const doc = await api.getPrompt(id);
      setPrompt(doc.content);
      setPromptDirty(false);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 400) {
        setPrompt('');
      } else {
        console.error(e);
      }
    } finally {
      setLoadingPrompt(false);
    }
  };

  const loadVersions = async () => {
    if (!id) return;
    setLoadingVersions(true);
    try {
      const data = await api.listPromptVersions(id);
      setVersions(data.versions);
      setActiveVersion(data.active_version);
      setDraftVersion(data.draft_version);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 404) {
        // Agent has no prompt_path — ignore.
      } else {
        console.error(e);
      }
    } finally {
      setLoadingVersions(false);
    }
  };

  const loadRuns = async () => {
    if (!id) return;
    setRunsLoading(true);
    try {
      const [rows, activity] = await Promise.all([
        api.listRuns(id),
        activityApi
          .runs({ range: '30d', action: id, limit: 200 })
          .catch(() => ({ results: [] as AgentRun[], total: 0 })),
      ]);
      setRuns(rows);
      setActivityRuns(activity.results);
    } catch (e) {
      console.error(e);
    } finally {
      setRunsLoading(false);
    }
  };

  useEffect(() => {
    loadAgent();
    loadPrompt();
    loadVersions();
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Cmd/Ctrl-S saves a draft.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (promptDirty) saveDraft();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promptDirty, prompt]);

  const saveDraft = async () => {
    if (!id) return;
    try {
      const doc = await api.savePromptDraft(id, prompt);
      setPrompt(doc.content);
      setPromptDirty(false);
      flash('ok', `draft saved (v${doc.mtime ? 'draft' : ''})`);
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `draft save failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const publish = async () => {
    if (!id) return;
    try {
      const doc = await api.publishPrompt(id, changelog);
      setPrompt(doc.content);
      setPromptDirty(false);
      setChangelog('');
      flash('ok', `published v${doc.mtime} (${doc.size} bytes)`);
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `publish failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const rollback = async (targetVersion: number) => {
    if (!id) return;
    try {
      const doc = await api.rollbackPrompt(id, targetVersion);
      setPrompt(doc.content);
      setPromptDirty(false);
      flash('ok', `rolled back to v${targetVersion} → new v${doc.mtime}`);
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `rollback failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const loadVersionContent = async (version: number) => {
    if (!id) return;
    setLoadingPrompt(true);
    try {
      const data = await api.getPromptVersion(id, version);
      setPrompt(data.content);
      setPromptDirty(false);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingPrompt(false);
    }
  };

  const stats = useMemo(() => computeRunStats(runs), [runs]);
  const dailySeries = useMemo(() => buildDailySeries(runs, 14), [runs]);
  const tokenSeries = useMemo(() => buildTokenSeries(activityRuns, 14), [activityRuns]);
  const tokenTotals = useMemo(() => sumTokens(activityRuns), [activityRuns]);

  if (!agent) {
    if (!agentLoaded) return <p className="dim">loading…</p>;
    return (
      <div className="stack">
        <h1>
          <Link to="/agents" className="dim">agents</Link> / {id}
        </h1>
        <p className="dim">
          No agent with id <code>{id}</code> is registered. It may be missing
          from <code>bin/agentbox_sync.py</code>'s <code>ACTIVE_AGENTS</code>{' '}
          list, or the agentbox container needs a restart after a sync.
        </p>
        <p className="dim">
          <Link to="/agents">← back to agents</Link>
        </p>
      </div>
    );
  }

  const hasDraft = draftVersion !== null;

  return (
    <div className="stack">
      <div className="row between">
        <h1>
          <Link to="/agents" className="dim">agents</Link> / {agent.id}
        </h1>
        <span className="dim">
          <Link to={`/runs?agent=${encodeURIComponent(agent.id)}`}>view runs →</Link>
          {' · '}
          {agent.description}
        </span>
      </div>

      <ManifestEditor
        agent={agent}
        onSaved={(updated) => {
          setAgent(updated);
          flash('ok', 'manifest updated');
        }}
        onError={(msg) => flash('error', msg)}
      />

      {/* Run dashboard */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 style={{ border: 'none', margin: 0 }}>Runs</h2>
          <span className="dim" style={{ fontSize: 12 }}>
            <button onClick={loadRuns} disabled={runsLoading} style={{ fontSize: 12, marginRight: 8 }}>
              {runsLoading ? 'loading…' : 'refresh'}
            </button>
            <Link to={`/runs?agent=${encodeURIComponent(agent.id)}`}>open runs page →</Link>
          </span>
        </div>

        {runs.length === 0 ? (
          <p className="dim" style={{ margin: 0 }}>
            {runsLoading ? 'loading runs…' : 'no runs recorded for this agent yet'}
          </p>
        ) : (
          <>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: 8,
                marginBottom: 12,
              }}
            >
              <StatTile label="Total" value={String(stats.total)} />
              <StatTile label="Success" value={String(stats.ok)} tone="ok" />
              <StatTile label="Errors" value={String(stats.error)} tone="error" />
              <StatTile label="Running" value={String(stats.running)} tone="running" />
              <StatTile
                label="Success rate"
                value={stats.total ? `${stats.successRate.toFixed(0)}%` : '—'}
              />
              <StatTile label="Avg duration" value={fmtMs(stats.avgDurationMs)} />
              <StatTile label="P95 duration" value={fmtMs(stats.p95DurationMs)} />
              <StatTile label="Last run" value={fmtRelative(stats.lastRunAt)} />
              <StatTile label="Tokens (30d)" value={fmtNum(tokenTotals.total)} />
              <StatTile label="In tokens" value={fmtNum(tokenTotals.input)} />
              <StatTile label="Out tokens" value={fmtNum(tokenTotals.output)} />
            </div>

            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailySeries} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                  <XAxis dataKey="label" stroke="#8b949e" fontSize={11} />
                  <YAxis allowDecimals={false} stroke="#8b949e" fontSize={11} />
                  <Tooltip
                    contentStyle={{
                      background: '#161b22',
                      border: '1px solid #30363d',
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="ok" stackId="s" fill="#3fb950" name="ok" />
                  <Bar dataKey="error" stackId="s" fill="#f85149" name="error" />
                  <Bar dataKey="running" stackId="s" fill="#d29922" name="running" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {tokenTotals.total > 0 && (
              <div style={{ height: 180, marginTop: 8 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tokenSeries} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                    <XAxis dataKey="label" stroke="#8b949e" fontSize={11} />
                    <YAxis allowDecimals={false} stroke="#8b949e" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        background: '#161b22',
                        border: '1px solid #30363d',
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="input" stackId="t" fill="#58a6ff" name="input tokens" />
                    <Bar dataKey="output" stackId="t" fill="#bc8cff" name="output tokens" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            <div style={{ marginTop: 12 }}>
              <h3 style={{ marginTop: 0, fontSize: 13 }} className="dim">
                Recent runs
              </h3>
              <table style={{ fontSize: 12, width: '100%' }}>
                <thead>
                  <tr className="dim">
                    <th style={{ textAlign: 'left' }}>When</th>
                    <th style={{ textAlign: 'left' }}>Status</th>
                    <th style={{ textAlign: 'right' }}>Duration</th>
                    <th style={{ textAlign: 'left' }}>Run</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.slice(0, 8).map((r) => (
                    <tr key={r.id}>
                      <td className="dim">{fmtRelative(r.created_at)}</td>
                      <td>
                        <span className={`pill ${statusPillClass(r.status)}`}>{r.status}</span>
                      </td>
                      <td style={{ textAlign: 'right' }}>{fmtMs(durationMs(r))}</td>
                      <td>
                        <Link to={`/runs/${r.id}`} style={{ fontSize: 12 }}>
                          {r.id.slice(0, 8)}…
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {/* Workspace section */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 style={{ border: 'none', margin: 0 }}>Workspace</h2>
          {agent.workspace ? (
            <Link to={`/workspaces/${agent.workspace}`}>open workspace →</Link>
          ) : (
            <span className="dim">no workspace assigned</span>
          )}
        </div>
        <p className="dim" style={{ margin: 0 }}>
          {agent.workspace || '(auto-resolved at run time)'}
        </p>
      </section>

      <AgentToolsEditor
        workspace={agent.workspace}
        onSaved={(msg) => flash('ok', msg)}
        onError={(msg) => flash('error', msg)}
      />

      <section className="section">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 style={{ border: 'none', margin: 0 }}>
            Prompt
            {agent.prompt_path && (
              <span className="dim" style={{ marginLeft: 8, fontSize: 12 }}>
                {agent.prompt_path}
              </span>
            )}
            {hasDraft && (
              <span
                className="pill"
                style={{
                  marginLeft: 8,
                  fontSize: 11,
                  background: '#fef3c7',
                  color: '#92400e',
                }}
              >
                draft v{draftVersion}
              </span>
            )}
            {promptDirty && (
              <span className="dirty" style={{ marginLeft: 8 }}>
                ● unsaved
              </span>
            )}
          </h2>
          <div className="row" style={{ gap: 8 }}>
            <button onClick={loadPrompt} disabled={loadingPrompt}>
              reload
            </button>
            <button onClick={saveDraft} disabled={!promptDirty}>
              save draft (⌘S)
            </button>
            <button
              className="primary"
              onClick={publish}
              disabled={!hasDraft}
              title={hasDraft ? 'Publish draft as new version' : 'No draft to publish'}
            >
              publish
            </button>
          </div>
        </div>

        {hasDraft && (
          <div className="row" style={{ marginBottom: 8, gap: 8 }}>
            <input
              type="text"
              placeholder="changelog (optional)"
              value={changelog}
              onChange={(e) => setChangelog(e.target.value)}
              style={{ flex: 1, padding: '4px 8px', fontSize: 13 }}
            />
          </div>
        )}

        {!agent.prompt_path ? (
          <p className="dim">
            This agent has no <code>prompt_path</code> — nothing to edit.
          </p>
        ) : (
          <MarkdownEditor
            value={prompt}
            onChange={(v) => {
              setPrompt(v);
              setPromptDirty(true);
            }}
          />
        )}
      </section>

      {versions.length > 0 && (
        <section className="section">
          <h3 style={{ marginTop: 0 }}>Versions</h3>
          {loadingVersions && <p className="dim">loading versions…</p>}
          <table style={{ fontSize: 13, width: '100%' }}>
            <thead>
              <tr className="dim">
                <th style={{ textAlign: 'left' }}>Ver</th>
                <th style={{ textAlign: 'left' }}>Status</th>
                <th style={{ textAlign: 'left' }}>Author</th>
                <th style={{ textAlign: 'left' }}>Changelog</th>
                <th style={{ textAlign: 'right' }}>Size</th>
                <th style={{ textAlign: 'left' }}>Date</th>
                <th style={{ textAlign: 'right' }}></th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr
                  key={v.version}
                  style={{
                    background:
                      v.version === activeVersion
                        ? '#ecfdf5'
                        : v.is_draft
                          ? '#fef3c7'
                          : 'transparent',
                  }}
                >
                  <td>v{v.version}</td>
                  <td>
                    {v.is_draft ? (
                      <span className="pill" style={{ background: '#fef3c7', color: '#92400e' }}>
                        draft
                      </span>
                    ) : v.version === activeVersion ? (
                      <span className="pill" style={{ background: '#d1fae5', color: '#065f46' }}>
                        active
                      </span>
                    ) : (
                      <span className="pill" style={{ background: '#f3f4f6', color: '#6b7280' }}>
                        committed
                      </span>
                    )}
                  </td>
                  <td>{v.author}</td>
                  <td className="dim">{v.changelog}</td>
                  <td style={{ textAlign: 'right' }}>{v.size}b</td>
                  <td className="dim">{new Date(v.created_at).toLocaleString()}</td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                      <button
                        onClick={() => loadVersionContent(v.version)}
                        style={{ fontSize: 12 }}
                      >
                        load
                      </button>
                      {!v.is_draft && v.version !== activeVersion && (
                        <button
                          onClick={() => rollback(v.version)}
                          style={{ fontSize: 12 }}
                        >
                          rollback
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard helpers
// ---------------------------------------------------------------------------

interface RunStats {
  total: number;
  ok: number;
  error: number;
  running: number;
  successRate: number;
  avgDurationMs: number | null;
  p95DurationMs: number | null;
  lastRunAt: string | null;
}

function durationMs(r: RunRecord): number | null {
  if (!r.finished_at) return null;
  const start = Date.parse(r.created_at);
  const end = Date.parse(r.finished_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

function computeRunStats(runs: RunRecord[]): RunStats {
  let ok = 0;
  let err = 0;
  let running = 0;
  const durations: number[] = [];
  let lastRunAt: string | null = null;
  for (const r of runs) {
    if (r.status === 'ok') ok += 1;
    else if (r.status === 'error') err += 1;
    else if (r.status === 'running') running += 1;
    const d = durationMs(r);
    if (d !== null) durations.push(d);
    if (!lastRunAt || Date.parse(r.created_at) > Date.parse(lastRunAt)) {
      lastRunAt = r.created_at;
    }
  }
  const total = runs.length;
  const terminal = ok + err;
  const successRate = terminal ? (ok / terminal) * 100 : 0;
  durations.sort((a, b) => a - b);
  const avg =
    durations.length === 0
      ? null
      : Math.round(durations.reduce((s, x) => s + x, 0) / durations.length);
  const p95 =
    durations.length === 0
      ? null
      : durations[Math.min(durations.length - 1, Math.floor(durations.length * 0.95))];
  return { total, ok, error: err, running, successRate, avgDurationMs: avg, p95DurationMs: p95, lastRunAt };
}

interface DayBucket {
  date: string;
  label: string;
  ok: number;
  error: number;
  running: number;
}

function buildDailySeries(runs: RunRecord[], days: number): DayBucket[] {
  const buckets = new Map<string, DayBucket>();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    buckets.set(key, {
      date: key,
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      ok: 0,
      error: 0,
      running: 0,
    });
  }
  for (const r of runs) {
    const key = r.created_at.slice(0, 10);
    const b = buckets.get(key);
    if (!b) continue;
    if (r.status === 'ok') b.ok += 1;
    else if (r.status === 'error') b.error += 1;
    else if (r.status === 'running') b.running += 1;
  }
  return Array.from(buckets.values());
}

interface TokenBucket {
  date: string;
  label: string;
  input: number;
  output: number;
}

function buildTokenSeries(rows: AgentRun[], days: number): TokenBucket[] {
  const buckets = new Map<string, TokenBucket>();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = days - 1; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    buckets.set(key, {
      date: key,
      label: `${d.getMonth() + 1}/${d.getDate()}`,
      input: 0,
      output: 0,
    });
  }
  for (const r of rows) {
    if (!r.started_at) continue;
    const key = r.started_at.slice(0, 10);
    const b = buckets.get(key);
    if (!b) continue;
    b.input += r.input_tokens || 0;
    b.output += r.output_tokens || 0;
  }
  return Array.from(buckets.values());
}

function sumTokens(rows: AgentRun[]): { input: number; output: number; total: number } {
  let input = 0;
  let output = 0;
  for (const r of rows) {
    input += r.input_tokens || 0;
    output += r.output_tokens || 0;
  }
  return { input, output, total: input + output };
}

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString();
}

function statusPillClass(status: RunRecord['status']): string {
  if (status === 'ok') return 'ok';
  if (status === 'error') return 'error';
  return 'running';
}

function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.round(s % 60);
  return `${m}m ${rs}s`;
}

function fmtRelative(iso: string | null): string {
  if (!iso) return '—';
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return '—';
  const diff = Date.now() - then;
  if (diff < 0) return 'in the future';
  const s = Math.floor(diff / 1000);
  if (s < 45) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

function StatTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'ok' | 'error' | 'running';
}) {
  const toneColor =
    tone === 'ok' ? '#3fb950' : tone === 'error' ? '#f85149' : tone === 'running' ? '#d29922' : undefined;
  return (
    <div
      style={{
        border: '1px solid #30363d',
        borderRadius: 4,
        padding: '8px 10px',
        background: '#0d1117',
      }}
    >
      <div className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>
        {label}
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: toneColor }}>{value}</div>
    </div>
  );
}
