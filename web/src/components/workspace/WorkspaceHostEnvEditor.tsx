import { useEffect, useState } from 'react';
import { hostEnvApi, HostEnvCapability, HostEnvGrants } from '../../api/repo';

interface Props {
  workspaceId: string;
}

export default function WorkspaceHostEnvEditor({ workspaceId }: Props) {
  const [caps, setCaps] = useState<HostEnvCapability[]>([]);
  const [grants, setGrants] = useState<HostEnvGrants | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    try {
      const [capRes, grantRes] = await Promise.all([
        hostEnvApi.capabilities(),
        hostEnvApi.getWorkspace(workspaceId),
      ]);
      setCaps(capRes.capabilities);
      setGrants(grantRes);
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(grantRes.grants || {})) {
        next[k] = JSON.stringify(v, null, 2);
      }
      setDraft(next);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [workspaceId]);

  const toggleGrant = (capName: string, on: boolean, defaultJson = '{}') => {
    setDraft((prev) => {
      const next = { ...prev };
      if (on) next[capName] = defaultJson;
      else delete next[capName];
      return next;
    });
  };

  const updateGrant = (capName: string, json: string) => {
    setDraft((prev) => ({ ...prev, [capName]: json }));
  };

  const save = async () => {
    const parsed: Record<string, Record<string, unknown>> = {};
    for (const [k, v] of Object.entries(draft)) {
      try {
        parsed[k] = JSON.parse(v || '{}');
      } catch {
        alert(`Grant for "${k}" is not valid JSON.`);
        return;
      }
    }
    const reason = window.prompt('Reason for configuration change:', 'updated workspace host-env capabilities');
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    try {
      await hostEnvApi.setWorkspace(
        workspaceId,
        parsed,
        reason.trim(),
        grants?.profile_id ?? null,
      );
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="dim" style={{ fontSize: 12 }}>loading host-env capabilities…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;

  return (
    <div className="stack" style={{ gap: 12 }}>
      <p className="dim" style={{ fontSize: 11, marginTop: 0 }}>
        Host-environment capabilities <strong>available</strong> in this workspace
        (<em>provisioning</em>, not per-agent authorization). Scoping constraints
        (paths, allowlists) are JSON.
      </p>
      <table style={{ fontSize: 12, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left', width: 40 }}></th>
            <th style={{ textAlign: 'left' }}>Capability</th>
            <th style={{ textAlign: 'left' }}>Description</th>
            <th style={{ textAlign: 'left' }}>Scope (JSON)</th>
          </tr>
        </thead>
        <tbody>
          {caps.map((c) => {
            const enabled = c.name in draft || c.default_granted;
            const forced = c.default_granted;
            return (
              <tr key={c.name}>
                <td>
                  <input
                    type="checkbox"
                    checked={enabled}
                    disabled={forced || busy}
                    title={forced ? 'always granted' : ''}
                    onChange={(e) => toggleGrant(c.name, e.target.checked)}
                  />
                </td>
                <td>
                  <code>{c.name}</code>
                  {forced && <div className="dim" style={{ fontSize: 10 }}>(always)</div>}
                </td>
                <td style={{ maxWidth: 240 }}>{c.description}</td>
                <td>
                  {enabled && !forced ? (
                    <textarea
                      rows={3}
                      value={draft[c.name] ?? '{}'}
                      onChange={(e) => updateGrant(c.name, e.target.value)}
                      style={{ width: '100%', fontFamily: 'monospace', fontSize: 11 }}
                    />
                  ) : (
                    <span className="dim" style={{ fontSize: 11 }}>
                      schema: {Object.keys(c.grant_schema).join(', ') || '—'}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button onClick={save} disabled={busy} className="primary">
          {busy ? 'saving…' : 'save capabilities'}
        </button>
      </div>
    </div>
  );
}
