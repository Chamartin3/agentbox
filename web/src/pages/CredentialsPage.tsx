import { useEffect, useRef, useState } from 'react';
import Toast from '../components/common/Toast';
import { ApiError } from '../api/http';
import {
  credentialsApi,
  CredentialInventoryEntry,
  CredentialKind,
} from '../api/credentials';

type ToastState = { kind: 'ok' | 'error'; msg: string } | null;

// What a missing row hands to the add form to pre-fill it.
export interface CredentialPrefill {
  id: string;
  label: string;
  kind: CredentialKind;
  env_var: string | null;
  token: number; // bump to force the form to re-read even for the same id
}

// State shown as "how it's provided" (source) when present, so a green badge
// reads "env" / "file" / "db" instead of a bare "present".
function StateBadge({ entry, onAdd }: { entry: CredentialInventoryEntry; onAdd: () => void }) {
  if (entry.state === 'present')
    return <span style={{ color: '#3fb950' }} title={`present via ${entry.source}`}>● {entry.source}</span>;
  if (entry.state === 'invalid')
    return <span style={{ color: '#d29922' }} title="invalid">⚠ invalid</span>;
  return (
    <button
      onClick={onAdd}
      title="click to add this credential"
      style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: 'var(--link)', font: 'inherit' }}
    >
      ○ missing · add
    </button>
  );
}

function AddCredentialForm({
  onCreated,
  onToast,
  prefill,
}: {
  onCreated: () => void;
  onToast: (t: ToastState) => void;
  prefill: CredentialPrefill | null;
}) {
  const [id, setId] = useState('');
  const [label, setLabel] = useState('');
  const [kind, setKind] = useState<CredentialKind>('api_key');
  const [envVar, setEnvVar] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);

  // Pull identifying fields from a clicked missing row; secret stays blank.
  useEffect(() => {
    if (!prefill) return;
    setId(prefill.id);
    setLabel(prefill.label);
    setKind(prefill.kind);
    setEnvVar(prefill.env_var ?? '');
    setSecret('');
  }, [prefill]);

  const isApiKey = kind === 'api_key';

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await credentialsApi.create({
        id: id.trim(),
        label: label.trim(),
        kind,
        env_var: isApiKey ? envVar.trim() || null : null,
        secret,
      });
      onToast({ kind: 'ok', msg: `credential "${id.trim()}" added` });
      setId('');
      setLabel('');
      setEnvVar('');
      setSecret('');
      onCreated();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? typeof err.detail === 'string'
            ? err.detail
            : JSON.stringify(err.detail)
          : (err as Error).message;
      onToast({ kind: 'error', msg: `add failed: ${msg}` });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="stack"
      style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}
    >
      <h3 style={{ margin: 0 }}>Add credential</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 8, alignItems: 'center' }}>
        <label style={{ fontSize: 13 }}>id</label>
        <input type="text" value={id} onChange={(e) => setId(e.target.value)} placeholder="my_service" required />

        <label style={{ fontSize: 13 }}>label</label>
        <input type="text" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="My Service" required />

        <label style={{ fontSize: 13 }}>kind</label>
        <select value={kind} onChange={(e) => setKind(e.target.value as CredentialKind)}>
          <option value="api_key">api_key</option>
          <option value="login">login</option>
        </select>

        <label style={{ fontSize: 13 }}>env_var</label>
        <input
          type="text"
          value={envVar}
          onChange={(e) => setEnvVar(e.target.value)}
          placeholder={isApiKey ? 'MY_SERVICE_API_KEY (required)' : '(not used for login)'}
          disabled={!isApiKey}
          required={isApiKey}
        />

        <label style={{ fontSize: 13 }}>secret</label>
        <input
          type="password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder="secret value"
          required
        />
      </div>
      <div>
        <button type="submit" className="primary" disabled={busy}>
          {busy ? 'adding…' : 'add credential'}
        </button>
      </div>
    </form>
  );
}

export default function CredentialsPage({ embedded = false }: { embedded?: boolean } = {}) {
  const [items, setItems] = useState<CredentialInventoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState>(null);
  const [prefill, setPrefill] = useState<CredentialPrefill | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const addFromRow = (c: CredentialInventoryEntry) => {
    setPrefill({ id: c.id, label: c.label, kind: c.kind, env_var: c.env_var, token: Date.now() });
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  async function reload() {
    setLoading(true);
    try {
      const d = await credentialsApi.list();
      setItems(d.items);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function remove(id: string) {
    if (!confirm(`delete credential "${id}"?`)) return;
    try {
      await credentialsApi.remove(id);
      setToast({ kind: 'ok', msg: `${id} deleted` });
      await reload();
    } catch (e) {
      setToast({ kind: 'error', msg: `delete failed: ${(e as Error).message}` });
    }
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      {!embedded && <h1 style={{ margin: 0 }}>Credentials</h1>}
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Read-only sources (file/env) come from the host/compose; values are never shown. Add UI credentials below.
      </p>

      {err ? (
        <p className="dim">load failed: {err}</p>
      ) : loading ? (
        <p className="dim">loading…</p>
      ) : (
        <div
          className="stack"
          style={{ gap: 6, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}
        >
          {items.length === 0 ? (
            <p className="dim" style={{ margin: 0 }}>no credentials</p>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>state</th>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>id</th>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>label</th>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>kind</th>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>source</th>
                  <th style={{ textAlign: 'left', padding: '2px 8px' }}>env_var</th>
                  <th style={{ padding: '2px 8px' }}></th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id}>
                    <td style={{ padding: '2px 8px' }}>
                      <StateBadge entry={c} onAdd={() => addFromRow(c)} />
                    </td>
                    <td style={{ padding: '2px 8px' }}>
                      <code>{c.id}</code>
                    </td>
                    <td style={{ padding: '2px 8px' }}>{c.label}</td>
                    <td style={{ padding: '2px 8px' }} className="dim">{c.kind}</td>
                    <td style={{ padding: '2px 8px' }} className="dim">{c.source}</td>
                    <td style={{ padding: '2px 8px', fontFamily: 'monospace' }}>
                      {c.env_var || <span className="dim">—</span>}
                    </td>
                    <td style={{ padding: '2px 8px', textAlign: 'right' }}>
                      {c.source === 'db' ? (
                        <button className="dim" style={{ fontSize: 11 }} onClick={() => remove(c.id)}>
                          delete
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      <div ref={formRef}>
        <AddCredentialForm onCreated={reload} onToast={setToast} prefill={prefill} />
      </div>

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
