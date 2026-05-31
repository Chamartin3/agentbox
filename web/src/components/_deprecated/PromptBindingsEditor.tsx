import { useEffect, useState } from 'react';
import { apiRequestOrNull } from '../api/http';

export interface PromptBinding {
  marker: string;
  resource_id: string;
  resource_version?: number | null;
  kind?: string;
  name?: string;
}

interface PromptBindingsResponse {
  agent_id: string;
  bindings: PromptBinding[];
}

interface Props {
  agentId: string;
}

export default function PromptBindingsEditor({ agentId }: Props) {
  const [bindings, setBindings] = useState<PromptBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) return;
    setLoading(true);
    setError(null);
    apiRequestOrNull<PromptBindingsResponse>(
      `/api/agents/${encodeURIComponent(agentId)}/prompt-bindings`,
    )
      .then((data) => setBindings(data?.bindings || []))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [agentId]);

  if (loading) return <p className="dim">loading prompt bindings…</p>;
  if (error) return <p style={{ color: 'var(--error)', fontSize: 12 }}>{error}</p>;

  return (
    <section className="section">
      <h2>
        Prompt Bindings{' '}
        <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
          · marker → shared resource mappings
        </span>
      </h2>
      {bindings.length === 0 ? (
        <p className="dim">No prompt bindings configured for this agent.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Marker</th>
              <th>Resource ID</th>
              <th>Version</th>
              <th>Kind</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            {bindings.map((b) => (
              <tr key={b.marker}>
                <td className="mono" style={{ fontSize: 12 }}>{b.marker}</td>
                <td className="mono" style={{ fontSize: 12 }}>{b.resource_id}</td>
                <td>
                  {b.resource_version != null ? (
                    <span className="pill">v{b.resource_version}</span>
                  ) : (
                    <span className="dim">latest</span>
                  )}
                </td>
                <td>{b.kind ? <span className="tag">{b.kind}</span> : <span className="dim">—</span>}</td>
                <td className="dim">{b.name || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
