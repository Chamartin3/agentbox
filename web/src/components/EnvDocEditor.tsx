import { useEffect, useState } from 'react';

interface EnvDocResponse {
  workspace_id: string;
  content: string;
  path?: string;
  size?: number;
}

interface Props {
  workspaceId: string;
}

export default function EnvDocEditor({ workspaceId }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc`, {
      headers: { 'Content-Type': 'application/json' },
    })
      .then(async (resp) => {
        if (resp.status === 404) return null;
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return (await resp.json()) as EnvDocResponse;
      })
      .then((data) => {
        if (data) {
          setContent(data.content);
          setPath(data.path ?? null);
        } else {
          setContent(null);
        }
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  if (loading) return <p className="dim">loading env-doc…</p>;
  if (error) return <p style={{ color: 'var(--error)', fontSize: 12 }}>{error}</p>;

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>
          Env Doc{' '}
          <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
            · active environment documentation for this workspace
          </span>
        </h3>
        {path && (
          <span className="dim" style={{ fontSize: 11 }}>{path}</span>
        )}
      </div>
      {content == null || content === '' ? (
        <p className="dim">No env-doc found for this workspace.</p>
      ) : (
        <div className="code-block">
          <div className="code-block-bar">
            <span className="dim" style={{ fontSize: 11 }}>env-doc</span>
          </div>
          <pre style={{ maxHeight: 400, overflow: 'auto', fontSize: 12, padding: '12px 14px', margin: 0 }}>
            {content}
          </pre>
        </div>
      )}
    </section>
  );
}
