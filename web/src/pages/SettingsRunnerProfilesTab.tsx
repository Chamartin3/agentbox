import { useEffect, useState } from 'react';
import { api, type RunnerProvider, type RunnerBackend } from '../api/client';
import { apiRequest } from '../api/http';
import { credentialsApi, type CredentialInventoryEntry } from '../api/credentials';
import Toast from '../components/common/Toast';
import RunnerProfilesPage from './RunnerProfilesPage';
import CredentialsPage, { type CredentialPrefill } from './CredentialsPage';
import SettingsApiTokensTab from './SettingsApiTokensTab';
import { RuntimeDefaultsForm, type ToastState } from './SettingsBaseTab';
import { HarnessBadge, ProviderBadge } from '../components/runner/RunnerBadges';

// Backends whose default model the runtime actually reads (runtime_defaults keys).
const HARNESS_MODEL_KEY: Record<string, string> = {
  opencode: 'default_model_opencode',
  codex: 'default_model_codex',
  pi: 'default_model_pi',
};

// Resolve a harness's auth from the credential inventory: prefer its own
// login credential (id == backend id), else an api-key from a compatible
// provider. Returns null when the harness needs no auth.
function harnessAuth(b: RunnerBackend, creds: CredentialInventoryEntry[]) {
  const own = creds.find((c) => c.id === b.id);
  if (own) return { method: own.kind, present: own.state === 'present', via: own.env_var ?? own.id };
  const provHit = b.compatible_providers
    .map((p) => creds.find((c) => c.id === p))
    .find((c): c is CredentialInventoryEntry => !!c);
  if (provHit) return { method: 'api_key' as const, present: provHit.state === 'present', via: provHit.env_var ?? provHit.id };
  return null;
}

