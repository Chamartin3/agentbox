import { useEffect, useState } from 'react';
import { apiRequest } from '../api/http';

interface DeploymentEntry {
  name: string;
  env: string;
  value: string;
}
interface DeploymentPayload {
  groups: Record<string, DeploymentEntry[]>;
}

// Read-only view of the AGENTBOX_* process config (the SETTINGS singleton).
// These are read once at startup; change them via env / .env + restart.
export default function SettingsDeploymentTab() {
  const [data, setData] = useState<DeploymentPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    apiRequest<DeploymentPayload>('/api/settings/deployment')
      .then(setData)
      .catch((e) => setErr((e as Error).message));
  }, []);

  if (err) return <p className="dim">load failed: {err}</p>;
  if (!data) return <p className="dim">loading…</p>;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Read-only. Sourced from <code>AGENTBOX_*</code> env vars at startup — set via env / .env and restart to change.
      </p>
      {Object.entries(data.groups).map(([group, entries]) => (
        <div
          key={group}
          className="stack"
          style={{ gap: 6, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}
        >
          <h3 style={{ margin: 0 }}>{group}</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {entries.map((e) => (
                <tr key={e.name}>
                  <td style={{ padding: '2px 8px', width: 220 }}>
                    <code>{e.name}</code>
                  </td>
                  <td style={{ padding: '2px 8px', fontFamily: 'monospace' }}>{e.value || <span className="dim">—</span>}</td>
                  <td style={{ padding: '2px 8px' }} className="dim">
                    {e.env}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
