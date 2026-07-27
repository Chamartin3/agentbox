import { useEffect, useState } from 'react';
import { projectMcpApi, ProjectMcpServer, McpIntrospection } from '../../api/repo';
import { ApiError } from '../../api/http';
import Modal from '../common/Modal';

// FastAPI errors come back as {detail: "..."}; pull the string out for a toast.
function errMsg(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail;
    if (d && typeof d === 'object' && 'detail' in d) return String((d as { detail: unknown }).detail);
    return typeof d === 'string' ? d : e.message;
  }
  return (e as Error).message;
}

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
  const [toolFilter, setToolFilter] = useState('');

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

  const introspect = async (name: string, refresh = false) => {
    setInspectBusy(true);
    try {
      const res = await projectMcpApi.introspect(name, refresh);
      setInfo((p) => ({ ...p, [name]: res }));
      if (res.error) onToast({ kind: 'error', msg: `${name}: ${res.error}` });
      // A live refresh rewrites the server-side cache; reload so the table
      // counts reflect it without reopening each modal.
      else if (refresh) void load();
    } catch (e) {
      const msg = (e as Error).message;
      // Keep the modal useful: surface the failure inside it, not just a toast.
      setInfo((p) => ({ ...p, [name]: { server: name, tools: [], resources: [], error: msg } }));
      onToast({ kind: 'error', msg: `introspect failed: ${msg}` });
    } finally {
      setInspectBusy(false);
    }
  };

  const openInspect = async (name: string) => {
    setInspecting(name);
    setToolFilter('');
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
      // The server is probed before it is saved; a broken/uninstalled command
      // is rejected here (422) and the modal stays open so it can be fixed.
      const saved = await projectMcpApi.upsert(name, spec);
      setAdding(false);
      setForm({ name: '', kind: 'command', value: '' });
      onToast({ kind: 'ok', msg: `${name} added — ${saved.tool_count ?? 0} tools` });
      await load();
    } catch (e) {
      onToast({ kind: 'error', msg: `could not add ${name}: ${errMsg(e)}` });
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
              // Prefer this-session introspection; else the counts the list
              // endpoint returns from the persisted cache; else nothing yet.
              const seen = info[s.name];
              const toolN = seen ? seen.tools.length : s.tool_count;
              const resN = seen ? seen.resources.length : s.resource_count;
              const label =
                toolN != null ? `${toolN} tools · ${resN ?? 0} resources` : 'inspect';
              return (
                <tr key={s.name}>
                  <td><code>{s.name}</code></td>
                  <td><code style={{ fontSize: 11 }}>{s.url || (s.command || []).join(' ')}</code></td>
                  <td>
                    <button onClick={() => openInspect(s.name)} disabled={busy} style={{ fontSize: 11 }}>
                      {label}
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
          wide
          title={`${inspecting} — tools & resources`}
          onClose={() => setInspecting(null)}
          footer={
            <button onClick={() => introspect(inspecting, true)} disabled={inspectBusy}>
              {inspectBusy ? 'refreshing…' : '↻ refresh'}
            </button>
          }
        >
          {inspectBusy && !current ? (
            <p className="dim">connecting…</p>
          ) : current?.error ? (
            <p style={{ color: 'crimson', fontSize: 12 }}>{current.error}</p>
          ) : current ? (
            (() => {
              const q = toolFilter.trim().toLowerCase();
              const tools = q
                ? current.tools.filter(
                    (t) =>
                      t.name.toLowerCase().includes(q) ||
                      (t.description ?? '').toLowerCase().includes(q),
                  )
                : current.tools;
              return (
                <div className="stack" style={{ gap: 12 }}>
                  {current.tools.length > 8 && (
                    <input
                      autoFocus
                      placeholder={`Filter ${current.tools.length} tools…`}
                      value={toolFilter}
                      onChange={(e) => setToolFilter(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  )}
                  <div className="stack" style={{ gap: 0 }}>
                    <strong style={{ fontSize: 12, marginBottom: 4 }}>
                      Tools ({q ? `${tools.length}/${current.tools.length}` : current.tools.length})
                    </strong>
                    {current.tools.length === 0 ? (
                      <span className="dim" style={{ fontSize: 12 }}>none</span>
                    ) : tools.length === 0 ? (
                      <span className="dim" style={{ fontSize: 12 }}>no match for “{toolFilter}”</span>
                    ) : (
                      tools.map((t) => (
                        <div
                          key={t.name}
                          style={{ padding: '6px 0', borderTop: '1px solid var(--border)' }}
                        >
                          <code style={{ fontSize: 12 }}>{t.name}</code>
                          {t.description && (
                            <div
                              className="dim"
                              title={t.description}
                              style={{
                                fontSize: 12,
                                marginTop: 2,
                                whiteSpace: 'pre-wrap',
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                              }}
                            >
                              {t.description}
                            </div>
                          )}
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
                          {r.description && <span className="dim" title={r.description}> — {r.description}</span>}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              );
            })()
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
