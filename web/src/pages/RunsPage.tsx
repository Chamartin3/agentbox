import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  RunsFacets,
  RunsPage as RunsPageData,
  RunsStats,
  api,
} from '../api/client';
import { RunsFilterKey, RunStatus } from '../api/enums';
import RunsTable, { RunRow } from '../components/runs/RunsTable';
import RunsDashboard from '../components/runs/RunsDashboard';
import RunnerProfilesPage from './RunnerProfilesPage';
import { RuntimeDefaultsForm, type ToastState } from './SettingsBaseTab';
import Toast from '../components/common/Toast';

const PAGE_SIZE = 25;

type FilterKey = RunsFilterKey;

function readParam(p: URLSearchParams, k: FilterKey): string {
  return p.get(k) ?? '';
}

function setParam(
  p: URLSearchParams,
  k: FilterKey,
  v: string,
): URLSearchParams {
  const next = new URLSearchParams(p);
  if (v) next.set(k, v);
  else next.delete(k);
  if (k !== RunsFilterKey.Page) next.delete(RunsFilterKey.Page);
  return next;
}

const STATUSES = [
  { value: '', label: 'All' },
  { value: RunStatus.OK, label: 'OK' },
  { value: RunStatus.FAILED, label: 'Failed' },
  { value: RunStatus.ERROR, label: 'Error' },
  { value: RunStatus.INCOMPLETE, label: 'Incomplete' },
  { value: RunStatus.TIMEOUT, label: 'Timeout' },
  { value: RunStatus.RUNNING, label: 'Running' },
];


function filtersToQuery(f: { agent: string; status: string; executor: string; q: string }) {
  return {
    agent: f.agent || undefined,
    status: f.status || undefined,
    executor: f.executor || undefined,
    q: f.q || undefined,
  };
}

export default function RunsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab: 'runs' | 'profiles' = location.pathname.startsWith('/runs/profiles')
    ? 'profiles'
    : 'runs';
  const [toast, setToast] = useState<ToastState>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack">
      <h1>Runs</h1>
      <div className="tabs">
        <button
          className={`tab-button ${activeTab === 'runs' ? 'active' : ''}`}
          onClick={() => navigate('/runs')}
        >
          Runs
        </button>
        <button
          className={`tab-button ${activeTab === 'profiles' ? 'active' : ''}`}
          onClick={() => navigate('/runs/profiles')}
        >
          Runner profiles
        </button>
      </div>
      <div className="tab-content">
        {activeTab === 'runs' ? (
          <div className="tab-pane stack">
            <RunsTab />
          </div>
        ) : (
          <div className="tab-pane stack">
            <section className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
              <h3 style={{ margin: 0 }}>Runtime defaults</h3>
              <p className="dim" style={{ fontSize: 12, margin: 0 }}>
                Default model per backend + runner timeout. Backends consult these on every run.
              </p>
              <RuntimeDefaultsForm onToast={setToast} />
            </section>
            <section className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
              <h3 style={{ margin: 0 }}>Profiles</h3>
              <RunnerProfilesPage embedded />
            </section>
          </div>
        )}
      </div>
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}

