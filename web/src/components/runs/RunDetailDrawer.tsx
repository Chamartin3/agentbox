import { Link } from 'react-router-dom';
import { AgentRun } from '../../api/activity';
import { fmtCost, fmtDt, fmtMs, fmtNum } from '../../util/format';

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
