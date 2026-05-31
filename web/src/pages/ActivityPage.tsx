import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { CHART_STATUSES, STATUS_COLORS } from '../theme/statusColors';
import {
  ActivityRange,
  ActivitySummary,
  AgentRun,
  AgentRunState,
  activityApi,
} from '../api/activity';
import RunsTable, { RunRow } from '../components/runs/RunsTable';
import RunDetailDrawer from '../components/runs/RunDetailDrawer';
import { fmtCost, fmtMs, fmtNum } from '../util/format';

const RANGES: ActivityRange[] = ['7d', '30d', '90d'];

function fmtDateTick(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
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
  const byReportedModel = summary?.by_reported_model ?? [];

  const series = useMemo(() => {
    const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
    const byDate = new Map(rawSeries.map((p) => [p.date, p]));
    const empty = {
      runs: 0,
      failures: 0,
      running: 0,
      ok: 0,
      error: 0,
      failed: 0,
      timeout: 0,
      incomplete: 0,
    };
    const out: Array<typeof empty & { date: string }> = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = days - 1; i >= 0; i -= 1) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const hit = byDate.get(key);
      out.push(hit ?? { date: key, ...empty });
    }
    return out;
  }, [rawSeries, range]);

  const actionOptions = useMemo(
    () => Array.from(new Set(byAction.map((b) => b.action_name))).sort(),
    [byAction],
  );
  const reportedModelOptions = useMemo(
    () => Array.from(new Set(byReportedModel.map((b) => b.reported_model))).sort(),
    [byReportedModel],
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
          <option value="">All models</option>
          {reportedModelOptions.map((x) => <option key={x} value={x}>{x}</option>)}
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
                    {CHART_STATUSES.map((k) => (
                      <linearGradient key={k} id={`fill-${k}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={STATUS_COLORS[k]} stopOpacity={0.7} />
                        <stop offset="100%" stopColor={STATUS_COLORS[k]} stopOpacity={0.15} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
                  <XAxis dataKey="date" tickFormatter={fmtDateTick} stroke="#8b949e" fontSize={11} />
                  <YAxis allowDecimals={false} stroke="#8b949e" fontSize={11} />
                  <Tooltip
                    labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
                    contentStyle={{ background: '#161b22', border: '1px solid #30363d', fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
                  {CHART_STATUSES.map((k) => (
                    <Area
                      key={k}
                      type="monotone"
                      stackId="status"
                      dataKey={k}
                      stroke={STATUS_COLORS[k]}
                      fill={`url(#fill-${k})`}
                      name={k}
                    />
                  ))}
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
              <h2 style={{ borderBottom: 'none' }}>By reported model</h2>
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th style={{ textAlign: 'right' }}>Runs</th>
                    <th style={{ textAlign: 'right' }}>Fail</th>
                    <th style={{ textAlign: 'right' }}>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {byReportedModel.length === 0 ? (
                    <tr><td colSpan={4} className="dim">no runs in range</td></tr>
                  ) : byReportedModel.map((row) => (
                    <tr
                      key={row.reported_model}
                      onClick={() => navigate(`/runs?executor=${encodeURIComponent(row.reported_model)}`)}
                      style={{ cursor: 'pointer' }}
                      title={`Open runs for model ${row.reported_model}`}
                    >
                      <td><code>{row.reported_model}</code></td>
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
            <h2 style={{ border: 'none' }}>Recent runs</h2>
            <RunsTable
              items={runs.map((r): RunRow => ({
                id: r.id,
                agent_id: r.action_name,
                status: r.state,
                started_at: r.started_at,
                finished_at: r.completed_at,
                duration_ms: r.duration_ms,
                backend: r.backend,
                configured_model: r.configured_model,
                reported_model: r.reported_model,
                input_tokens: r.input_tokens,
                output_tokens: r.output_tokens,
                cache_read_tokens: r.cache_read_tokens,
                cache_creation_tokens: r.cache_creation_tokens,
                cost_usd: r.cost_usd,
              }))}
              columns={['run', 'agent', 'model', 'runner', 'status', 'duration', 'tokens', 'cost', 'open']}
              emptyMessage="no runs"
              loading={loading}
              onPeek={(row) => {
                const found = runs.find((r) => r.id === row.id);
                if (found) setSelected(found);
              }}
            />
          </section>
        </>
      )}

      <RunDetailDrawer run={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
