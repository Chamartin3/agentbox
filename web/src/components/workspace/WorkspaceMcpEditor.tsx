import { Fragment, useEffect, useState } from 'react';
import {
  workspaceMcpApi,
  projectMcpApi,
  EffectiveMcp,
  McpPolicy,
  McpServerView,
  ProjectMcpServer,
} from '../../api/repo';
import Modal from '../common/Modal';

interface Props {
  workspaceId: string;
}

export default function WorkspaceMcpEditor({ workspaceId }: Props) {
  const [data, setData] = useState<EffectiveMcp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: '', kind: 'url' as 'url' | 'command', value: '' });
  const [linking, setLinking] = useState(false);
  const [globals, setGlobals] = useState<ProjectMcpServer[]>([]);

  const addServer = async () => {
    const name = form.name.trim();
    const value = form.value.trim();
    if (!name || !value) { alert('Name and endpoint/command are required.'); return; }
    if (data?.servers.some((s) => s.name === name)) { alert(`Server "${name}" already exists.`); return; }
    const config = form.kind === 'url'
      ? { url: value, transport: 'http' }
      : { command: value.split(/\s+/) };
    setBusy(true);
    try {
      await workspaceMcpApi.setServer(workspaceId, name, true, 'added via workspace UI', config);
      setAdding(false);
      setForm({ name: '', kind: 'url', value: '' });
      // Install-time validation: connect to the server and discover its tools
      // so the catalog is populated and we can confirm it actually works.
      let discovered = 0;
      try {
        discovered = (await workspaceMcpApi.refresh(workspaceId)).invalidated;
      } catch (e) {
        alert(`Server "${name}" added, but tool discovery failed: ${String(e)}`);
      }
      await load();
      if (discovered === 0) {
        alert(`Server "${name}" added, but no tools were discovered — check the command/URL is correct and the server starts.`);
      }
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      setData(await workspaceMcpApi.get(workspaceId));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [workspaceId]);

  const setPolicy = async (policy: McpPolicy) => {
    if (!data || policy === data.policy) return;
    setBusy(true);
    try {
      await workspaceMcpApi.setPolicy(workspaceId, policy);
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  // Inherited (global) servers: exclude = hard-exclude from this workspace
  // (stays out under any policy); include = allow again. Global list untouched.
  const setEnabled = async (srv: McpServerView, enabled: boolean) => {
    setBusy(true);
    try {
      await workspaceMcpApi.setServer(
        workspaceId,
        srv.name,
        enabled,
        enabled ? 'included in workspace' : 'excluded from workspace',
      );
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  // Local (workspace-only) servers: delete the override outright.
  const removeServer = async (srv: McpServerView) => {
    if (!confirm(`Remove MCP server "${srv.name}" from this workspace?`)) return;
    setBusy(true);
    try {
      await workspaceMcpApi.removeServer(workspaceId, srv.name);
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  // Link a global (project-level) server into this workspace: for an
  // inherited server that was excluded, this re-includes it. New workspaces
  // already inherit every global by default (allow_all policy), so this is
  // the "put it back" / opt-in-under-deny-all path.
  const openLink = async () => {
    try {
      setGlobals((await projectMcpApi.list()).servers);
      setLinking(true);
    } catch (e) {
      alert(`Could not load global servers: ${String(e)}`);
    }
  };

  const linkServer = async (name: string) => {
    setBusy(true);
    try {
      await workspaceMcpApi.setServer(workspaceId, name, true, 'linked global server');
      setLinking(false);
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    setBusy(true);
    try {
      const { invalidated } = await workspaceMcpApi.refresh(workspaceId);
      await load();
      alert(`Discovered ${invalidated} tool${invalidated === 1 ? '' : 's'}.`);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="dim" style={{ fontSize: 12 }}>loading MCP server configuration…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;
  if (!data) return null;

  // Active = local (workspace-only) servers + inherited globals that are
  // included. Excluded globals drop out of the table; "+ link global" re-adds.
  const activeServers = data.servers.filter((s) => s.source === 'override_only' || s.enabled);
  const activeNames = new Set(activeServers.map((s) => s.name));
  const linkable = globals.filter((g) => !activeNames.has(g.name));

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row between">
        <div>
          <strong style={{ fontSize: 12 }}>Default policy:</strong>{' '}
          <label className="row" style={{ gap: 4, display: 'inline-flex', marginRight: 12 }}>
            <input
              type="radio"
              checked={data.policy === 'allow_all_unless_disabled'}
              disabled={busy}
              onChange={() => setPolicy('allow_all_unless_disabled')}
            />
            <span style={{ fontSize: 12 }}>show all servers</span>
          </label>
          <label className="row" style={{ gap: 4, display: 'inline-flex' }}>
            <input
              type="radio"
              checked={data.policy === 'deny_all_unless_enabled'}
              disabled={busy}
              onChange={() => setPolicy('deny_all_unless_enabled')}
            />
            <span style={{ fontSize: 12 }}>hide all servers unless shown</span>
          </label>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button onClick={openLink} disabled={busy} style={{ fontSize: 11 }}>
            + link global
          </button>
          <button onClick={() => setAdding(true)} disabled={busy} style={{ fontSize: 11 }}>
            + add server
          </button>
          <button onClick={refresh} disabled={busy} style={{ fontSize: 11 }}>
            refresh discovery
          </button>
        </div>
      </div>

      {activeServers.length === 0 ? (
        <p className="dim" style={{ fontSize: 12 }}>
          No servers in this workspace. Use “+ link global” to add one.
        </p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Server</th>
              <th style={{ textAlign: 'left' }}>Source</th>
              <th style={{ textAlign: 'left' }}>Tools</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {activeServers.map((s) => {
              const isLocal = s.source === 'override_only';
              const tools = s.tools ?? [];
              return (
                <Fragment key={s.name}>
                  <tr>
                    <td><code>{s.name}</code></td>
                    <td>
                      <span
                        className="pill"
                        style={{ fontSize: 10 }}
                        title={isLocal ? 'added to this workspace' : 'from the global MCP list'}
                      >
                        {isLocal ? 'local' : 'inherited'}
                      </span>
                    </td>
                    <td>
                      {tools.length > 0 ? (
                        <button
                          onClick={() => setExpanded(expanded === s.name ? null : s.name)}
                          style={{ fontSize: 11 }}
                        >
                          {expanded === s.name ? 'hide' : `${tools.length}`}
                        </button>
                      ) : (
                        <span className="dim" title="run 'refresh discovery' to list tools">—</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        onClick={() => (isLocal ? removeServer(s) : setEnabled(s, false))}
                        disabled={busy}
                        title={isLocal ? 'remove from workspace' : 'exclude from workspace'}
                        style={{ fontSize: 13, color: 'crimson', lineHeight: 1 }}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                  {expanded === s.name && tools.length > 0 && (
                    <tr key={`${s.name}-tools`}>
                      <td colSpan={4} style={{ paddingLeft: 24, background: '#161b22' }}>
                        <div className="row" style={{ gap: 6, flexWrap: 'wrap', padding: 8 }}>
                          {tools.map((t) => (
                            <span key={t} className="pill" style={{ fontSize: 11 }}>{t}</span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      {linking && (
        <Modal title="Link a global MCP server" onClose={() => setLinking(false)}>
          {linkable.length === 0 ? (
            <p className="dim" style={{ fontSize: 12 }}>
              All global servers are already in this workspace.
            </p>
          ) : (
            <div className="stack" style={{ gap: 6 }}>
              {linkable.map((g) => (
                <div key={g.name} className="row between" style={{ gap: 8, alignItems: 'center' }}>
                  <div>
                    <code style={{ fontSize: 12 }}>{g.name}</code>{' '}
                    <span className="dim" style={{ fontSize: 11 }}>{g.url || g.command}</span>
                  </div>
                  <button
                    className="primary"
                    onClick={() => linkServer(g.name)}
                    disabled={busy}
                    style={{ fontSize: 11 }}
                  >
                    link
                  </button>
                </div>
              ))}
            </div>
          )}
        </Modal>
      )}

      {adding && (
        <Modal
          title="Add MCP server"
          onClose={() => setAdding(false)}
          footer={
            <button className="primary" onClick={addServer} disabled={busy}>
              {busy ? 'adding…' : 'add server'}
            </button>
          }
        >
          <div className="stack" style={{ gap: 10 }}>
            <label className="stack" style={{ gap: 4 }}>
              <span className="dim" style={{ fontSize: 12 }}>Name</span>
              <input
                autoFocus
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="my-mcp"
              />
            </label>
            <div className="row" style={{ gap: 12 }}>
              <label className="row" style={{ gap: 4 }}>
                <input
                  type="radio"
                  checked={form.kind === 'url'}
                  onChange={() => setForm({ ...form, kind: 'url' })}
                />
                <span style={{ fontSize: 12 }}>Remote (URL)</span>
              </label>
              <label className="row" style={{ gap: 4 }}>
                <input
                  type="radio"
                  checked={form.kind === 'command'}
                  onChange={() => setForm({ ...form, kind: 'command' })}
                />
                <span style={{ fontSize: 12 }}>Local (command)</span>
              </label>
            </div>
            <label className="stack" style={{ gap: 4 }}>
              <span className="dim" style={{ fontSize: 12 }}>
                {form.kind === 'url' ? 'Endpoint URL' : 'Command'}
              </span>
              <input
                value={form.value}
                onChange={(e) => setForm({ ...form, value: e.target.value })}
                placeholder={form.kind === 'url' ? 'https://host/mcp' : 'npx my-mcp-server --flag'}
              />
            </label>
          </div>
        </Modal>
      )}
    </div>
  );
}
