import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  RunsFacets,
  RunsPage as RunsPageData,
  api,
} from '../api/client';

const PAGE_SIZE = 25;

// Filter state is URL-synced so shares/reloads keep the same view. The
// query params we own:
//   ?agent=<id>&status=ok|error|running&executor=<model>&q=<text>&page=<1-based>
// Empty values are dropped from the URL.
type FilterKey = 'agent' | 'status' | 'executor' | 'q' | 'page';

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
  // Changing a filter resets pagination, except when the filter *is*
  // the page itself.
  if (k !== 'page') next.delete('page');
  return next;
}

const STATUSES = [
  { value: '', label: 'All' },
  { value: 'ok', label: 'OK' },
  { value: 'failed', label: 'Failed' },
  { value: 'error', label: 'Error' },
  { value: 'incomplete', label: 'Incomplete' },
  { value: 'timeout', label: 'Timeout' },
  { value: 'running', label: 'Running' },
];

export default function RunsPage() {
  const [params, setParams] = useSearchParams();
  const agent = readParam(params, 'agent');
  const status = readParam(params, 'status');
  const executor = readParam(params, 'executor');
  const qParam = readParam(params, 'q');
  const page = Math.max(1, Number(readParam(params, 'page') || '1'));

  // Local search input — debounced into the URL so we don't refetch on
  // every keystroke. Initialised from the URL on mount and whenever the
  // user navigates back into the page.
  const [qInput, setQInput] = useState(qParam);
  useEffect(() => setQInput(qParam), [qParam]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      if (qInput !== qParam) {
        setParams(setParam(params, 'q', qInput), { replace: true });
      }
    }, 250);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  const [data, setData] = useState<RunsPageData | null>(null);
  const [facets, setFacets] = useState<RunsFacets | null>(null);
  const [loading, setLoading] = useState(false);
  const [agg, setAgg] = useState<{ runs: number; input_tokens: number; output_tokens: number; cost_usd: number } | null>(null);

  // Poll only when we're on page 1 with no filters — that's the
  // "live activity" view. Filtered/paginated views are stable.
  const isLiveView = page === 1 && !agent && !status && !executor && !qParam;
  const lastQuery = useRef<string>('');

  useEffect(() => {
    api.runFacets().then(setFacets).catch(console.error);
  }, []);

  useEffect(() => {
    const queryKey = JSON.stringify({ agent, status, executor, q: qParam, page });
    lastQuery.current = queryKey;
    const tick = async () => {
      // Avoid clobbering newer state if the user filtered while a
      // previous tick was in flight.
      if (lastQuery.current !== queryKey) return;
      setLoading(true);
      try {
        const [d, a] = await Promise.all([
          api.listRunsPaged({
            agent: agent || undefined,
            status: status || undefined,
            executor: executor || undefined,
            q: qParam || undefined,
            limit: PAGE_SIZE,
            offset: (page - 1) * PAGE_SIZE,
          }),
          api.aggregateUsage(),
        ]);
        if (lastQuery.current === queryKey) {
          setData(d);
          setAgg(a);
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
  }, [agent, status, executor, qParam, page, isLiveView]);

  const totalPages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total / Math.max(1, data.limit)));
  }, [data]);

  const setFilter = (k: FilterKey, v: string) =>
    setParams(setParam(params, k, v), { replace: false });

  const goToPage = (n: number) =>
    setParams(setParam(params, 'page', String(Math.max(1, n))), { replace: false });

  const clearAll = () => {
    const next = new URLSearchParams();
    setParams(next, { replace: false });
    setQInput('');
  };

  const anyFilter = !!(agent || status || executor || qParam);
  const items = data?.items ?? [];

  return (
    <div className="stack">
      <div className="row between">
        <h1>Runs</h1>
        {agg && (
          <span className="dim">
            {agg.runs} runs · {agg.input_tokens.toLocaleString()} in ·{' '}
            {agg.output_tokens.toLocaleString()} out · ${(agg.cost_usd || 0).toFixed(4)}
          </span>
        )}
      </div>

      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          placeholder="Search input/output/error/id…"
          style={{ minWidth: 260 }}
        />
        <select value={agent} onChange={(e) => setFilter('agent', e.target.value)}>
          <option value="">All agents</option>
          {facets?.agents.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={executor} onChange={(e) => setFilter('executor', e.target.value)}>
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
              onClick={() => setFilter('status', s.value)}
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

      <table>
        <thead>
          <tr>
            <th>Run</th>
            <th>Agent</th>
            <th>Version</th>
            <th>Status</th>
            <th>Started</th>
            <th>Finished</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              <td><Link to={`/runs/${r.id}`}>{r.id.slice(0, 12)}</Link></td>
              <td>
                <Link to={`/runs?agent=${encodeURIComponent(r.agent_id)}`} title="filter by this agent">
                  {r.agent_id}
                </Link>
              </td>
              <td>
                {r.agent_version_id ? (
                  <Link
                    to={`/agents/${encodeURIComponent(r.agent_id)}/versions?highlight=${r.agent_version_id}`}
                    className="version-chip"
                  >
                    v{r.agent_version_id}
                  </Link>
                ) : (
                  <span className="dim">—</span>
                )}
              </td>
              <td><span className={`pill ${r.status}`}>{r.status}</span></td>
              <td className="dim">{r.created_at}</td>
              <td className="dim">{r.finished_at || ''}</td>
            </tr>
          ))}
          {!items.length && !loading && (
            <tr>
              <td colSpan={6} className="dim">
                {anyFilter ? 'no runs match these filters' : 'no runs yet'}
              </td>
            </tr>
          )}
        </tbody>
      </table>

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