function RunsTab() {
  const [params, setParams] = useSearchParams();
  const agent = readParam(params, RunsFilterKey.Agent);
  const status = readParam(params, RunsFilterKey.Status);
  const executor = readParam(params, RunsFilterKey.Executor);
  const qParam = readParam(params, RunsFilterKey.Q);
  const page = Math.max(1, Number(readParam(params, RunsFilterKey.Page) || '1'));

  const [qInput, setQInput] = useState(qParam);
  useEffect(() => setQInput(qParam), [qParam]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (qInput !== qParam) {
        setParams(setParam(params, RunsFilterKey.Q, qInput), { replace: true });
      }
    }, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const [data, setData] = useState<RunsPageData | null>(null);
  const [stats, setStats] = useState<RunsStats | null>(null);
  const [facets, setFacets] = useState<RunsFacets | null>(null);
  const [loading, setLoading] = useState(false);

  const isLiveView = page === 1 && !agent && !status && !executor && !qParam;
  const lastQuery = useRef<string>('');

  const filterQuery = filtersToQuery({ agent, status, executor, q: qParam });

  useEffect(() => {
    api.runFacets().then(setFacets).catch(console.error);
  }, []);

  useEffect(() => {
    const queryKey = JSON.stringify({ agent, status, executor, q: qParam, page });
    lastQuery.current = queryKey;
    const tick = async () => {
      if (lastQuery.current !== queryKey) return;
      setLoading(true);
      try {
        const [d, s] = await Promise.all([
          api.listRunsPaged({
            ...filterQuery,
            limit: PAGE_SIZE,
            offset: (page - 1) * PAGE_SIZE,
          }),
          api.runStats(filterQuery),
        ]);
        if (lastQuery.current === queryKey) {
          setData(d);
          setStats(s);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    tick();
    if (!isLiveView) return;
    const h = window.setInterval(tick, 4000);
    return () => window.clearInterval(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, status, executor, qParam, page, isLiveView]);

  const totalPages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total / Math.max(1, data.limit)));
  }, [data]);

  const setFilter = (k: FilterKey, v: string) =>
    setParams(setParam(params, k, v), { replace: false });

  const goToPage = (n: number) =>
    setParams(setParam(params, RunsFilterKey.Page, String(Math.max(1, n))), { replace: false });

  const clearAll = () => {
    const next = new URLSearchParams();
    setParams(next, { replace: false });
    setQInput('');
  };

  const anyFilter = !!(agent || status || executor || qParam);
  const items = data?.items ?? [];

  const runRows: RunRow[] = useMemo(
    () =>
      items.map((r) => ({
        id: r.id,
        agent_id: r.agent_id,
        status: r.status,
        started_at: r.created_at,
        finished_at: r.finished_at,
        backend: r.backend ?? null,
        configured_model: r.configured_model ?? null,
        reported_model: r.model ?? null,
        agent_version: r.agent_version ?? null,
        agent_version_id: r.agent_version_id ?? null,
        input_tokens: r.input_tokens ?? null,
        output_tokens: r.output_tokens ?? null,
        cache_read_tokens: r.cache_read_tokens ?? null,
        cache_creation_tokens: r.cache_write_tokens ?? null,
        cost_usd: r.cost_usd ?? null,
        duration_ms: r.duration_ms ?? null,
        rating: r.rating ?? null,
      })),
    [items],
  );

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="Search input/output/error/id…"
          style={{ minWidth: 260 }}
        />
        <select value={agent} onChange={(e) => setFilter(RunsFilterKey.Agent, e.target.value)}>
          <option value="">All agents</option>
          {facets?.agents.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={executor} onChange={(e) => setFilter(RunsFilterKey.Executor, e.target.value)}>
          <option value="">All executors</option>
          {facets?.executors.map((e) => (
            <option key={e} value={e}>{e}</option>
          ))}
        </select>
        <div className="range-toggle" role="tablist" aria-label="Status">
          {STATUSES.map((s) => (
            <button
              key={s.value || 'all'}
              className={status === s.value ? 'active' : ''}
              onClick={() => setFilter(RunsFilterKey.Status, s.value)}
            >
              {s.label}
            </button>
          ))}
        </div>
        {anyFilter && (
          <button className="link-btn" onClick={clearAll}>
            clear all
          </button>
        )}
        <span className="dim" style={{ marginLeft: 'auto' }}>
          {data ? `${data.total.toLocaleString()} match${data.total === 1 ? '' : 'es'}` : ''}
          {loading ? ' · loading…' : ''}
        </span>
      </div>

      <RunsDashboard stats={stats} scope="global" />

      <RunsTable
        items={runRows}
        columns={['run', 'status', 'started', 'duration', 'agent_version', 'runner_model', 'tokens', 'rating']}
        emptyMessage={anyFilter ? 'no runs match these filters' : 'no runs yet'}
        loading={loading}
      />

      {data && data.total > 0 && (
        <div className="row between" style={{ marginTop: 4 }}>
          <span className="dim">
            page {page} of {totalPages} · showing {items.length} of {data.total}
          </span>
          <div className="row">
            <button
              onClick={() => goToPage(page - 1)}
              disabled={page <= 1 || loading}
            >
              ← prev
            </button>
            <button
              onClick={() => goToPage(page + 1)}
              disabled={!data.has_more || loading}
            >
              next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
