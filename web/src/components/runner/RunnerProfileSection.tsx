import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError, type RunnerBackend, type RunnerProfile, type RunnerProvider } from '../../api/client';
import { apiTokens as apiTokensClient } from '../../api/api_tokens';
import RunnerProfileModal from './RunnerProfileModal';

export function RunnerProfileSection({ agentId }: { agentId: string }) {
  const [bound, setBound] = useState<RunnerProfile | null>(null);
  const [profiles, setProfiles] = useState<RunnerProfile[]>([]);
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [backends, setBackends] = useState<RunnerBackend[]>([]);
  const [apiTokens, setApiTokens] = useState<Array<{ id: string; name: string; environment: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const [b, list, provs, bes, tokensResp] = await Promise.all([
        api.getAgentRunnerProfile(agentId).catch(() => null),
        api.listRunnerProfiles(),
        api.listRunnerProviders().catch(() => []),
        api.listRunnerBackends().catch(() => []),
        apiTokensClient.listSafe(),
      ]);
      setBound(b);
      setProfiles(list);
      setProviders(provs);
      setBackends(bes);
      setApiTokens(tokensResp);
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [agentId]);

  const onChange = async (profileId: string) => {
    setSaving(true);
    setErr(null);
    try {
      if (profileId) {
        await api.setAgentRunnerProfile(agentId, profileId);
      } else {
        await api.clearAgentRunnerProfile(agentId);
      }
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleSaved = async (profile: RunnerProfile) => {
    setShowModal(false);
    setErr(null);
    // Refresh profile list and auto-select the new profile
    await load();
    try {
      await api.setAgentRunnerProfile(agentId, profile.id);
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    }
  };

  return (
    <fieldset className="config-fieldset">
      <legend>runner profile</legend>
      <p className="dim" style={{ fontSize: 11, marginTop: 0 }}>
        Provider + model + credentials used to execute this agent.
      </p>
      {loading ? (
        <p className="dim">loading…</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={bound?.id || ''}
              disabled={saving}
              onChange={(e) => void onChange(e.target.value)}
              style={{ minWidth: 280 }}
            >
              <option value="">— use system default —</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.backend}{p.provider ? `/${p.provider}` : ''}{p.model ? ` · ${p.model}` : ''})
                  {p.is_system_default ? ' [default]' : ''}
                </option>
              ))}
            </select>
            <button onClick={() => setShowModal(true)} disabled={saving}>
              + new profile
            </button>
            <Link to="/runners" className="dim" style={{ fontSize: 12 }}>manage profiles →</Link>
            {bound && (
              <span className="dim" style={{ fontSize: 12 }}>
                bound to <strong>{bound.id}</strong>
              </span>
            )}
          </div>
        </>
      )}
      {err && <p style={{ color: 'var(--error)', fontSize: 12 }}>{err}</p>}

      {showModal && (
        <RunnerProfileModal
          mode="create"
          backends={backends}
          providers={providers}
          apiTokens={apiTokens}
          onClose={() => setShowModal(false)}
          onSaved={handleSaved}
          onError={(msg) => setErr(msg)}
        />
      )}
    </fieldset>
  );
}
