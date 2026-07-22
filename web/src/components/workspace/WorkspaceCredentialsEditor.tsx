import { useEffect, useState } from 'react';
import { credentialsApi, WorkspaceCredentials } from '../../api/credentials';

interface Props {
  workspaceId: string;
}

export default function WorkspaceCredentialsEditor({ workspaceId }: Props) {
  const [data, setData] = useState<WorkspaceCredentials | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const d = await credentialsApi.forWorkspace(workspaceId);
      setData(d);
      setEnabled(new Set(d.enabled));
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
      const result = await credentialsApi.setForWorkspace(workspaceId, [...enabled]);
      setData(result);
      setEnabled(new Set(result.enabled));
      setMsg({ kind: 'ok', text: `saved ${result.enabled.length} enabled credential(s)` });
    } catch (e) {
      setMsg({ kind: 'error', text: `save failed: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Credentials</h3>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          {msg && (
            <span className={`pill ${msg.kind === 'ok' ? 'ok' : 'err'}`} style={{ fontSize: 11 }}>
              {msg.text}
            </span>
          )}
          <button onClick={save} disabled={saving || loading} className="primary">
            {saving ? 'saving…' : 'save credentials'}
          </button>
        </div>
      </div>

      <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
        Enabling ≥1 credential makes this workspace least-privilege: runs get ONLY the enabled credentials, not the whole
        host env.
      </p>

      {loading ? (
        <p className="dim" style={{ fontSize: 12 }}>loading…</p>
      ) : !data || data.available.length === 0 ? (
        <p className="dim" style={{ fontSize: 12 }}>No credentials available.</p>
      ) : (
        <div className="stack" style={{ gap: 6 }}>
          {data.available.map((c) => (
            <label key={c.id} className="row" style={{ gap: 8, cursor: 'pointer', alignItems: 'center' }}>
              <input type="checkbox" checked={enabled.has(c.id)} onChange={() => toggle(c.id)} />
              <code style={{ fontSize: 12 }}>{c.id}</code>
              <span style={{ fontSize: 12 }}>{c.label}</span>
              <span className="dim" style={{ fontSize: 11 }}>
                {c.source} · {c.state}
              </span>
            </label>
          ))}
        </div>
      )}
    </section>
  );
}
