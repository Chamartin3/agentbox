import { useEffect, useState } from 'react';

interface ApiToken {
  id: string;
  environment: string;
  name: string;
  last_four: string;
  created_at: string;
  updated_at: string;
}

interface CreatedToken extends ApiToken {
  secret: string;
}

export default function SettingsApiTokensTab() {
  const [items, setItems] = useState<ApiToken[]>([]);
  const [env, setEnv] = useState('dev');
  const [name, setName] = useState('');
  const [secret, setSecret] = useState('');
  const [justCreated, setJustCreated] = useState<CreatedToken | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function reload() {
    const r = await fetch('/api/api-tokens');
    const data = await r.json();
    setItems(data.items || []);
  }

  useEffect(() => {
    reload().catch(console.error);
  }, []);

  async function create() {
    setStatus(null);
    setJustCreated(null);
    const r = await fetch('/api/api-tokens', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ environment: env, name, secret }),
    });
    if (!r.ok) {
      setStatus(`create failed: ${r.status} ${await r.text()}`);
      return;
    }
    const data = await r.json();
    setJustCreated(data);
    setName('');
    setSecret('');
    await reload();
  }

  async function rotate(id: string) {
    const next = prompt('new secret (min 4 chars):');
    if (!next || next.length < 4) return;
    const r = await fetch(`/api/api-tokens/${id}/rotate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ secret: next }),
    });
    if (!r.ok) {
      setStatus(`rotate failed: ${r.status}`);
      return;
    }
    setStatus('rotated.');
    await reload();
  }

  async function rename(id: string, current: string) {
    const next = prompt('new name:', current);
    if (!next || next === current) return;
    const r = await fetch(`/api/api-tokens/${id}`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name: next }),
    });
    if (!r.ok) {
      setStatus(`rename failed: ${r.status}`);
      return;
    }
    await reload();
  }

  async function remove(id: string) {
    if (!confirm('delete this token?')) return;
    const r = await fetch(`/api/api-tokens/${id}`, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) {
      setStatus(`delete failed: ${r.status}`);
      return;
    }
    await reload();
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="stack" style={{ border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
        <h3 style={{ margin: 0 }}>Create token</h3>
        <div className="row" style={{ gap: 8 }}>
          <input
            placeholder="environment (e.g. dev, prod)"
            value={env}
            onChange={(e) => setEnv(e.target.value)}
            style={{ width: 180 }}
          />
          <input
            placeholder="name (e.g. openai)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: 200 }}
          />
          <input
            placeholder="secret"
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            style={{ flex: 1 }}
          />
          <button onClick={create} disabled={!env || !name || secret.length < 4}>
            create
          </button>
        </div>
        {justCreated && (
          <div
            className="stack"
            style={{ background: '#fff8e1', padding: 8, borderRadius: 4, color: '#664d00' }}
          >
            <strong>Secret created. Copy it now — it won't be shown again.</strong>
            <code style={{ wordBreak: 'break-all' }}>{justCreated.secret}</code>
          </div>
        )}
        {status && <span className="dim">{status}</span>}
      </div>

      <table>
        <thead>
          <tr>
            <th>Environment</th>
            <th>Name</th>
            <th>Last 4</th>
            <th>Updated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 ? (
            <tr>
              <td colSpan={5} className="dim">
                no tokens yet.
              </td>
            </tr>
          ) : (
            items.map((t) => (
              <tr key={t.id}>
                <td>{t.environment}</td>
                <td>{t.name}</td>
                <td>
                  <code>…{t.last_four}</code>
                </td>
                <td className="dim">{t.updated_at}</td>
                <td className="row" style={{ gap: 6 }}>
                  <button onClick={() => rename(t.id, t.name)}>rename</button>
                  <button onClick={() => rotate(t.id)}>rotate</button>
                  <button onClick={() => remove(t.id)}>delete</button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
