import { useEffect, useState } from 'react';
import { api, type RunnerProvider } from '../api/client';
import Toast from '../components/common/Toast';
import RunnerProfilesPage from './RunnerProfilesPage';
import { RuntimeDefaultsForm, type ToastState } from './SettingsBaseTab';
import { HarnessBadge, ProviderBadge } from '../components/runner/RunnerBadges';

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      {hint && <p className="dim" style={{ fontSize: 12, margin: 0 }}>{hint}</p>}
      {children}
    </section>
  );
}

function ProvidersSection({ onToast }: { onToast: (t: ToastState) => void }) {
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api.listRunnerProviders().then(setProviders).catch((e) => onToast({ kind: 'error', msg: `load providers: ${e.message}` }));
  }, [onToast]);

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
          <th style={{ textAlign: 'left' }}>Backends</th>
          <th style={{ textAlign: 'left' }}>Models</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {providers.length === 0 ? (
          <tr><td colSpan={4} className="dim">no providers</td></tr>
        ) : (
          providers.map((p) => (
            <tr key={p.id}>
              <td><ProviderBadge provider={p.id} /> <span className="dim">{p.label}</span></td>
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
                        {models[p.id].map((m) => <li key={m}>{m}</li>)}
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
                  <button onClick={() => fetchModels(p.id)} disabled={busy === p.id} style={{ fontSize: 11 }}>
                    {busy === p.id ? 'fetching…' : 'fetch models'}
                  </button>
                ) : (
                  <span className="dim" style={{ fontSize: 11 }}>static</span>
                )}
              </td>
            </tr>
          ))
        )}
      </tbody>
    </table>
  );
}

// Settings → Runner Profiles: harness defaults, runner profiles, providers.
export default function SettingsRunnerProfilesTab() {
  const [toast, setToast] = useState<ToastState>(null);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <Section title="Harness defaults" hint="Default model per backend + runner timeout. Backends consult these on every run.">
        <RuntimeDefaultsForm onToast={setToast} />
      </Section>
      <Section title="Profiles">
        <RunnerProfilesPage embedded />
      </Section>
      <Section title="Providers" hint="Discovered provider adapters. Providers are registered via plugins/opencode discovery — add a new one via a runner profile.">
        <ProvidersSection onToast={setToast} />
      </Section>
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
