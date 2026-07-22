import type { RunnerProfile } from '../../api/client';
import { harnessLabel, providerLabel } from './runnerLabels';
import './runner.css';

interface Props {
  profile?: RunnerProfile | null;
  /** Runner kind to show as harness when there's no bound profile. */
  fallbackKind?: string | null;
  /** Compact = just the profile name (used in dense lists like the agents table). */
  compact?: boolean;
}

/** Reusable profile summary. Full = name on one line + harness/provider/model
 *  badges beneath. Compact = just the name. */
export function ProfileDisplay({ profile, fallbackKind, compact }: Props) {
  const name = profile
    ? (profile.name || profile.id)
    : 'System default';

  if (compact) {
    return (
      <span className={`profile-display-name${profile ? '' : ' dim'}`}>{name}</span>
    );
  }

  if (!profile) {
    return (
      <div className="profile-display">
        <span className="profile-display-name dim">System default</span>
        <div className="profile-display-badges">
          <span className="runner-badge runner-badge--harness" data-harness={fallbackKind ?? undefined}>{harnessLabel(fallbackKind)}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="profile-display">
      <span className="profile-display-name">
        {name}
        {profile.is_system_default && <span className="dim" style={{ marginLeft: 6, fontWeight: 400 }}>[default]</span>}
      </span>
      <div className="profile-display-badges">
        <span className="runner-badge runner-badge--harness" data-harness={profile.backend ?? undefined}>{harnessLabel(profile.backend)}</span>
        <span className="runner-badge runner-badge--provider" data-provider={providerLabel(profile).toLowerCase()}>{providerLabel(profile)}</span>
        <span className="runner-badge runner-badge--model">{profile.model || 'default'}</span>
      </div>
    </div>
  );
}
