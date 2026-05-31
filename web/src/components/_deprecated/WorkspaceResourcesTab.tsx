import { useEffect, useState } from 'react';
import { apiRequestOrNull } from '../api/http';

export interface WorkspaceFileBinding {
  path: string;
  resource_id: string;
  resource_version?: number | null;
  kind?: string;
  sha256?: string;
}

interface WorkspaceResourcesResponse {
  workspace_id: string;
  bindings: WorkspaceFileBinding[];
}

interface Props {
  workspaceId: string;
}

export default function WorkspaceResourcesTab({ workspaceId }: Props) {
  const [bindings, setBindings] = useState<WorkspaceFileBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    apiRequestOrNull<WorkspaceResourcesResponse>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/resources`,
    )
      .then((data) => setBindings(data?.bindings || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  if (loading) return <p className="dim">loading workspace resources…</p>;
  if (error) return <p style={{ color: 'var(--error)', fontSize: 12 }}>{error}</p>;

  return (
    <section className="section">
      <h3 style={{ marginTop: 0 }}>
        Workspace File Bindings{' '}
        <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
          · resource files materialized into the workspace
        </span>
      </h3>
      {bindings.length === 0 ? (
        <p className="dim">No resource file bindings for this workspace.</p>
      ) : (
        <table style={{ fontSize: 12 }}>
          <thead>
            <tr>
              <th>Path</th>
              <th>Resource ID</th>
              <th>Version</th>
              <th>Kind</th>
              <th>SHA</th>
            </tr>
          </thead>
          <tbody>
            {bindings.map((b) => (
              <tr key={b.path}>
                <td className="mono">{b.path}</td>
                <td className="mono">{b.resource_id}</td>
                <td>
                  {b.resource_version != null ? (
                    <span className="pill">v{b.resource_version}</span>
                  ) : (
                    <span className="dim">latest</span>
                  )}
                </td>
                <td>{b.kind ? <span className="tag">{b.kind}</span> : <span className="dim">—</span>}</td>
                <td className="dim mono" style={{ fontSize: 11 }}>
                  {b.sha256 ? b.sha256.slice(0, 12) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
