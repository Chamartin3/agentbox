import { useEffect, useState } from 'react';
import Toast from '../components/common/Toast';
import { apiRequest } from '../api/http';

const SECTIONS = [
  {
    key: 'workspace_defaults',
    label: 'Workspace defaults',
    hint: 'Default permissions / scaffolding applied to new workspaces.',
  },
  {
    key: 'mcp_global',
    label: 'MCP global',
    hint: 'Global MCP server configuration shared by all workspaces.',
  },
  { key: 'webhook', label: 'Webhook', hint: 'Run-completion webhook URL, retries, signing key.' },
  { key: 'telemetry', label: 'Telemetry', hint: 'Anonymous usage telemetry opt-in / endpoint.' },
  { key: 'secrets', label: 'Secrets', hint: 'Write-only secret values. Existing values are never shown.' },
] as const;

interface SectionPayload {
  section: string;
  values: Record<string, unknown>;
  defaults?: Record<string, unknown>;
  overrides?: Record<string, unknown>;
}

export type ToastState = { kind: 'ok' | 'error'; msg: string } | null;

async function fetchSection(section: string): Promise<SectionPayload> {
  return apiRequest<SectionPayload>(`/api/settings/${section}`);
}

async function patchSection(section: string, values: Record<string, unknown>): Promise<void> {
  await apiRequest(`/api/settings/${section}`, {
    method: 'PATCH',
    body: JSON.stringify({ values }),
  });
}

function SectionShell({
  section,
  label,
  hint,
  children,
}: {
  section: string;
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h3 style={{ margin: 0 }}>{label}</h3>
        <code className="dim" style={{ fontSize: 12 }}>
          {section}
        </code>
      </div>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        {hint}
      </p>
      {children}
    </div>
  );
}

function inputRow(label: string, child: React.ReactNode) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 8, alignItems: 'center' }}>
      <label style={{ fontSize: 13 }}>{label}</label>
      {child}
    </div>
  );
}

