import { useEffect, useState } from 'react';
import {
  credentialsApi,
  WorkspaceCredentials,
  CredentialKind,
} from '../../api/credentials';
import Modal from '../common/Modal';

interface Props {
  workspaceId: string;
}

// Merged "Secrets & environment" card: enable global credentials for this
// workspace and (per workspace) remap each to a chosen env-var name — e.g.
// token "DS1" → DEEPSEEK_API_KEY here, "DS2" → DEEPSEEK_API_KEY elsewhere.
// Plaintext env vars were dropped; everything a run gets is a credential.
export default function WorkspaceSecretsEditor({ workspaceId }: Props) {
  const [data, setData] = useState<WorkspaceCredentials | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  // credential_id → env-var name typed in the "expose as" field
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const d = await credentialsApi.forWorkspace(workspaceId);
      setData(d);
      setEnabled(new Set(d.enabled));
      setOverrides({ ...d.overrides });
      setMsg(null);
    } catch (e) {
      setMsg({ kind: 'error', text: `load failed: ${(e as Error).message}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const toggle = (id: string) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      // Only send overrides for enabled api_key creds where the typed name
      // is non-empty and differs from the credential's default env-var.
      const payload: Record<string, string> = {};
      for (const c of data?.available ?? []) {
        if (!enabled.has(c.id)) continue;
        const name = (overrides[c.id] ?? '').trim();
        if (name && name !== c.env_var) payload[c.id] = name;
      }
      const result = await credentialsApi.setForWorkspace(
        workspaceId,
        [...enabled],
        payload,
      );
      setData(result);
      setEnabled(new Set(result.enabled));
      setOverrides({ ...result.overrides });
      setMsg({ kind: 'ok', text: `saved ${result.enabled.length} credential(s)` });
    } catch (e) {
      setMsg({ kind: 'error', text: `save failed: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  // "missing" credentials aren't configured on the host — can't be enabled.
  const visible = data?.available.filter((c) => c.state !== 'missing') ?? [];

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Secrets &amp; environment</h3>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          {msg && (
            <span className={`pill ${msg.kind === 'ok' ? 'ok' : 'err'}`} style={{ fontSize: 11 }}>
              {msg.text}
            </span>
          )}
          <button onClick={() => setCreating(true)} className="secondary" style={{ fontSize: 11 }}>
            + new credential
          </button>
          <button onClick={save} disabled={saving || loading} className="primary">
            {saving ? 'saving…' : 'save'}
          </button>
        </div>
      </div>

      <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
        Enable credentials for this workspace. Enabling ≥1 makes runs least-privilege (only the
        enabled secrets, not the whole host env). Set an "expose as" name to remap a token to a
        different env-var here.
      </p>

      {loading ? (
        <p className="dim" style={{ fontSize: 12 }}>loading…</p>
      ) : visible.length === 0 ? (
        <p className="dim" style={{ fontSize: 12 }}>
          No configured credentials. Add one in Settings or with "+ new credential".
        </p>
      ) : (
        <div className="stack" style={{ gap: 6 }}>
          {visible.map((c) => {
            const on = enabled.has(c.id);
            return (
              <div key={c.id} className="row" style={{ gap: 8, alignItems: 'center' }}>
                <label className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'center', flex: 1 }}>
                  <input type="checkbox" checked={on} onChange={() => toggle(c.id)} />
                  <code style={{ fontSize: 12 }}>{c.id}</code>
                  <span style={{ fontSize: 12 }}>{c.label}</span>
                  <span className="dim" style={{ fontSize: 11 }}>
                    {c.source} · {c.state}
                  </span>
                </label>
                {/* env-var remap only applies to api_key creds (login creds
                    aren't env-materialized). */}
                {on && c.kind === 'api_key' && (
                  <>
                    <span className="dim" style={{ fontSize: 11 }}>expose as</span>
                    <input
                      type="text"
                      placeholder={c.env_var ?? 'ENV_VAR'}
                      value={overrides[c.id] ?? ''}
                      onChange={(e) =>
                        setOverrides((prev) => ({ ...prev, [c.id]: e.target.value }))
                      }
                      style={{ width: 200, fontFamily: 'monospace', fontSize: 12 }}
                    />
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      {creating && (
        <NewCredentialModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </section>
  );
}

// Minimal inline create form — mirrors credentialsApi.create's body.
function NewCredentialModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [label, setLabel] = useState('');
  const [kind, setKind] = useState<CredentialKind>('api_key');
  const [envVar, setEnvVar] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await credentialsApi.create({
        label,
        kind,
        env_var: kind === 'api_key' ? envVar : null,
        secret,
      });
      onCreated();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New credential"
      onClose={onClose}
      footer={
        <>
          {err && <span className="pill err" style={{ fontSize: 11 }}>{err}</span>}
          <button onClick={onClose} className="secondary">cancel</button>
          <button
            onClick={submit}
            className="primary"
            disabled={busy || !label.trim() || !secret || (kind === 'api_key' && !envVar.trim())}
          >
            {busy ? 'saving…' : 'create'}
          </button>
        </>
      }
    >
      <div className="stack" style={{ gap: 8 }}>
        <label className="stack" style={{ gap: 2 }}>
          <span className="dim" style={{ fontSize: 11 }}>label</span>
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="DeepSeek key" />
        </label>
        <label className="stack" style={{ gap: 2 }}>
          <span className="dim" style={{ fontSize: 11 }}>kind</span>
          <select value={kind} onChange={(e) => setKind(e.target.value as CredentialKind)}>
            <option value="api_key">api_key</option>
            <option value="login">login</option>
          </select>
        </label>
        {kind === 'api_key' && (
          <label className="stack" style={{ gap: 2 }}>
            <span className="dim" style={{ fontSize: 11 }}>env var (default name)</span>
            <input
              value={envVar}
              onChange={(e) => setEnvVar(e.target.value)}
              placeholder="DEEPSEEK_API_KEY"
              style={{ fontFamily: 'monospace' }}
            />
          </label>
        )}
        <label className="stack" style={{ gap: 2 }}>
          <span className="dim" style={{ fontSize: 11 }}>secret</span>
          <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} />
        </label>
      </div>
    </Modal>
  );
}
