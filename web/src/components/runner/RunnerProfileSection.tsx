import { useEffect, useState } from 'react';
import { api, ApiError, type RunnerProfile } from '../../api/client';
import RunnerProfilePickerModal from './RunnerProfilePickerModal';
import { ProfileDisplay } from './ProfileDisplay';

export function RunnerProfileSection({ agentId }: { agentId: string }) {
  const [bound, setBound] = useState<RunnerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      setBound(await api.getAgentRunnerProfile(agentId).catch(() => null));
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [agentId]);

  const bind = async (profileId: string) => {
    setSaving(true);
    setErr(null);
    try {
      if (profileId) await api.setAgentRunnerProfile(agentId, profileId);
      else await api.clearAgentRunnerProfile(agentId);
      setShowPicker(false);
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <fieldset className="config-fieldset">
      <legend>runner profile</legend>
      {loading ? (
        <p className="dim">loading…</p>
      ) : (
        <div className="runner-card">
          <ProfileDisplay profile={bound} />
          <div className="runner-card-actions">
            <button
              className="icon-btn"
              aria-label="Change runner profile"
              title="Change runner profile"
              onClick={() => setShowPicker(true)}
              disabled={saving}
            >
              ✎
            </button>
          </div>
        </div>
      )}
      {err && <p style={{ color: 'var(--error)', fontSize: 12 }}>{err}</p>}

      {showPicker && (
        <RunnerProfilePickerModal
          boundId={bound?.id ?? null}
          busy={saving}
          onPick={(id) => void bind(id)}
          onCreated={(p) => void bind(p.id)}
          onClose={() => setShowPicker(false)}
        />
      )}
    </fieldset>
  );
}
