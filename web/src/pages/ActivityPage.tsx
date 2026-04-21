import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  ActivityRange,
  ActivitySummary,
  AgentRun,
  AgentRunState,
  activityApi,
} from '../api/activity';
import RunDetailDrawer from '../components/RunDetailDrawer';

const RANGES: ActivityRange[] = ['7d', '30d', '90d'];

function fmtMs(ms: number | null | undefined): string {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rs = Math.round(s % 60);
  return `${m}m ${rs}s`;
}
function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString();
}
function fmtCost(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (n === 0) return '$0';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}
function fmtDateTick(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
function fmtRelative(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
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

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

function StatePill({ state }: { state: AgentRunState }) {
  const cls =
    state === 'running' ? 'running' :
    state === 'succeeded' ? 'ok' :
    state === 'timeout' ? 'eph' :
    'error';
  const label = state === 'succeeded' ? 'ok' : state === 'failed' ? 'fail' : state;
  return <span className={`pill ${cls}`}>{label}</span>;
}

export default function ActivityPage() {
  const [range, setRange] = useState<ActivityRange>('30d');
  const [actionFilter, setActionFilter] = useState('');
  const [executorFilter, setExecutorFilter] = useState('');
  const [stateFilter, setStateFilter] = useState<'' | AgentRunState>('');
  const [selected, setSelected] = useState<AgentRun | null>(null);
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, r] = await Promise.all([
        activityApi.summary({
          range,
          action: actionFilter || undefined,
          executor: executorFilter || undefined,
        }),
        activityApi.runs({
          range,
          action: actionFilter || undefined,
          executor: executorFilter || undefined,
          state: stateFilter || undefined,
          limit: 50,
        }),
      ]);
      setSummary(s);
      setRuns(r.results);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const h = setInterval(load, 8000);
    return () => clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, actionFilter, executorFilter, stateFilter]);

  const totals = summary?.totals;
  const rawSeries = summary?.series ?? [];
  const byAction = summary?.by_action ?? [];
  const byExecutor = summary?.by_executor ?? [];

  const series = useMemo(() => {
    const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
    const byDate = new Map(rawSeries.map((p) => [p.date, p]));
    const out: Array<{ date: string; runs: number; failures: number }> = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = days - 1; i >= 0; i -= 1) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const hit = byDate.get(key);
      out.push(hit ?? { date: key, runs: 0, failures: 0 });
    }
    return out;
  }, [rawSeries, range]);

  const actionOptions = useMemo(
    () => Array.from(new Set(byAction.map((b) => b.action_name))).sort(),
    [byAction],
  );
  const executorOptions = useMemo(
    () => Array.from(new Set(byExecutor.map((b) => b.executor))).sort(),
    [byExecutor],
  );

  return (
    <div className="stack">
      <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
        <div className="range-toggle">
          {RANGES.map((r) => (
            <button
              key={r}
              className={range === r ? 'active' : ''}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
        <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)}>
          <option value="">All actions</option>
          {actionOptions.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={executorFilter} onChange={(e) => setExecutorFilter(e.target.value)}>
          <option value="">All executors</option>
          {executorOptions.map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value as '' | AgentRunState)}
        >
          <option value="">All states</option>
          <option value="running">Running</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {error && <div className="toast error">{error}</div>}
      {loading && !summary ? (
        <p className="dim">Loading…</p>
      ) : (
        <>
          <div className="kpi-grid">
            <Kpi
              label="Runs"
              value={fmtNum(totals?.runs ?? 0)}
              sub={`${totals?.running ?? 0} running · ${totals?.successes ?? 0} ok · ${totals?.failures ?? 0} fail`}
            />
            <Kpi label="Failure rate" value={`${totals?.failure_rate_pct ?? 0}%`} />
            <Kpi
              label="Avg duration"
              value={fmtMs(totals?.avg_duration_ms ?? 0)}
              sub={`total ${fmtMs(totals?.total_duration_ms ?? 0)}`}
            />
            <Kpi
              label="Tokens"
              value={fmtNum((totals?.input_tokens ?? 0) + (totals?.output_tokens ?? 0))}
              sub={`in ${fmtNum(totals?.input_tokens ?? 0)} · out ${fmtNum(totals?.output_tokens ?? 0)}`}
            />
            <Kpi label="Cost" value={fmtCost(totals?.cost_usd ?? 0)} />
          </div>

          <section className="section">
            <h2 style={{ borderBottom: 'none' }}>Runs over time</h2>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="runsFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#1f6feb" stopOpacity={0.5} />
                      <stop offset="100%" stopColor="#1f6feb" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="failFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#f85149" stopOpacity={0.5} />
                      <stop offset="100%" stopColor="#f85149" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                  <XAxis dataKey="date" tickFormatter={fmtDateTick} stroke="#8b949e" fontSize={11} />
                  <YAxis allowDecimals={false} stroke="#8b949e" fontSize={11} />
                  <Tooltip
                    labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
                    contentStyle={{ background: '#161b22', border: '1px solid #30363d', fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="runs" stroke="#58a6ff" fill="url(#runsFill)" name="Runs" />
                  <Area type="monotone" dataKey="failures" stroke="#f85149" fill="url(#failFill)" name="Failures" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <div className="grid-2">
            <section className="section">
              <h2 style={{ borderBottom: 'none' }}>By action</h2>
              <table>
                <thead>
                  <tr>
                    <th>Action</th>
                    <th style={{ textAlign: 'right' }}>Runs</th>
                    <th style={{ textAlign: 'right' }}>Fail</th>
                    <th style={{ textAlign: 'right' }}>Avg dur</th>
                    <th style={{ textAlign: 'right' }}>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {byAction.length === 0 ? (
                    <tr><td colSpan={5} className="dim">no runs in range</td></tr>
                  ) : byAction.map((row) => (
                    <tr
                      key={row.action_name}
                      onClick={() => navigate(`/runs?agent=${encodeURIComponent(row.action_name)}`)}
                      style={{ cursor: 'pointer' }}
                      title={`Open runs for ${row.action_name}`}
                    >
                      <td><code>{row.action_name}</code></td>
                      <td style={{ textAlign: 'right' }}>{row.total}</td>
                      <td style={{ textAlign: 'right', color: row.failures ? 'var(--red)' : 'inherit' }}>
                        {row.failures}
                      </td>
                      <td style={{ textAlign: 'right' }}>{fmtMs(row.avg_duration_ms)}</td>
                      <td style={{ textAlign: 'right' }}>
                        {fmtNum(row.total_input_tokens + row.total_output_tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="section">
              <h2 style={{ borderBottom: 'none' }}>By executor</h2>
              <table>
                <thead>
                  <tr>
                    <th>Executor</th>
                    <th style={{ textAlign: 'right' }}>Runs</th>
                    <th style={{ textAlign: 'right' }}>Fail</th>
                    <th style={{ textAlign: 'right' }}>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {byExecutor.length === 0 ? (
                    <tr><td colSpan={4} className="dim">no runs in range</td></tr>
                  ) : byExecutor.map((row) => (
                    <tr
                      key={row.executor}
                      onClick={() => navigate(`/runs?executor=${encodeURIComponent(row.executor)}`)}
                      style={{ cursor: 'pointer' }}
                      title={`Open runs for executor ${row.executor}`}
                    >
                      <td><code>{row.executor}</code></td>
                      <td style={{ textAlign: 'right' }}>{row.total}</td>
                      <td style={{ textAlign: 'right', color: row.failures ? 'var(--red)' : 'inherit' }}>
                        {row.failures}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {fmtNum(row.total_input_tokens + row.total_output_tokens)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </div>

          <section className="section">
            <div className="row between" style={{ marginBottom: 8 }}>
              <h2 style={{ border: 'none', margin: 0 }}>Recent runs</h2>
              <span className="dim">{runs.length} shown</span>
            </div>
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Agent</th>
                  <th>Runner</th>
                  <th>Model</th>
                  <th>State</th>
                  <th style={{ textAlign: 'right' }}>Duration</th>
                  <th style={{ textAlign: 'right' }}>Tokens</th>
                  <th style={{ textAlign: 'right' }}>Cost</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.length === 0 ? (
                  <tr><td colSpan={9} className="dim">no runs</td></tr>
                ) : runs.map((r) => {
                  const tokens =
                    (r.input_tokens ?? 0) + (r.output_tokens ?? 0) +
                    (r.cache_read_tokens ?? 0) + (r.cache_creation_tokens ?? 0);
                  const stop = (e: React.MouseEvent) => e.stopPropagation();
                  return (
                    <tr
                      key={r.id}
                      onClick={() => navigate(`/runs/${r.id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="dim" title={r.started_at || ''}>{fmtRelative(r.started_at)}</td>
                      <td onClick={stop}>
                        <Link to={`/agents/${r.action_name}`}><code>{r.action_name}</code></Link>
                      </td>
                      <td className="dim"><code>{r.executor}</code></td>
                      <td className="dim">{r.model ? <code>{r.model}</code> : '—'}</td>
                      <td><StatePill state={r.state} /></td>
                      <td style={{ textAlign: 'right' }}>{fmtMs(r.duration_ms)}</td>
                      <td style={{ textAlign: 'right' }}>{tokens ? fmtNum(tokens) : '—'}</td>
                      <td style={{ textAlign: 'right' }}>{fmtCost(r.cost_usd)}</td>
                      <td onClick={stop} style={{ textAlign: 'right' }}>
                        <button
                          className="link-btn"
                          onClick={(e) => { stop(e); setSelected(r); }}
                          title="quick peek"
                        >
                          peek
                        </button>
                        <Link to={`/runs/${r.id}`} style={{ marginLeft: 8 }} title="open run">↗</Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        </>
      )}

      <RunDetailDrawer run={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
