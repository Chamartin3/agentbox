import { Link, useNavigate } from 'react-router-dom';
import { RunStatus, canonicalStatus } from '../theme/statusColors';

// Normalized row shape used by the shared runs table. Both the runs API
// (RunRecord) and the activity API (AgentRun) map onto this — fields not
// available on a given source stay null and the corresponding column is
// hidden via the `columns` prop.
export interface RunRow {
  id: string;
  agent_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms?: number | null;
  backend?: string | null;
  configured_model?: string | null;
  reported_model?: string | null;
  agent_version?: number | null;
  agent_version_id?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_creation_tokens?: number | null;
  cost_usd?: number | null;
}

export type RunsColumn =
  | 'run'
  | 'agent'
  | 'version'
  | 'runner'
  | 'model'
  | 'status'
  | 'started'
  | 'finished'
  | 'duration'
  | 'tokens'
  | 'cost'
  | 'open';

const DEFAULT_COLUMNS: RunsColumn[] = [
  'run',
  'agent',
  'version',
  'status',
  'started',
  'finished',
];

function statusClass(s: string): string {
  return canonicalStatus(s);
}

function statusLabel(s: string): string {
  return canonicalStatus(s) === RunStatus.OK && s !== RunStatus.OK ? RunStatus.OK : s;
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${statusClass(status)}`}>{statusLabel(status)}</span>;
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

function fmtRelative(iso: string | null | undefined): string {
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

const COLUMN_HEADER: Record<RunsColumn, string> = {
  run: 'Run',
  agent: 'Agent',
  version: 'Version',
  runner: 'Runner',
  model: 'Model',
  status: 'Status',
  started: 'Started',
  finished: 'Finished',
  duration: 'Duration',
  tokens: 'Tokens',
  cost: 'Cost',
  open: '',
};

const RIGHT_ALIGNED: ReadonlySet<RunsColumn> = new Set([
  'duration',
  'tokens',
  'cost',
  'open',
]);

interface Props {
  items: RunRow[];
  columns?: RunsColumn[];
  emptyMessage?: string;
  loading?: boolean;
  onRowClick?: (row: RunRow) => 'navigate' | 'custom';
  onPeek?: (row: RunRow) => void;
}

export default function RunsTable({
  items,
  columns = DEFAULT_COLUMNS,
  emptyMessage = 'no runs',
  loading = false,
  onRowClick,
  onPeek,
}: Props) {
  const navigate = useNavigate();
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  const renderCell = (col: RunsColumn, r: RunRow): React.ReactNode => {
    switch (col) {
      case 'run':
        return (
          <Link to={`/runs/${r.id}`} onClick={stop}>
            <code>{r.id.slice(0, 12)}</code>
          </Link>
        );
      case 'agent':
        return (
          <Link to={`/agents/${encodeURIComponent(r.agent_id)}`} onClick={stop}>
            <code>{r.agent_id}</code>
          </Link>
        );
      case 'version':
        return r.agent_version != null && r.agent_version_id ? (
          <Link
            to={`/agents/${encodeURIComponent(r.agent_id)}/versions?highlight=${r.agent_version_id}`}
            className="version-chip"
            onClick={stop}
          >
            v{r.agent_version}
          </Link>
        ) : (
          <span className="dim">—</span>
        );
      case 'runner':
        return r.backend ? <code className="dim">{r.backend}</code> : <span className="dim">—</span>;
      case 'model': {
        const primary = r.configured_model;
        const reported = r.reported_model;
        if (!primary) return <span className="dim">—</span>;
        if (reported && reported !== primary) {
          return (
            <code className="dim" title={`Reported as: ${reported}`}>
              {primary}
              <span style={{ fontSize: 10, opacity: 0.6, marginLeft: 4 }}>
                as: {reported}
              </span>
            </code>
          );
        }
        return <code className="dim">{primary}</code>;
      }
      case 'status':
        return <StatusPill status={r.status} />;
      case 'started':
        return <span className="dim" title={r.started_at || ''}>{fmtRelative(r.started_at)}</span>;
      case 'finished':
        return <span className="dim">{r.finished_at || ''}</span>;
      case 'duration':
        return fmtMs(r.duration_ms);
      case 'tokens': {
        const t =
          (r.input_tokens ?? 0) +
          (r.output_tokens ?? 0) +
          (r.cache_read_tokens ?? 0) +
          (r.cache_creation_tokens ?? 0);
        return t ? fmtNum(t) : '—';
      }
      case 'cost':
        return fmtCost(r.cost_usd);
      case 'open':
        return (
          <span onClick={stop}>
            {onPeek && (
              <button className="link-btn" onClick={() => onPeek(r)} title="quick peek">
                peek
              </button>
            )}
            <Link to={`/runs/${r.id}`} style={{ marginLeft: 8 }} title="open run">
              ↗
            </Link>
          </span>
        );
    }
  };

  const handleRowClick = (r: RunRow) => {
    if (!onRowClick) return navigate(`/runs/${r.id}`);
    const action = onRowClick(r);
    if (action === 'navigate') navigate(`/runs/${r.id}`);
  };

  return (
    <table>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c} style={RIGHT_ALIGNED.has(c) ? { textAlign: 'right' } : undefined}>
              {COLUMN_HEADER[c]}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {items.length === 0 && !loading && (
          <tr>
            <td colSpan={columns.length} className="dim">{emptyMessage}</td>
          </tr>
        )}
        {items.map((r) => (
          <tr
            key={r.id}
            onClick={() => handleRowClick(r)}
            style={{ cursor: 'pointer' }}
          >
            {columns.map((c) => (
              <td
                key={c}
                style={RIGHT_ALIGNED.has(c) ? { textAlign: 'right' } : undefined}
              >
                {renderCell(c, r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
