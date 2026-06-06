import { RunStatus, canonicalStatus } from '../../theme/statusColors';

// Single source of truth for run-status pills.
// CSS classes live in styles.css (.pill.ok | .pill.running | .pill.error |
// .pill.failed | .pill.timeout | .pill.incomplete).
export function StatusPill({ status }: { status: string }) {
  const cls = canonicalStatus(status);
  // Surface alias inputs (e.g. 'succeeded') with their canonical label.
  const label = cls === RunStatus.OK && status !== RunStatus.OK ? RunStatus.OK : status;
  return <span className={`pill ${cls}`}>{label}</span>;
}
