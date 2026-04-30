import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, RunsPage as RunsPageData } from '../api/client';

interface Props {
  agentId: string;
  pageSize?: number;
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

export default function AgentRunsList({ agentId, pageSize = 25 }: Props) {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [data, setData] = useState<RunsPageData | null>(null);
  const [loading, setLoading] = useState(false);
  const lastQuery = useRef('');

  const isLiveView = page === 1 && !status;

  useEffect(() => {
    const queryKey = JSON.stringify({ agentId, status, page });
    lastQuery.current = queryKey;
    const tick = async () => {
      if (lastQuery.current !== queryKey) return;
      setLoading(true);
      try {
        const d = await api.listRunsPaged({
          agent: agentId,
          status: status || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        });
        if (lastQuery.current === queryKey) setData(d);
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
  }, [agentId, status, page, pageSize, isLiveView]);

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / Math.max(1, data.limit))) : 1;

  return (
    <div className="stack">
      <div className="row between" style={{ alignItems: 'center' }}>
        <div className="range-toggle" role="tablist" aria-label="Status">
          {STATUSES.map((s) => (
            <button
              key={s.value || 'all'}
              className={status === s.value ? 'active' : ''}
              onClick={() => {
                setStatus(s.value);
                setPage(1);
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
        <span className="dim">
          {data ? `${data.total.toLocaleString()} match${data.total === 1 ? '' : 'es'}` : ''}
          {loading ? ' · loading…' : ''}
        </span>
      </div>

      <table>
        <thead>
          <tr>
            <th>Run</th>
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
                {r.agent_version != null && r.agent_version_id ? (
                  <Link
                    to={`/agents/${encodeURIComponent(r.agent_id)}/versions?highlight=${r.agent_version_id}`}
                    className="version-chip"
                  >
                    v{r.agent_version}
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
              <td colSpan={5} className="dim">no runs for this agent</td>
            </tr>
          )}
        </tbody>
      </table>

      {data && data.total > pageSize && (
        <div className="row between">
          <span className="dim">
            page {page} of {totalPages} · showing {items.length} of {data.total}
          </span>
          <div className="row">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading}>
              ← prev
            </button>
            <button onClick={() => setPage((p) => p + 1)} disabled={!data.has_more || loading}>
              next →
            </button>
          </div>
        </div>
      )}

      <div className="dim" style={{ fontSize: 12 }}>
        <Link to={`/runs?agent=${encodeURIComponent(agentId)}`}>
          Open full runs view →
        </Link>
      </div>
    </div>
  );
}
