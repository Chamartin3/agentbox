import { useEffect, useState } from 'react';
import { apiRequestOrNull } from '../api/http';

interface HostEnvGrant {
  name: string;
  value?: string;
  source?: string;
  masked?: boolean;
}

interface HostEnvResponse {
  workspace_id: string;
  grants: HostEnvGrant[];
}

interface Props {
  workspaceId: string;
}

export default function HostEnvTab({ workspaceId }: Props) {
  const [grants, setGrants] = useState<HostEnvGrant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    apiRequestOrNull<HostEnvResponse>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/host-env`,
    )
      .then((data) => setGrants(data?.grants ?? []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  if (loading) return <p className="dim">loading host-env grants…</p>;
  if (error) return <p style={{ color: 'var(--error)', fontSize: 12 }}>{error}</p>;

  return (
    <section className="section">
      <h3 style={{ marginTop: 0 }}>
        Host Environment Grants{' '}
        <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
          · resolved env vars passed through to agent processes
        </span>
      </h3>
      {grants.length === 0 ? (
        <p className="dim">No host-env grants configured for this workspace.</p>
      ) : (
        <table style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Value</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {grants.map((g) => (
              <tr key={g.name}>
                <td className="mono">{g.name}</td>
                <td className="mono dim">
                  {g.masked
                    ? <span className="dim">••••••</span>
                    : (g.value ?? <span className="dim">—</span>)}
                </td>
                <td className="dim">{g.source ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
