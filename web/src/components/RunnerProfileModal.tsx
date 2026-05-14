import { useEffect, useMemo, useState } from 'react';
import {
  api,
  ApiError,
  type RunnerBackend,
  type RunnerProfile,
  type RunnerProfileCreate,
  type RunnerProfilePatch,
  type RunnerProvider,
} from '../api/client';
import { BackendId } from '../api/enums';

function stripProviderPrefix(model: string | null | undefined, provider: string | null | undefined): string {
  if (!model) return '';
  if (provider && model.startsWith(`${provider}:`)) return model.slice(provider.length + 1);
  return model;
}

/** Token backend expects `provider:model`; CLI backends pass through verbatim. */
function encodeModel(
  model: string,
  provider: string | null | undefined,
  backend: string | null | undefined,
): string {
  if (!model) return '';
  if (backend !== BackendId.Token) return model;
  if (!provider) return model;
  if (model.startsWith(`${provider}:`)) return model;
  if (model.includes(':')) return model;
  return `${provider}:${model}`;
}

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: string } | string | undefined;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.detail === 'string') return d.detail;
    return `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}

type FormMode = 'create' | 'edit';

type FormState = Partial<RunnerProfile> & { id: string };

const blankForm: FormState = {
  id: '',
  name: '',
  backend: BackendId.Token,
  is_enabled: true,
  is_system_default: false,
};

export interface RunnerProfileModalProps {
  mode: FormMode;
  profile?: RunnerProfile;
  backends: RunnerBackend[];
  providers: RunnerProvider[];
  apiTokens: Array<{ id: string; name: string; environment: string }>;
  onClose: () => void;
  onSaved: (profile: RunnerProfile) => void;
  onDelete?: (id: string) => void;
  onError?: (msg: string) => void;
}

export default function RunnerProfileModal({
  mode,
  profile,
  backends,
  providers,
  apiTokens,
  onClose,
  onSaved,
  onDelete,
  onError,
}: RunnerProfileModalProps) {
  const [formData, setFormData] = useState<FormState>(blankForm);
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [credentialsUnlocked, setCredentialsUnlocked] = useState(false);

  // Initialize form data when opening
  useEffect(() => {
    if (mode === 'edit' && profile) {
      setFormData({ ...profile, model: stripProviderPrefix(profile.model, profile.provider) });
      setCredentialsUnlocked(false);
    } else {
      setFormData(blankForm);
      setCredentialsUnlocked(false);
    }
    setProviderModels([]);
    setModelsError(null);
  }, [mode, profile]);

  // ESC closes the modal
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const currentBackend = backends.find((b) => b.id === formData.backend) || null;
  const currentProvider = providers.find((p) => p.id === formData.provider) || null;

  const compatibleProviders = useMemo(() => {
    if (!currentBackend) return providers;
    const allow = new Set(currentBackend.compatible_providers);
    return providers.filter((p) => allow.has(p.id));
  }, [providers, currentBackend]);

  const providerIncompatible =
    formData.provider != null &&
    currentBackend != null &&
    !currentBackend.compatible_providers.includes(formData.provider);

  // Load provider models
  useEffect(() => {
    setProviderModels([]);
    setModelsError(null);
    if (!currentProvider || !currentProvider.supports_model_listing) return;
    let cancelled = false;
    setModelsLoading(true);
    const opts: { base_url?: string; api_key_env?: string; backend?: string } = {};
    if (formData.base_url) opts.base_url = formData.base_url;
    if (formData.api_key_env) opts.api_key_env = formData.api_key_env;
    if (formData.backend) opts.backend = formData.backend;
    api
      .listProviderModels(currentProvider.id, opts)
      .then((r) => {
        if (cancelled) return;
        const ids = (r || []).map((m) => m.id).sort();
        setProviderModels(ids);
      })
      .catch((e) => {
        if (cancelled) return;
        setProviderModels([]);
        setModelsError(errMsg(e, 'failed to load models'));
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentProvider?.id, formData.backend, formData.base_url, formData.api_key_env]);

  const handleFormChange = (key: string, value: unknown) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreate = async () => {
    if (!formData.name || !formData.backend) {
      onError?.('name and backend are required');
      return;
    }
    try {
      const payload: RunnerProfileCreate = {
        name: formData.name,
        description: formData.description || null,
        backend: formData.backend,
        provider: formData.provider || null,
        model: formData.model ? encodeModel(formData.model, formData.provider, formData.backend) : null,
        timeout_seconds: formData.timeout_seconds || null,
        base_url: formData.base_url || null,
        api_key_env: formData.api_key_env || null,
        api_token_id: formData.api_token_id || null,
        params: formData.params || {},
        headers: formData.headers || {},
        extra_args: formData.extra_args || [],
        is_enabled: formData.is_enabled ?? true,
        is_system_default: formData.is_system_default ?? false,
      };
      const created = await api.createRunnerProfile(payload);
      onSaved(created);
    } catch (e) {
      onError?.(errMsg(e, 'failed to create profile'));
    }
  };

  const handleUpdate = async (id: string) => {
    try {
      const patch: RunnerProfilePatch = {
        name: formData.name || undefined,
        description: formData.description ?? undefined,
        backend: formData.backend || undefined,
        provider: formData.provider ?? undefined,
        model:
          formData.model === undefined
            ? undefined
            : formData.model
              ? encodeModel(formData.model, formData.provider, formData.backend)
              : null,
        timeout_seconds: formData.timeout_seconds ?? undefined,
        base_url: credentialsUnlocked ? (formData.base_url ?? undefined) : undefined,
        api_key_env: credentialsUnlocked ? (formData.api_key_env ?? undefined) : undefined,
        api_token_id: formData.api_token_id ?? undefined,
        params: formData.params || undefined,
        headers: formData.headers || undefined,
        extra_args: formData.extra_args || undefined,
        is_enabled: formData.is_enabled,
        is_system_default: formData.is_system_default,
      };
      const updated = await api.updateRunnerProfile(id, patch);
      onSaved(updated);
    } catch (e) {
      onError?.(errMsg(e, 'failed to update profile'));
    }
  };

  // On create, credentials should be editable by default.
  // On edit they are locked until the user unlocks them.
  const credentialsEditable = mode === 'create' || credentialsUnlocked;

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-header">
          <h2>
            {mode === 'create' ? 'Create Runner Profile' : `Edit · ${formData.name || formData.id}`}
          </h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="modal-body">
          {/* ── Identity ───────────────────────────────────────── */}
          <section className="form-section">
            <div className="form-section-header"><span>Identity</span></div>
            <div className="form-grid">
              <div className="form-field full">
                <label>Name</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => handleFormChange('name', e.target.value)}
                  placeholder="My Profile"
                />
              </div>
              {mode === 'edit' && (
                <div className="form-field full">
                  <label>ID <span className="dim" style={{ fontWeight: 400 }}>(read-only)</span></label>
                  <input type="text" value={formData.id} disabled />
                </div>
              )}
              <div className="form-field full">
                <label>Description</label>
                <input
                  type="text"
                  value={formData.description || ''}
                  onChange={(e) => handleFormChange('description', e.target.value)}
                  placeholder="Optional description"
                />
              </div>
            </div>
          </section>

          {/* ── Routing ────────────────────────────────────────── */}
          <section className="form-section">
            <div className="form-section-header"><span>Routing</span></div>
            <div className="form-grid">
              <div className="form-field">
                <label>Backend</label>
                <select
                  value={formData.backend}
                  onChange={(e) => {
                    const v = e.target.value;
                    handleFormChange('backend', v);
                    const nextBackend = backends.find((b) => b.id === v);
                    if (
                      nextBackend &&
                      formData.provider &&
                      !nextBackend.compatible_providers.includes(formData.provider)
                    ) {
                      handleFormChange('provider', null);
                      handleFormChange('model', null);
                      handleFormChange('base_url', '');
                      handleFormChange('api_key_env', '');
                    }
                  }}
                >
                  {backends.length === 0 ? (
                    <option value="token">token</option>
                  ) : (
                    backends.map((b) => (
                      <option key={b.id} value={b.id}>{b.label}</option>
                    ))
                  )}
                </select>
                {currentBackend && currentBackend.compatible_providers.length === 0 && (
                  <div className="form-hint">
                    No external providers — runs use the backend's own credentials.
                  </div>
                )}
              </div>

              <div className="form-field">
                <label>Provider</label>
                <select
                  value={formData.provider || ''}
                  onChange={(e) => {
                    const v = e.target.value || null;
                    handleFormChange('provider', v);
                    const prov = providers.find((p) => p.id === v);
                    handleFormChange('base_url', prov?.default_base_url ?? '');
                    handleFormChange('api_key_env', prov?.default_api_key_env ?? '');
                    handleFormChange('model', '');
                  }}
                  disabled={
                    currentBackend != null && currentBackend.compatible_providers.length === 0
                  }
                >
                  <option value="">None</option>
                  {compatibleProviders.map((p) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
                {providerIncompatible && (
                  <div className="form-hint error">
                    ⚠ &quot;{formData.provider}&quot; is not compatible with backend &quot;{formData.backend}&quot;.
                  </div>
                )}
              </div>

              <div className="form-field">
                <label>
                  Model
                  {currentProvider?.supports_model_listing && (
                    <span className="dim" style={{ fontSize: 11, marginLeft: 6, fontWeight: 400 }}>
                      {modelsLoading ? '(loading…)' : `(${providerModels.length} available)`}
                    </span>
                  )}
                </label>
                {currentProvider && currentProvider.supports_model_listing ? (
                  <select
                    value={formData.model || ''}
                    onChange={(e) => handleFormChange('model', e.target.value || null)}
                    disabled={modelsLoading || providerModels.length === 0}
                  >
                    <option value="">
                      {modelsLoading
                        ? 'loading models…'
                        : providerModels.length === 0
                          ? 'no models available'
                          : 'select a model'}
                    </option>
                    {providerModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                    {formData.model && !providerModels.includes(formData.model) && (
                      <option key={formData.model} value={formData.model}>
                        {formData.model} (legacy)
                      </option>
                    )}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={formData.model || ''}
                    onChange={(e) => handleFormChange('model', e.target.value || null)}
                    placeholder={
                      currentBackend?.default_model
                        ? `default: ${currentBackend.default_model}`
                        : 'model id (raw)'
                    }
                    autoComplete="off"
                  />
                )}
                {modelsError && (
                  <div className="form-hint error">
                    ⚠ {modelsError} — set the API-key env var and try again.
                  </div>
                )}
              </div>

              <div className="form-field">
                <label>Timeout (seconds)</label>
                <input
                  type="number"
                  value={formData.timeout_seconds || ''}
                  onChange={(e) =>
                    handleFormChange('timeout_seconds', e.target.value ? parseInt(e.target.value) : null)
                  }
                  placeholder="300"
                />
              </div>
            </div>
          </section>

          {/* ── Credentials ────────────────────────────────────── */}
          <section className="form-section">
            <div className="form-section-header">
              <span>Credentials</span>
              {mode === 'edit' && (
                <button
                  type="button"
                  className={`unlock-btn ${credentialsUnlocked ? 'active' : ''}`}
                  onClick={() => setCredentialsUnlocked((v) => !v)}
                >
                  {credentialsUnlocked ? '🔓 Locked on save' : '🔒 Click to edit'}
                </button>
              )}
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Base URL</label>
                <input
                  type="text"
                  value={formData.base_url || ''}
                  onChange={(e) => handleFormChange('base_url', e.target.value || null)}
                  placeholder={currentProvider?.default_base_url || 'https://api.example.com'}
                  disabled={
                    !credentialsEditable ||
                    (currentProvider != null && !currentProvider.supports_base_url)
                  }
                />
              </div>
              <div className="form-field">
                <label>API Key Env Var</label>
                <input
                  type="text"
                  value={formData.api_key_env || ''}
                  onChange={(e) => handleFormChange('api_key_env', e.target.value || null)}
                  placeholder={currentProvider?.default_api_key_env || 'OPENAI_API_KEY'}
                  disabled={!credentialsEditable}
                />
              </div>
              <div className="form-field full">
                <label>Assigned API Token</label>
                <select
                  value={formData.api_token_id || ''}
                  onChange={(e) => handleFormChange('api_token_id', e.target.value || null)}
                >
                  <option value="">— none —</option>
                  {apiTokens.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.environment} / {t.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {mode === 'edit' && !credentialsUnlocked && (
              <div className="form-hint" style={{ marginTop: 8 }}>
                Base URL and API Key Env are locked. Click &quot;Click to edit&quot; above to change them.
              </div>
            )}
          </section>

          {/* ── Flags ──────────────────────────────────────────── */}
          <section className="form-section">
            <div className="form-section-header"><span>Status</span></div>
            <div className="checkbox-row">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_enabled ?? true}
                  onChange={(e) => handleFormChange('is_enabled', e.target.checked)}
                />
                Enabled
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_system_default ?? false}
                  onChange={(e) => handleFormChange('is_system_default', e.target.checked)}
                />
                System Default
              </label>
            </div>
          </section>
        </div>

        <div className="modal-footer">
          <div>
            {mode === 'edit' && onDelete && (
              <button
                onClick={() => onDelete(formData.id)}
                style={{ background: 'none', border: '1px solid var(--error)', color: 'var(--error)' }}
              >
                Delete
              </button>
            )}
          </div>
          <div className="footer-actions">
            <button onClick={onClose} style={{ background: 'var(--bg-secondary)' }}>
              Cancel
            </button>
            <button onClick={() => (mode === 'create' ? handleCreate() : handleUpdate(formData.id))}>
              {mode === 'create' ? 'Create' : 'Update'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
