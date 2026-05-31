import { useEffect, useState } from 'react';
import { apiRequestOrNull } from '../api/http';

interface McpServerOverride {
  name: string;
  url?: string;
  command?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

interface McpPolicy {
  allow_all?: boolean;
  allowed_servers?: string[];
  denied_servers?: string[];
}

interface McpPolicyResponse {
  workspace_id: string;
  policy: McpPolicy;
}

interface McpServersResponse {
  workspace_id: string;
  servers: McpServerOverride[];
}

interface Props {
  workspaceId: string;
}

export default function WorkspaceMcpTab({ workspaceId }: Props) {
  const [policy, setPolicy] = useState<McpPolicy | null>(null);
  const [servers, setServers] = useState<McpServerOverride[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);

    const wid = encodeURIComponent(workspaceId);
    const policyReq = apiRequestOrNull<McpPolicyResponse>(
      `/api/workspaces/${wid}/mcp/policy`,
    );
    const serversReq = apiRequestOrNull<McpServersResponse>(
      `/api/workspaces/${wid}/mcp/servers`,
    );

    Promise.all([policyReq, serversReq])
      .then(([policyData, serversData]) => {
        setPolicy(policyData?.policy ?? null);
        setServers(serversData?.servers ?? []);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  if (loading) return <p className="dim">loading MCP config…</p>;
  if (error) return <p style={{ color: 'var(--error)', fontSize: 12 }}>{error}</p>;

  return (
    <div className="stack">
      <section className="section">
        <h3 style={{ marginTop: 0 }}>
          MCP Policy{' '}
          <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
            · server access control for this workspace
          </span>
        </h3>
        {policy == null ? (
          <p className="dim">No MCP policy configured.</p>
        ) : (
          <dl style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: '6px 12px', fontSize: 13 }}>
            <dt className="dim">Allow all</dt>
            <dd>{policy.allow_all ? 'yes' : 'no'}</dd>
            {(policy.allowed_servers ?? []).length > 0 && (
              <>
                <dt className="dim">Allowed servers</dt>
                <dd style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {policy.allowed_servers!.map((s) => (
                    <span key={s} className="tag">{s}</span>
                  ))}
                </dd>
              </>
            )}
            {(policy.denied_servers ?? []).length > 0 && (
              <>
                <dt className="dim">Denied servers</dt>
                <dd style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {policy.denied_servers!.map((s) => (
                    <span key={s} className="tag" style={{ background: 'var(--bg-error)', color: 'var(--error)' }}>{s}</span>
                  ))}
                </dd>
              </>
            )}
          </dl>
        )}
      </section>

      <section className="section">
        <h3 style={{ marginTop: 0 }}>
          MCP Server Overrides{' '}
          <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
            · workspace-specific server configuration
          </span>
        </h3>
        {servers.length === 0 ? (
          <p className="dim">No server overrides defined.</p>
        ) : (
          <table style={{ fontSize: 12 }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>URL / Command</th>
                <th>Status</th>
                <th>Env vars</th>
              </tr>
            </thead>
            <tbody>
              {servers.map((s) => (
                <tr key={s.name}>
                  <td className="mono">{s.name}</td>
                  <td className="dim mono">
                    {s.url || (s.command ? s.command.join(' ') : '—')}
                  </td>
                  <td>
                    {s.enabled === false ? (
                      <span className="pill" style={{ background: 'var(--bg-muted)' }}>disabled</span>
                    ) : (
                      <span className="pill ok">enabled</span>
                    )}
                  </td>
                  <td className="dim">
                    {s.env ? Object.keys(s.env).join(', ') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