export function RuntimeDefaultsForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'runtime_defaults';
  const [timeout, setTimeoutS] = useState<number | ''>('');
  const [opencode, setOpencode] = useState('');
  const [codex, setCodex] = useState('');
  const [pi, setPi] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        const v = d.values || {};
        setTimeoutS(typeof v.timeout_seconds === 'number' ? v.timeout_seconds : '');
        setOpencode(typeof v.default_model_opencode === 'string' ? v.default_model_opencode : '');
        setCodex(typeof v.default_model_codex === 'string' ? v.default_model_codex : '');
        setPi(typeof v.default_model_pi === 'string' ? v.default_model_pi : '');
        setLoaded(true);
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      await patchSection(section, {
        timeout_seconds: timeout === '' ? null : Number(timeout),
        default_model_opencode: opencode || null,
        default_model_codex: codex || null,
        default_model_pi: pi || null,
      });
      onToast({ kind: 'ok', msg: 'runtime defaults saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!loaded) return <p className="dim">loading…</p>;

  return (
    <div className="stack" style={{ gap: 8 }}>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Backends read these on every run — no restart needed.
      </p>
      {inputRow(
        'timeout_seconds',
        <input
          type="number"
          value={timeout}
          onChange={(e) => setTimeoutS(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          placeholder="1200"
        />,
      )}
      {inputRow(
        'default_model_opencode',
        <input type="text" value={opencode} onChange={(e) => setOpencode(e.target.value)} placeholder="opencode/…" />,
      )}
      {inputRow(
        'default_model_codex',
        <input type="text" value={codex} onChange={(e) => setCodex(e.target.value)} placeholder="(none)" />,
      )}
      {inputRow(
        'default_model_pi',
        <input type="text" value={pi} onChange={(e) => setPi(e.target.value)} placeholder="(none)" />,
      )}
      <div>
        <button onClick={save}>save</button>
      </div>
    </div>
  );
}

function WebhookForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'webhook';
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [maxRetries, setMaxRetries] = useState<number | ''>('');
  const [timeoutS, setTimeoutS] = useState<number | ''>('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        const v = d.values || {};
        setUrl(typeof v.url === 'string' ? v.url : '');
        setSecret(typeof v.secret_key === 'string' ? v.secret_key : '');
        setMaxRetries(typeof v.max_retries === 'number' ? v.max_retries : '');
        setTimeoutS(typeof v.timeout_seconds === 'number' ? v.timeout_seconds : '');
        setLoaded(true);
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      await patchSection(section, {
        url: url || null,
        secret_key: secret || null,
        max_retries: maxRetries === '' ? null : Number(maxRetries),
        timeout_seconds: timeoutS === '' ? null : Number(timeoutS),
      });
      onToast({ kind: 'ok', msg: 'webhook saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!loaded) return <p className="dim">loading…</p>;
  return (
    <div className="stack" style={{ gap: 8 }}>
      {inputRow('url', <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />)}
      {inputRow(
        'secret_key',
        <input type="password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="signing secret" />,
      )}
      {inputRow(
        'max_retries',
        <input
          type="number"
          value={maxRetries}
          onChange={(e) => setMaxRetries(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
        />,
      )}
      {inputRow(
        'timeout_seconds',
        <input
          type="number"
          value={timeoutS}
          onChange={(e) => setTimeoutS(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
        />,
      )}
      <div>
        <button onClick={save}>save</button>
      </div>
    </div>
  );
}

function TelemetryForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'telemetry';
  const [enabled, setEnabled] = useState(false);
  const [endpoint, setEndpoint] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        const v = d.values || {};
        setEnabled(Boolean(v.enabled));
        setEndpoint(typeof v.endpoint === 'string' ? v.endpoint : '');
        setLoaded(true);
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      await patchSection(section, { enabled, endpoint: endpoint || null });
      onToast({ kind: 'ok', msg: 'telemetry saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!loaded) return <p className="dim">loading…</p>;
  return (
    <div className="stack" style={{ gap: 8 }}>
      {inputRow(
        'enabled',
        <label>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> opt in
        </label>,
      )}
      {inputRow(
        'endpoint',
        <input type="text" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://…" />,
      )}
      <div>
        <button onClick={save}>save</button>
      </div>
    </div>
  );
}

function WorkspaceDefaultsForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'workspace_defaults';
  const [data, setData] = useState<SectionPayload | null>(null);
  const [fields, setFields] = useState<Record<string, unknown>>({});
  const [jsonFallback, setJsonFallback] = useState<string | null>(null);

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        setData(d);
        setFields({ ...(d.values || {}) });
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      let payload: Record<string, unknown>;
      if (jsonFallback !== null) {
        payload = JSON.parse(jsonFallback) as Record<string, unknown>;
        if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
          throw new Error('must be a JSON object');
        }
      } else {
        payload = fields;
      }
      await patchSection(section, payload);
      onToast({ kind: 'ok', msg: 'workspace defaults saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!data) return <p className="dim">loading…</p>;

  const keys = Object.keys(fields);
  const allScalar = keys.every((k) => {
    const v = fields[k];
    return v === null || ['string', 'number', 'boolean'].includes(typeof v);
  });

  if (!allScalar || keys.length === 0) {
    const json = jsonFallback ?? JSON.stringify(data.values || {}, null, 2);
    return (
      <div className="stack" style={{ gap: 8 }}>
        <textarea
          value={json}
          onChange={(e) => setJsonFallback(e.target.value)}
          rows={Math.max(6, keys.length + 2)}
          style={{ fontFamily: 'monospace', fontSize: 13, width: '100%' }}
        />
        <div>
          <button onClick={save}>save</button>
        </div>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      {keys.map((k) => {
        const v = fields[k];
        if (typeof v === 'boolean') {
          return inputRow(
            k,
            <label>
              <input
                type="checkbox"
                checked={v}
                onChange={(e) => setFields((p) => ({ ...p, [k]: e.target.checked }))}
              />
            </label>,
          );
        }
        if (typeof v === 'number') {
          return inputRow(
            k,
            <input
              type="number"
              value={v}
              onChange={(e) =>
                setFields((p) => ({ ...p, [k]: e.target.value === '' ? null : Number(e.target.value) }))
              }
            />,
          );
        }
        return inputRow(
          k,
          <input
            type="text"
            value={(v as string) ?? ''}
            onChange={(e) => setFields((p) => ({ ...p, [k]: e.target.value }))}
          />,
        );
      })}
      <div>
        <button onClick={save}>save</button>
      </div>
    </div>
  );
}

function McpGlobalForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'mcp_global';
  const [data, setData] = useState<SectionPayload | null>(null);
  const [editor, setEditor] = useState('');

  useEffect(() => {
    fetchSection(section)
      .then((d) => {
        setData(d);
        setEditor(JSON.stringify(d.values || {}, null, 2));
      })
      .catch((e) => onToast({ kind: 'error', msg: `load failed: ${e.message}` }));
  }, [onToast]);

  async function save() {
    try {
      const parsed = JSON.parse(editor) as Record<string, unknown>;
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        throw new Error('must be a JSON object');
      }
      await patchSection(section, parsed);
      onToast({ kind: 'ok', msg: 'mcp_global saved' });
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!data) return <p className="dim">loading…</p>;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        For per-workspace MCP overrides, see <a href="/workspaces">/workspaces</a>.
      </p>
      <textarea
        value={editor}
        onChange={(e) => setEditor(e.target.value)}
        rows={Math.max(8, Object.keys(data.values || {}).length + 2)}
        style={{ fontFamily: 'monospace', fontSize: 13, width: '100%' }}
      />
      <div>
        <button onClick={save}>save</button>
      </div>
    </div>
  );
}

function SecretsForm({ onToast }: { onToast: (t: ToastState) => void }) {
  const section = 'secrets';
  const [keys, setKeys] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');
  const [loaded, setLoaded] = useState(false);

  async function reload() {
    try {
      const d = await fetchSection(section);
      setKeys(Object.keys(d.values || {}).sort());
      setLoaded(true);
    } catch (e) {
      onToast({ kind: 'error', msg: `load failed: ${(e as Error).message}` });
    }
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function setKey(key: string, value: string) {
    if (!value) {
      onToast({ kind: 'error', msg: 'value required' });
      return;
    }
    try {
      await patchSection(section, { [key]: value });
      setDrafts((p) => ({ ...p, [key]: '' }));
      onToast({ kind: 'ok', msg: `${key} set` });
      await reload();
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  async function clearKey(key: string) {
    if (!confirm(`clear secret "${key}"?`)) return;
    try {
      await patchSection(section, { [key]: null });
      onToast({ kind: 'ok', msg: `${key} cleared` });
      await reload();
    } catch (e) {
      onToast({ kind: 'error', msg: `clear failed: ${(e as Error).message}` });
    }
  }

  async function addNew() {
    if (!newKey || !newVal) {
      onToast({ kind: 'error', msg: 'key and value required' });
      return;
    }
    try {
      await patchSection(section, { [newKey]: newVal });
      onToast({ kind: 'ok', msg: `${newKey} set` });
      setNewKey('');
      setNewVal('');
      await reload();
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    }
  }

  if (!loaded) return <p className="dim">loading…</p>;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Values are write-only — existing secret values are never displayed. Enter a new value and click Set to
        overwrite.
      </p>
      {keys.length === 0 && <p className="dim">no secrets set</p>}
      {keys.map((k) => (
        <div
          key={k}
          style={{ display: 'grid', gridTemplateColumns: '220px 1fr auto auto', gap: 8, alignItems: 'center' }}
        >
          <code style={{ fontSize: 13 }}>{k}</code>
          <input
            type="password"
            placeholder="new value"
            value={drafts[k] || ''}
            onChange={(e) => setDrafts((p) => ({ ...p, [k]: e.target.value }))}
          />
          <button onClick={() => setKey(k, drafts[k] || '')}>Set</button>
          <button onClick={() => clearKey(k)} className="dim">
            Clear
          </button>
        </div>
      ))}
      <hr style={{ border: 0, borderTop: '1px solid #30363d', margin: '8px 0' }} />
      <div
        style={{ display: 'grid', gridTemplateColumns: '220px 1fr auto', gap: 8, alignItems: 'center' }}
      >
        <input type="text" placeholder="NEW_KEY" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
        <input
          type="password"
          placeholder="value"
          value={newVal}
          onChange={(e) => setNewVal(e.target.value)}
        />
        <button onClick={addNew}>Add</button>
      </div>
    </div>
  );
}

export default function SettingsBaseTab() {
  const [toast, setToast] = useState<ToastState>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack" style={{ gap: 16 }}>
      {SECTIONS.map((s) => (
        <SectionShell key={s.key} section={s.key} label={s.label} hint={s.hint}>
          {s.key === 'webhook' ? (
            <WebhookForm onToast={setToast} />
          ) : s.key === 'telemetry' ? (
            <TelemetryForm onToast={setToast} />
          ) : s.key === 'workspace_defaults' ? (
            <WorkspaceDefaultsForm onToast={setToast} />
          ) : s.key === 'mcp_global' ? (
            <McpGlobalForm onToast={setToast} />
          ) : (
            <SecretsForm onToast={setToast} />
          )}
        </SectionShell>
      ))}
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
