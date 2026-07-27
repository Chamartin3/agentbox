import type { RunnerProfile } from '../../api/client';
import { HarnessBadge, ProviderBadge, ModelBadge } from './RunnerBadges';
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
          <HarnessBadge backend={fallbackKind} />
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
        <HarnessBadge backend={profile.backend} />
        <ProviderBadge backend={profile.backend} provider={profile.provider} />
        <ModelBadge model={profile.model} />
      </div>
    </div>
  );
}
