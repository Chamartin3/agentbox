import { useEffect, useState } from 'react';
import { projectMcpApi, ProjectMcpServer, McpIntrospection } from '../../api/repo';
import Modal from '../common/Modal';

// Global (project-level) MCP servers shared by all workspaces. Table + add/remove,
// plus on-demand introspection (tools + resources) in a modal.
export default function ProjectMcpEditor({ onToast }: { onToast: (t: { kind: 'ok' | 'error'; msg: string }) => void }) {
  const [servers, setServers] = useState<ProjectMcpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: '', kind: 'command' as 'url' | 'command', value: '' });
  // Cached introspection per server (populated when the modal is opened/refreshed).
  const [info, setInfo] = useState<Record<string, McpIntrospection>>({});
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [inspectBusy, setInspectBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      setServers((await projectMcpApi.list()).servers);
    } catch (e) {
      onToast({ kind: 'error', msg: `load failed: ${(e as Error).message}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const introspect = async (name: string) => {
    setInspectBusy(true);
    try {
      const res = await projectMcpApi.introspect(name);
      setInfo((p) => ({ ...p, [name]: res }));
      if (res.error) onToast({ kind: 'error', msg: `${name}: ${res.error}` });
    } catch (e) {
      onToast({ kind: 'error', msg: `introspect failed: ${(e as Error).message}` });
    } finally {
      setInspectBusy(false);
    }
  };

  const openInspect = async (name: string) => {
    setInspecting(name);
    if (!info[name]) await introspect(name);
  };

  const add = async () => {
    const name = form.name.trim();
    const value = form.value.trim();
    if (!name || !value) { onToast({ kind: 'error', msg: 'name and endpoint/command are required' }); return; }
    if (servers.some((s) => s.name === name)) { onToast({ kind: 'error', msg: `"${name}" already exists` }); return; }
    const spec: Partial<ProjectMcpServer> = form.kind === 'url'
      ? { url: value, transport: 'http', command: null }
      : { command: value.split(/\s+/), transport: 'stdio', url: null };
    setBusy(true);
    try {
      await projectMcpApi.upsert(name, spec);
      setAdding(false);
      setForm({ name: '', kind: 'command', value: '' });
      onToast({ kind: 'ok', msg: `${name} added` });
      await load();
    } catch (e) {
      onToast({ kind: 'error', msg: `save failed: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (name: string) => {
    if (!confirm(`Remove global MCP server "${name}"?`)) return;
    setBusy(true);
    try {
      await projectMcpApi.remove(name);
      onToast({ kind: 'ok', msg: `${name} removed` });
      await load();
    } catch (e) {
      onToast({ kind: 'error', msg: `delete failed: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="dim">loading…</p>;

  const current = inspecting ? info[inspecting] : undefined;

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row between">
        <p className="dim" style={{ fontSize: 12, margin: 0 }}>
          Shared by all workspaces. Per-workspace show/hide lives on each <a href="/workspaces">workspace</a>.
        </p>
        <button onClick={() => setAdding(true)} disabled={busy} style={{ fontSize: 11 }}>+ add server</button>
      </div>

      {servers.length === 0 ? (
        <p className="dim">No global MCP servers.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Server</th>
              <th style={{ textAlign: 'left' }}>Endpoint / command</th>
              <th style={{ textAlign: 'left' }}>Tools / resources</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {servers.map((s) => {
              const seen = info[s.name];
              return (
                <tr key={s.name}>
                  <td><code>{s.name}</code></td>
                  <td><code style={{ fontSize: 11 }}>{s.url || (s.command || []).join(' ')}</code></td>
                  <td>
                    <button onClick={() => openInspect(s.name)} disabled={busy} style={{ fontSize: 11 }}>
                      {seen ? `${seen.tools.length} tools · ${seen.resources.length} resources` : 'inspect'}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button onClick={() => remove(s.name)} disabled={busy} style={{ color: 'crimson', fontSize: 11 }}>remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {inspecting && (
        <Modal
          title={`${inspecting} — tools & resources`}
          onClose={() => setInspecting(null)}
          footer={
            <button onClick={() => introspect(inspecting)} disabled={inspectBusy}>
              {inspectBusy ? 'refreshing…' : '↻ refresh'}
            </button>
          }
        >
          {inspectBusy && !current ? (
            <p className="dim">connecting…</p>
          ) : current?.error ? (
            <p style={{ color: 'crimson', fontSize: 12 }}>{current.error}</p>
          ) : current ? (
            <div className="stack" style={{ gap: 12 }}>
              <div className="stack" style={{ gap: 4 }}>
                <strong style={{ fontSize: 12 }}>Tools ({current.tools.length})</strong>
                {current.tools.length === 0 ? (
                  <span className="dim" style={{ fontSize: 12 }}>none</span>
                ) : (
                  current.tools.map((t) => (
                    <div key={t.name} style={{ fontSize: 12 }}>
                      <code>{t.name}</code>
                      {t.description && <span className="dim"> — {t.description}</span>}
                    </div>
                  ))
                )}
              </div>
              <div className="stack" style={{ gap: 4 }}>
                <strong style={{ fontSize: 12 }}>Resources ({current.resources.length})</strong>
                {current.resources.length === 0 ? (
                  <span className="dim" style={{ fontSize: 12 }}>none</span>
                ) : (
                  current.resources.map((r) => (
                    <div key={r.uri} style={{ fontSize: 12 }}>
                      <code>{r.name || r.uri}</code>
                      {r.description && <span className="dim"> — {r.description}</span>}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}
        </Modal>
      )}

      {adding && (
        <Modal
          title="Add MCP server"
          onClose={() => setAdding(false)}
          footer={<button className="primary" onClick={add} disabled={busy}>{busy ? 'adding…' : 'add server'}</button>}
        >
          <div className="stack" style={{ gap: 10 }}>
            <label className="stack" style={{ gap: 4 }}>
              <span className="dim" style={{ fontSize: 12 }}>Name</span>
              <input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="my-mcp" />
            </label>
            <div className="row" style={{ gap: 12 }}>
              <label className="row" style={{ gap: 4 }}>
                <input type="radio" checked={form.kind === 'command'} onChange={() => setForm({ ...form, kind: 'command' })} />
                <span style={{ fontSize: 12 }}>Local (command)</span>
              </label>
              <label className="row" style={{ gap: 4 }}>
                <input type="radio" checked={form.kind === 'url'} onChange={() => setForm({ ...form, kind: 'url' })} />
                <span style={{ fontSize: 12 }}>Remote (URL)</span>
              </label>
            </div>
            <label className="stack" style={{ gap: 4 }}>
              <span className="dim" style={{ fontSize: 12 }}>{form.kind === 'url' ? 'Endpoint URL' : 'Command'}</span>
              <input
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                placeholder={form.kind === 'url' ? 'https://host/mcp' : 'npx -y my-mcp-server'}
              />
            </label>
          </div>
        </Modal>
      )}
    </div>
  );
}
