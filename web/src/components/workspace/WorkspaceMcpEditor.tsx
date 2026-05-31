import { useEffect, useState } from 'react';
import { workspaceMcpApi, EffectiveMcp, McpPolicy, McpServerView } from '../../api/repo';

interface Props {
  workspaceId: string;
}

export default function WorkspaceMcpEditor({ workspaceId }: Props) {
  const [data, setData] = useState<EffectiveMcp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

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

  const toggleServer = async (srv: McpServerView) => {
    const reason = window.prompt(
      `${srv.enabled ? 'Disable' : 'Enable'} MCP server "${srv.name}" — reason:`,
      srv.enabled ? 'disabling for this workspace' : 'enabling for this workspace',
    );
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    try {
      await workspaceMcpApi.setServer(workspaceId, srv.name, !srv.enabled, reason.trim());
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const toggleTool = async (srv: McpServerView, tool: string, currentlyDisabled: boolean) => {
    setBusy(true);
    try {
      await workspaceMcpApi.setTool(workspaceId, srv.name, tool, currentlyDisabled);
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
      alert(`Invalidated ${invalidated} cache entries.`);
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="dim" style={{ fontSize: 12 }}>loading MCP overrides…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;
  if (!data) return null;

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
            <span style={{ fontSize: 12 }}>allow all unless disabled</span>
          </label>
          <label className="row" style={{ gap: 4, display: 'inline-flex' }}>
            <input
              type="radio"
              checked={data.policy === 'deny_all_unless_enabled'}
              disabled={busy}
              onChange={() => setPolicy('deny_all_unless_enabled')}
            />
            <span style={{ fontSize: 12 }}>deny all unless enabled</span>
          </label>
        </div>
        <button onClick={refresh} disabled={busy} style={{ fontSize: 11 }}>
          refresh discovery
        </button>
      </div>

      {data.servers.length === 0 ? (
        <p className="dim" style={{ fontSize: 12 }}>No MCP servers declared in manifest.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left' }}>Server</th>
              <th style={{ textAlign: 'left' }}>Enabled</th>
              <th style={{ textAlign: 'left' }}>Source</th>
              <th style={{ textAlign: 'left' }}>Disabled tools</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.servers.map((s) => {
              const tools = (s.config?.tools as string[] | undefined) ?? [];
              return (
                <>
                  <tr key={s.name}>
                    <td><code>{s.name}</code></td>
                    <td>
                      <button
                        onClick={() => toggleServer(s)}
                        disabled={busy}
                        className={s.enabled ? 'primary' : ''}
                        style={{ fontSize: 11, minWidth: 60 }}
                      >
                        {s.enabled ? 'on' : 'off'}
                      </button>
                    </td>
                    <td><span className="dim">{s.source}</span></td>
                    <td>
                      {s.disabled_tools.length === 0 ? (
                        <span className="dim">—</span>
                      ) : (
                        <code style={{ fontSize: 11 }}>{s.disabled_tools.join(', ')}</code>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {tools.length > 0 && (
                        <button
                          onClick={() => setExpanded(expanded === s.name ? null : s.name)}
                          style={{ fontSize: 11 }}
                        >
                          {expanded === s.name ? 'hide tools' : `tools (${tools.length})`}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded === s.name && tools.length > 0 && (
                    <tr key={`${s.name}-tools`}>
                      <td colSpan={5} style={{ paddingLeft: 24, background: '#161b22' }}>
                        <div className="row" style={{ gap: 6, flexWrap: 'wrap', padding: 8 }}>
                          {tools.map((t) => {
                            const disabled = s.disabled_tools.includes(t);
                            return (
                              <button
                                key={t}
                                onClick={() => toggleTool(s, t, disabled)}
                                disabled={busy}
                                className={disabled ? '' : 'primary'}
                                style={{ fontSize: 11 }}
                                title={disabled ? 'disabled — click to enable' : 'enabled — click to disable'}
                              >
                                {t}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
