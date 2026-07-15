import { useEffect, useState } from 'react';
import Toast from '../components/common/Toast';
import { apiRequest } from '../api/http';
import { SecretsForm, type ToastState } from './SettingsBaseTab';

interface EnvSecrets {
  names: string[];
  files: string[];
}

// Read-only companion: secret *names* discovered in the on-disk .env files
// (creds env). Values are never returned by the API — these are set by editing
// the .env / exporting env and restarting, not through the UI.
function EnvSecretsList() {
  const [data, setData] = useState<EnvSecrets | null>(null);

  useEffect(() => {
    apiRequest<EnvSecrets>('/api/settings/env-secrets')
      .then(setData)
      .catch(() => setData({ names: [], files: [] }));
  }, []);

  if (!data) return <p className="dim">loading…</p>;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Present in the .env files (read-only — edit the file + restart to change).
        {data.files.length > 0 && <> Source: <code>{data.files.join(', ')}</code></>}
      </p>
      {data.names.length === 0 && <p className="dim">none found</p>}
      {data.names.map((n) => (
        <div key={n} style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 8, alignItems: 'center' }}>
          <code style={{ fontSize: 13 }}>{n}</code>
          <span className="dim" style={{ fontSize: 12 }}>● set</span>
        </div>
      ))}
    </div>
  );
}

export default function SettingsSecretsTab() {
  const [toast, setToast] = useState<ToastState>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
        <h3 style={{ margin: 0 }}>DB secrets</h3>
        <SecretsForm onToast={setToast} />
      </div>
      <div className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
        <h3 style={{ margin: 0 }}>Environment (.env)</h3>
        <EnvSecretsList />
      </div>
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
