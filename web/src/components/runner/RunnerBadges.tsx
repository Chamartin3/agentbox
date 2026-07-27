// Global, reusable runner badges — one per category, visually distinct via the
// runner-badge--{harness,provider,model} classes (per-vendor colors in runner.css).
// Used on the agent detail card, the runner-profiles table, and the providers list.
import { harnessLabel, providerLabel } from './runnerLabels';
import './runner.css';

export function HarnessBadge({ backend }: { backend?: string | null }) {
  return (
    <span className="runner-badge runner-badge--harness" data-harness={backend ?? undefined}>
      {harnessLabel(backend)}
    </span>
  );
}

export function ProviderBadge({
  backend,
  provider,
}: {
  backend?: string | null;
  provider?: string | null;
}) {
  const label = providerLabel({ backend, provider });
  return (
    <span className="runner-badge runner-badge--provider" data-provider={label.toLowerCase()}>
      {label}
    </span>
  );
}

export function ModelBadge({ model }: { model?: string | null }) {
  return <span className="runner-badge runner-badge--model">{model || 'default'}</span>;
}
