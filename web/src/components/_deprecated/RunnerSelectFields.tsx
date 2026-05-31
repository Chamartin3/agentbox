/**
 * Backend / Provider / Model picker, shared between RunnerProfilesPage and
 * AgentNew so the two forms stay in sync as new backends/providers are added.
 *
 * Controlled component — parent owns the state. The picker handles:
 *   - fetching `/api/runner-backends` and `/api/runner-providers?backend=…`
 *   - filtering the provider list to ones compatible with the chosen backend
 *   - clearing provider/model when the chosen backend becomes incompatible
 *   - rendering a curated model `<select>` when the provider supports listing,
 *     and a raw `<input>` otherwise
 *
 * Model encoding (provider:model prefix for the token backend) is a concern
 * of the parent form on submit — this picker only round-trips the raw model
 * string the user picked.
 */

import { useEffect, useMemo, useState } from 'react';
import { api, type RunnerBackend, type RunnerProvider } from '../api/client';
import { BackendId } from '../api/enums';

export interface RunnerSelectValue {
  backend: string;
  provider: string | null;
  model: string | null;
  base_url?: string | null;
  api_key_env?: string | null;
}

export interface RunnerSelectFieldsProps {
  value: RunnerSelectValue;
  onChange: (next: RunnerSelectValue) => void;
  /** Hide the base_url / api_key_env fields (useful on the agent form). */
  showRouting?: boolean;
}

export default function RunnerSelectFields({
  value,
  onChange,
  showRouting = false,
}: RunnerSelectFieldsProps) {
  const [backends, setBackends] = useState<RunnerBackend[]>([]);
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => {
    api.listRunnerBackends().then(setBackends).catch(() => setBackends([]));
    api.listRunnerProviders().then(setProviders).catch(() => setProviders([]));
  }, []);

  const currentBackend = backends.find((b) => b.id === value.backend) || null;
  const currentProvider = providers.find((p) => p.id === value.provider) || null;

  const compatibleProviders = useMemo(() => {
    if (!currentBackend) return providers;
    const allow = new Set(currentBackend.compatible_providers);
    return providers.filter((p) => allow.has(p.id));
  }, [providers, currentBackend]);

  const providerIncompatible =
    value.provider != null &&
    currentBackend != null &&
    !currentBackend.compatible_providers.includes(value.provider);

  useEffect(() => {
    setModels([]);
    setModelsError(null);
    if (!currentProvider || !currentProvider.supports_model_listing) return;
    let cancelled = false;
    setModelsLoading(true);
    const opts: { base_url?: string; api_key_env?: string; backend?: string } = {};
    if (value.base_url) opts.base_url = value.base_url;
    if (value.api_key_env) opts.api_key_env = value.api_key_env;
    if (value.backend) opts.backend = value.backend;
    api
      .listProviderModels(currentProvider.id, opts)
      .then((r) => {
        if (cancelled) return;
        setModels((r || []).map((m) => m.id).sort());
      })
      .catch((e) => {
        if (cancelled) return;
        setModels([]);
        setModelsError(e instanceof Error ? e.message : 'failed to load models');
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [currentProvider?.id, value.backend, value.base_url, value.api_key_env]);

  const setBackend = (next: string) => {
    const b = backends.find((x) => x.id === next);
    const stillCompat = b && value.provider
      ? b.compatible_providers.includes(value.provider)
      : true;
    onChange({
      ...value,
      backend: next,
      provider: stillCompat ? value.provider : null,
      model: stillCompat ? value.model : null,
      base_url: stillCompat ? value.base_url : '',
      api_key_env: stillCompat ? value.api_key_env : '',
    });
  };

  const setProvider = (next: string | null) => {
    const prov = providers.find((p) => p.id === next);
    onChange({
      ...value,
      provider: next,
      base_url: prov?.default_base_url ?? '',
      api_key_env: prov?.default_api_key_env ?? '',
      model: null,
    });
  };

  return (
    <>
      <div>
        <label>Backend</label>
        <select value={value.backend} onChange={(e) => setBackend(e.target.value)}>
          {backends.length === 0 ? (
            <option value={value.backend}>{value.backend}</option>
          ) : (
            backends.map((b) => (
              <option key={b.id} value={b.id}>{b.label}</option>
            ))
          )}
        </select>
        {currentBackend && currentBackend.compatible_providers.length === 0 && (
          <div className="dim" style={{ fontSize: 11, marginTop: 4 }}>
            No external providers — runs use the backend's own credentials.
          </div>
        )}
      </div>

      <div>
        <label>Provider</label>
        <select
          value={value.provider || ''}
          onChange={(e) => setProvider(e.target.value || null)}
          disabled={currentBackend != null && currentBackend.compatible_providers.length === 0}
        >
          <option value="">None</option>
          {compatibleProviders.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
        {providerIncompatible && (
          <div
            className="dim"
            style={{ fontSize: 11, marginTop: 4, color: 'var(--error, #b91c1c)' }}
          >
            ⚠ "{value.provider}" is not compatible with backend "{value.backend}".
          </div>
        )}
      </div>

      <div>
        <label>
          Model
          {currentProvider?.supports_model_listing && (
            <span className="dim" style={{ fontSize: 11, marginLeft: 6 }}>
              {modelsLoading ? '(loading…)' : `(${models.length} available)`}
            </span>
          )}
        </label>
        {currentProvider?.supports_model_listing ? (
          <select
            value={value.model || ''}
            onChange={(e) => onChange({ ...value, model: e.target.value || null })}
            disabled={modelsLoading || models.length === 0}
          >
            <option value="">
              {modelsLoading
                ? 'loading models…'
                : models.length === 0
                  ? 'no models available'
                  : 'select a model'}
            </option>
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
            {value.model && !models.includes(value.model) && (
              <option key={value.model} value={value.model}>
                {value.model} (legacy)
              </option>
            )}
          </select>
        ) : (
          <input
            type="text"
            value={value.model || ''}
            onChange={(e) => onChange({ ...value, model: e.target.value || null })}
            placeholder={
              currentBackend?.default_model
                ? `default: ${currentBackend.default_model}`
                : 'model id (raw)'
            }
            autoComplete="off"
          />
        )}
        {modelsError && (
          <div
            className="dim"
            style={{ fontSize: 11, marginTop: 4, color: 'var(--error, #b91c1c)' }}
          >
            ⚠ {modelsError}
          </div>
        )}
      </div>

      {showRouting && (
        <>
          <div>
            <label>Base URL</label>
            <input
              type="text"
              value={value.base_url || ''}
              onChange={(e) => onChange({ ...value, base_url: e.target.value || null })}
              placeholder={currentProvider?.default_base_url || 'https://api.example.com'}
              disabled={currentProvider != null && !currentProvider.supports_base_url}
            />
          </div>
          <div>
            <label>API Key Env Var</label>
            <input
              type="text"
              value={value.api_key_env || ''}
              onChange={(e) => onChange({ ...value, api_key_env: e.target.value || null })}
              placeholder={currentProvider?.default_api_key_env || 'OPENAI_API_KEY'}
            />
          </div>
        </>
      )}
    </>
  );
}

/** `provider:model` for the token backend; verbatim for CLI backends. */
export function encodeModelForBackend(
  model: string | null | undefined,
  provider: string | null | undefined,
  backend: string | null | undefined,
): string | null {
  if (!model) return null;
  if (backend !== BackendId.Token) return model;
  if (!provider) return model;
  if (model.startsWith(`${provider}:`)) return model;
  if (model.includes(':')) return model;
  return `${provider}:${model}`;
}
