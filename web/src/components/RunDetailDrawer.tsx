import { Link } from 'react-router-dom';
import { AgentRun } from '../api/activity';

function fmtDt(iso: string | null | undefined) {
  return iso ? new Date(iso).toLocaleString() : '—';
}
function fmtMs(ms: number | null | undefined) {
  if (!ms && ms !== 0) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}
function fmtNum(n: number | null | undefined) {
  return n === null || n === undefined ? '—' : n.toLocaleString();
}
function fmtCost(n: number | null | undefined) {
  if (n === null || n === undefined) return '—';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

interface Props {
  run: AgentRun | null;
  onClose: () => void;
}

export default function RunDetailDrawer({ run, onClose }: Props) {
  if (!run) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3>
            <code>{run.id.slice(0, 12)}</code>
          </h3>
          <button onClick={onClose}>close</button>
        </div>

        <dl className="dl">
          <dt>Action</dt><dd><code>{run.action_name}</code></dd>
          <dt>Backend</dt><dd><code>{run.backend}</code></dd>
          <dt>Model</dt><dd><code>{run.configured_model ?? '—'}</code></dd>
          <dt>Reported</dt><dd><code>{run.reported_model ?? '—'}</code></dd>
          <dt>State</dt><dd>{run.state}</dd>
          <dt>Started</dt><dd>{fmtDt(run.started_at)}</dd>
          <dt>Completed</dt><dd>{fmtDt(run.completed_at)}</dd>
          <dt>Duration</dt><dd>{fmtMs(run.duration_ms)}</dd>
          <dt>Input</dt><dd>{fmtNum(run.input_tokens)}</dd>
          <dt>Output</dt><dd>{fmtNum(run.output_tokens)}</dd>
          <dt>Cache read</dt><dd>{fmtNum(run.cache_read_tokens)}</dd>
          <dt>Cache write</dt><dd>{fmtNum(run.cache_creation_tokens)}</dd>
          <dt>Cost</dt><dd>{fmtCost(run.cost_usd)}</dd>
        </dl>

        {run.error && (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ color: 'var(--red)' }}>Error</h3>
            <pre>{run.error}</pre>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <Link to={`/runs/${run.id}`} onClick={onClose}>open full run →</Link>
        </div>
      </div>
    </div>
  );
}