function HarnessesSection({
  onToast,
  onAddCredential,
}: {
  onToast: (t: ToastState) => void;
  onAddCredential: (p: CredentialPrefill) => void;
}) {
  const [backends, setBackends] = useState<RunnerBackend[]>([]);
  const [creds, setCreds] = useState<CredentialInventoryEntry[]>([]);
  const [defaults, setDefaults] = useState<Record<string, unknown>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [models, setModels] = useState<Record<string, string[]>>({});

  useEffect(() => {
    api.listRunnerBackends()
      // The token (pydantic-ai) backend is a raw model caller, not an agentic
      // harness — it has no harness logic of its own, so hide it here.
      .then((bs) => setBackends(bs.filter((b) => b.id !== 'token')))
      .catch((e) => onToast({ kind: 'error', msg: `load harnesses: ${e.message}` }));
    credentialsApi.list().then((r) => setCreds(r.items)).catch(() => setCreds([]));
    apiRequest<{ values: Record<string, unknown> }>('/api/settings/runtime_defaults')
      .then((d) => setDefaults(d.values || {}))
      .catch(() => setDefaults({}));
  }, [onToast]);

  // Fetch model lists for the providers each harness can drive, so the
  // default-model field is a dropdown of real models (uses the backend cache).
  useEffect(() => {
    const provIds = Array.from(new Set(backends.flatMap((b) => b.compatible_providers)));
    if (provIds.length === 0) return;
    Promise.allSettled(
      provIds.map((pid) => api.listProviderModels(pid).then((rows) => ({ pid, ids: rows.map((r) => r.id) }))),
    ).then((results) => {
      const batch: Record<string, string[]> = {};
      for (const r of results) if (r.status === 'fulfilled') batch[r.value.pid] = r.value.ids;
      setModels(batch);
    });
  }, [backends]);

  const saveModel = async (b: RunnerBackend) => {
    const key = HARNESS_MODEL_KEY[b.id];
    if (!key) return;
    const value = (drafts[b.id] ?? '').trim() || null;
    try {
      await apiRequest('/api/settings/runtime_defaults', {
        method: 'PATCH',
        body: JSON.stringify({ values: { [key]: value } }),
      });
      setDefaults((p) => ({ ...p, [key]: value }));
      onToast({ kind: 'ok', msg: `${b.id} default model saved` });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  };

  return (
    <table style={{ fontSize: 12, width: '100%' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left' }}>Harness</th>
          <th style={{ textAlign: 'left' }}>Auth</th>
          <th style={{ textAlign: 'left' }}>Compatible providers</th>
          <th style={{ textAlign: 'left' }}>Default model</th>
        </tr>
      </thead>
      <tbody>
        {backends.length === 0 ? (
          <tr><td colSpan={4} className="dim">no harnesses</td></tr>
        ) : (
          backends.map((b) => {
            const auth = harnessAuth(b, creds);
            const key = HARNESS_MODEL_KEY[b.id];
            const stored = key ? (typeof defaults[key] === 'string' ? (defaults[key] as string) : '') : '';
            return (
              <tr key={b.id}>
                <td>
                  <HarnessBadge backend={b.id} />{' '}
                  {b.supports_mcp ? <span className="dim" title="supports MCP">· mcp</span> : <span className="dim" title="native tools only">· native</span>}
                </td>
                <td style={{ fontSize: 11 }}>
                  {!auth ? (
                    <span className="dim">— none needed</span>
                  ) : auth.present ? (
                    <span style={{ color: 'var(--ok, #3fb950)' }} title={auth.via}>✓ {auth.method === 'login' ? 'login' : 'api-key'}</span>
                  ) : (
                    <span style={{ color: 'var(--warn, #d29922)' }} title={auth.via}>
                      ⚠ {auth.method === 'login' ? 'login' : 'api-key'} · missing{' '}
                      <button
                        className="link"
                        style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--link)', font: 'inherit' }}
                        onClick={() => onAddCredential({
                          id: auth.via,
                          label: b.label,
                          kind: auth.method === 'login' ? 'login' : 'api_key',
                          env_var: auth.method === 'login' ? null : auth.via,
                          token: Date.now(),
                        })}
                      >
                        add
                      </button>
                    </span>
                  )}
                </td>
                <td>
                  <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                    {b.compatible_providers.map((p) => <ProviderBadge key={p} provider={p} />)}
                  </div>
                </td>
                <td>
                  {key ? (
                    <>
                      <input
                        list={`hm-${b.id}`}
                        style={{ fontSize: 11, width: '100%' }}
                        placeholder="(none)"
                        value={drafts[b.id] ?? stored}
                        onChange={(e) => setDrafts((p) => ({ ...p, [b.id]: e.target.value }))}
                        onBlur={() => { if ((drafts[b.id] ?? stored) !== stored) void saveModel(b); }}
                      />
                      <datalist id={`hm-${b.id}`}>
                        {Array.from(new Set(b.compatible_providers.flatMap((p) => models[p] ?? []))).map((m) => (
                          <option key={m} value={m} />
                        ))}
                      </datalist>
                    </>
                  ) : (
                    <span className="dim" title="fixed by the harness">{b.default_model ?? '—'}</span>
                  )}
                </td>
              </tr>
            );
          })
        )}
      </tbody>
    </table>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      {hint && <p className="dim" style={{ fontSize: 12, margin: 0 }}>{hint}</p>}
      {children}
    </section>
  );
}

function ProvidersSection({
  onToast,
  onAddCredential,
}: {
  onToast: (t: ToastState) => void;
  onAddCredential: (p: CredentialPrefill) => void;
}) {
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [creds, setCreds] = useState<CredentialInventoryEntry[]>([]);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api.listRunnerProviders().then(setProviders).catch((e) => onToast({ kind: 'error', msg: `load providers: ${e.message}` }));
    credentialsApi.list().then((r) => setCreds(r.items)).catch(() => setCreds([]));
  }, [onToast]);

  // Join a provider to its credential/env-var by matching the provider's
  // declared api-key env var against the credential inventory.
  const authFor = (p: RunnerProvider) => {
    if (!p.requires_api_key) return { kind: 'none' as const };
    const env = p.default_api_key_env;
    const present = creds.filter((c) => c.env_var === env && c.state === 'present');
    const hit = present[0] ?? creds.find((c) => c.env_var === env);
    if (hit && hit.state === 'present') return { kind: 'ok' as const, entry: hit };
    return { kind: 'missing' as const, env };
  };

  // Fetches models for all model-listing providers on mount (uses backend cache).
  useEffect(() => {
    if (providers.length === 0) return;
    const fetchAllModels = async () => {
      const listing = providers.filter((p) => p.supports_model_listing);
      const results = await Promise.allSettled(
        listing.map((p) =>
          api.listProviderModels(p.id).then((rows) => ({ id: p.id, models: rows.map((r) => (r as any).name || r.id) }))
        ),
      );
      const batch: Record<string, string[]> = {};
      for (const r of results) {
        if (r.status === 'fulfilled') batch[r.value.id] = r.value.models;
      }
      setModels((prev) => ({ ...batch, ...prev }));
    };
    fetchAllModels();
  }, [providers]);

  const fetchModels = async (id: string) => {
    setBusy(id);
    try {
      const rows = await api.listProviderModels(id, { refresh: true });
      setModels((p) => ({ ...p, [id]: rows.map((r) => r.name || r.id) }));
      onToast({ kind: 'ok', msg: `${id}: ${rows.length} model(s)` });
    } catch (e) {
      onToast({ kind: 'error', msg: `fetch models: ${(e as Error).message}` });
    } finally {
      setBusy(null);
    }
  };

  return (
    <table style={{ fontSize: 12, width: '100%' }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left' }}>Provider</th>
          <th style={{ textAlign: 'left' }}>Auth</th>
          <th style={{ textAlign: 'left' }}>Harnesses</th>
          <th style={{ textAlign: 'left' }}>Models</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {providers.length === 0 ? (
          <tr><td colSpan={5} className="dim">no providers</td></tr>
        ) : (
          providers.map((p) => {
            const auth = authFor(p);
            return (
            <tr key={p.id}>
              <td><ProviderBadge provider={p.id} /> <span className="dim">{p.label}</span></td>
              <td style={{ fontSize: 11 }}>
                {auth.kind === 'none' ? (
                  <span className="dim">— none needed</span>
                ) : auth.kind === 'ok' ? (
                  <span style={{ color: 'var(--ok, #3fb950)' }} title={`${auth.entry.env_var ?? auth.entry.id} · ${auth.entry.source}`}>
                    ✓ <code>{auth.entry.env_var ?? auth.entry.id}</code> <span className="dim">({auth.entry.source})</span>
                  </span>
                ) : (
                  <span style={{ color: 'var(--warn, #d29922)' }} title={`Set ${auth.env ?? 'the API key'} or add a credential`}>
                    ⚠ missing{auth.env ? <> · <code>{auth.env}</code></> : null}
                    {auth.env && (
                      <>
                        {' '}
                        <button
                          className="link"
                          style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--link)', font: 'inherit' }}
                          onClick={() => onAddCredential({ id: auth.env!, label: p.label, kind: 'api_key', env_var: auth.env!, token: Date.now() })}
                        >
                          add
                        </button>
                      </>
                    )}
                  </span>
                )}
              </td>
              <td>
                <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                  {p.compatible_backends.map((b) => <HarnessBadge key={b} backend={b} />)}
                </div>
              </td>
              <td>
                {models[p.id] ? (
                  <div>
                    <button
                      className="link"
                      style={{ fontSize: 12, padding: 0, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--link)' }}
                      onClick={() => setExpanded((prev) => ({ ...prev, [p.id]: !prev[p.id] }))}
                    >
                      {models[p.id].length} model(s)
                    </button>
                    {expanded[p.id] && (
                      <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 11, color: 'var(--dim)' }}>
                        {models[p.id].map((m) => (
                          <li key={m}>
                            <button
                              title="Click to copy model name"
                              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'inherit', font: 'inherit' }}
                              onClick={() => {
                                void navigator.clipboard.writeText(m);
                                onToast({ kind: 'ok', msg: `copied ${m}` });
                              }}
                            >
                              <code>{m}</code> ⧉
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  p.supports_model_listing ? (
                    <button
                      className="dim"
                      style={{ fontSize: 11, padding: 0, background: 'none', border: 'none', cursor: 'pointer' }}
                      onClick={() => fetchModels(p.id)}
                    >
                      — click to fetch
                    </button>
                  ) : (
                    <span className="dim">—</span>
                  )
                )}
              </td>
              <td style={{ textAlign: 'right' }}>
                {p.supports_model_listing ? (
                  <button
                    onClick={() => fetchModels(p.id)}
                    disabled={busy === p.id}
                    title="Update models"
                    aria-label="Update models"
                    style={{ fontSize: 13, lineHeight: 1, padding: '2px 6px', background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: busy === p.id ? 'default' : 'pointer' }}
                  >
                    {busy === p.id ? '…' : '↻'}
                  </button>
                ) : (
                  <span className="dim" style={{ fontSize: 11 }}>static</span>
                )}
              </td>
            </tr>
            );
          })
        )}
      </tbody>
    </table>
  );
}

// Settings → Runner Profiles: harness defaults, runner profiles, providers.
export default function SettingsRunnerProfilesTab() {
  const [toast, setToast] = useState<ToastState>(null);
  const [credPrefill, setCredPrefill] = useState<CredentialPrefill | null>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <Section title="Run timeout" hint="Max wall-clock per run. Backends consult this on every run.">
        <RuntimeDefaultsForm onToast={setToast} />
      </Section>
      <Section title="Harnesses" hint="Agentic runners: authentication, compatible providers, and default model (consulted on every run).">
        <HarnessesSection onToast={setToast} onAddCredential={setCredPrefill} />
      </Section>
      <Section title="Providers" hint="Discovered provider adapters. Providers are registered via plugins/opencode discovery — add a new one via a runner profile.">
        <ProvidersSection onToast={setToast} onAddCredential={setCredPrefill} />
      </Section>
      <Section title="Credentials">
        <CredentialsPage embedded externalPrefill={credPrefill} />
      </Section>
      <Section title="API tokens">
        <SettingsApiTokensTab />
      </Section>
      <Section title="Profiles">
        <RunnerProfilesPage embedded />
      </Section>
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
