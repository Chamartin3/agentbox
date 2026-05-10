import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError, type RunnerProfile } from '../api/client';

export function RunnerProfileSection({ agentId }: { agentId: string }) {
  const [bound, setBound] = useState<RunnerProfile | null>(null);
  const [profiles, setProfiles] = useState<RunnerProfile[]>([]);
  const [providers, setProviders] = useState<
    Array<{ id: string; label: string; default_api_key_env: string | null; default_base_url: string | null; supports_model_listing: boolean }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Inline create form
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newProvider, setNewProvider] = useState('openai');
  const [newModel, setNewModel] = useState('');
  const [newApiKeyEnv, setNewApiKeyEnv] = useState('');
  const [newBaseUrl, setNewBaseUrl] = useState('');
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const [b, list, provs] = await Promise.all([
        api.getAgentRunnerProfile(agentId).catch(() => null),
        api.listRunnerProfiles(),
        api.listRunnerProviders().catch(() => []),
      ]);
      setBound(b);
      setProfiles(list);
      setProviders(provs as typeof providers);
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [agentId]);

  useEffect(() => {
    if (!showCreate) return;
    const prov = providers.find((p) => p.id === newProvider);
    if (!prov || !prov.supports_model_listing) {
      setProviderModels([]);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    api
      .listProviderModels(prov.id)
      .then((r) => {
        if (cancelled) return;
        setProviderModels((r || []).map((m) => m.id).sort());
      })
      .catch(() => {
        if (!cancelled) setProviderModels([]);
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [showCreate, newProvider, providers]);

  useEffect(() => {
    const prov = providers.find((p) => p.id === newProvider);
    if (!prov) return;
    setNewApiKeyEnv((prev) => prev || prov.default_api_key_env || '');
    setNewBaseUrl((prev) => prev || prov.default_base_url || '');
    setNewModel('');
  }, [newProvider, providers]);

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

  const resetCreate = () => {
    setShowCreate(false);
    setNewName('');
    setNewModel('');
    setNewApiKeyEnv('');
    setNewBaseUrl('');
    setProviderModels([]);
  };

  const onCreate = async () => {
    if (!newName.trim()) {
      setErr('name is required');
      return;
    }
    setCreating(true);
    setErr(null);
    try {
      const fullModel = newModel
        ? newModel.includes(':')
          ? newModel
          : `${newProvider}:${newModel}`
        : null;
      const created = await api.createRunnerProfile({
        name: newName.trim(),
        backend: 'token',
        provider: newProvider,
        model: fullModel,
        api_key_env: newApiKeyEnv.trim() || null,
        base_url: newBaseUrl.trim() || null,
        is_enabled: true,
        is_system_default: false,
      });
      await api.setAgentRunnerProfile(agentId, created.id);
      resetCreate();
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? `HTTP ${e.status}` : String(e));
    } finally {
      setCreating(false);
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
            <button onClick={() => setShowCreate((s) => !s)} disabled={creating}>
              {showCreate ? 'cancel' : '+ new profile'}
            </button>
            <Link to="/runners" className="dim" style={{ fontSize: 12 }}>manage profiles →</Link>
            {bound && (
              <span className="dim" style={{ fontSize: 12 }}>
                bound to <strong>{bound.id}</strong>
              </span>
            )}
          </div>

          {showCreate && (
            <div
              className="form-panel"
              style={{
                marginTop: 12,
                padding: 12,
                border: '1px solid var(--border)',
                borderRadius: 6,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 12,
              }}
            >
              <div style={{ gridColumn: '1 / -1' }}>
                <label>Name</label>
                <input
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="e.g. OpenAI gpt-4o for draft_fixer"
                />
              </div>
              <div>
                <label>Provider</label>
                <select value={newProvider} onChange={(e) => setNewProvider(e.target.value)}>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label>
                  Model
                  <span className="dim" style={{ fontSize: 11, marginLeft: 6 }}>
                    {modelsLoading
                      ? '(loading…)'
                      : providerModels.length > 0
                        ? `(${providerModels.length} available — type to search)`
                        : ''}
                  </span>
                </label>
                <input
                  list={`agent-profile-models-${agentId}`}
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  placeholder="gpt-4o"
                  autoComplete="off"
                />
                <datalist id={`agent-profile-models-${agentId}`}>
                  {providerModels.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
              </div>
              <div>
                <label>API Key Env Var</label>
                <input
                  value={newApiKeyEnv}
                  onChange={(e) => setNewApiKeyEnv(e.target.value)}
                  placeholder="OPENAI_API_KEY"
                />
              </div>
              <div>
                <label>Base URL (optional)</label>
                <input
                  value={newBaseUrl}
                  onChange={(e) => setNewBaseUrl(e.target.value)}
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div style={{ gridColumn: '1 / -1', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button onClick={resetCreate} disabled={creating} style={{ background: 'var(--bg-secondary)' }}>
                  Cancel
                </button>
                <button onClick={() => void onCreate()} disabled={creating || !newName.trim()}>
                  {creating ? 'creating…' : 'Create & bind'}
                </button>
              </div>
            </div>
          )}
        </>
      )}
      {err && <p style={{ color: 'var(--error)', fontSize: 12 }}>{err}</p>}
    </fieldset>
  );
}
