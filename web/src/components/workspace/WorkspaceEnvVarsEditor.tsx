import { useEffect, useState } from 'react';
import { api } from '../../api/client';

interface Props {
  workspaceId: string;
}

interface VarEntry {
  key: string;
  value: string;
}

export default function WorkspaceEnvVarsEditor({ workspaceId }: Props) {
  const [entries, setEntries] = useState<VarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const d = await api.getWorkspaceEnvVars(workspaceId);
      const vars = (d as Record<string, string>) || {};
      setEntries(
        Object.entries(vars).map(([key, value]) => ({ key, value })),
      );
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

  const updateKey = (idx: number, key: string) => {
    setEntries((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], key };
      return next;
    });
  };

  const updateValue = (idx: number, value: string) => {
    setEntries((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], value };
      return next;
    });
  };

  const add = () => {
    setEntries((prev) => [...prev, { key: '', value: '' }]);
  };

  const remove = (idx: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== idx));
  };

  const save = async () => {
    setSaving(true);
    try {
      const vars: Record<string, string> = {};
      for (const e of entries) {
        if (e.key.trim()) {
          vars[e.key.trim()] = e.value;
        }
      }
      const result = await api.setWorkspaceEnvVars(workspaceId, vars);
      const saved = (result as Record<string, string>) || {};
      setEntries(
        Object.entries(saved).map(([key, value]) => ({ key, value })),
      );
      setMsg({ kind: 'ok', text: `saved ${Object.keys(saved).length} env var(s)` });
    } catch (e) {
      setMsg({ kind: 'error', text: `save failed: ${(e as Error).message}` });
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Environment Variables</h3>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          {msg && (
            <span
              className={`pill ${msg.kind === 'ok' ? 'ok' : 'err'}`}
              style={{ fontSize: 11 }}
            >
              {msg.text}
            </span>
          )}
          <button onClick={save} disabled={saving || loading} className="primary">
            {saving ? 'saving…' : 'save env vars'}
          </button>
        </div>
      </div>

      <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
        Injected into the agent process at run time. Not a secrets store — avoid provider API keys (use Credentials).
      </p>

      {loading ? (
        <p className="dim" style={{ fontSize: 12 }}>
          loading…
        </p>
      ) : (
        <div className="stack" style={{ gap: 6 }}>
          {entries.map((entry, idx) => (
            <div key={idx} className="row" style={{ gap: 6, alignItems: 'center' }}>
              <input
                type="text"
                placeholder="KEY"
                value={entry.key}
                onChange={(e) => updateKey(idx, e.target.value)}
                style={{ width: 160, fontFamily: 'monospace', fontSize: 12 }}
              />
              <span style={{ fontSize: 12 }}>=</span>
              <input
                type="text"
                placeholder="value"
                value={entry.value}
                onChange={(e) => updateValue(idx, e.target.value)}
                style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }}
              />
              <button
                onClick={() => remove(idx)}
                className="danger"
                style={{ fontSize: 11, padding: '2px 8px' }}
                title="Remove this variable"
              >
                ✕
              </button>
            </div>
          ))}
          <div>
            <button onClick={add} className="secondary" style={{ fontSize: 11 }}>
              + add env var
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
