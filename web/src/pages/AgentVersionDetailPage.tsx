import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { versionsApi, VersionDetail, Comment } from '../api/versions';
import AgentVersionDiff from './AgentVersionDiff';
import RunRatingStars from '../components/runs/RunRatingStars';

interface RunRecord {
  id: string;
  status: string;
  input: string;
  output?: string;
  created_at: string;
  finished_at?: string;
  rating?: number | null;
  comments_count?: number;
}

export default function AgentVersionDetailPage() {
  const { id: agentId, vid } = useParams<{ id: string; vid: string }>();
  const navigate = useNavigate();

  const [version, setVersion] = useState<VersionDetail | null>(null);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    if (!agentId || !vid) return;
    loadData();
  }, [agentId, vid]);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [v] = await Promise.all([
        versionsApi.getVersion(agentId!, vid!),
      ]);
      setVersion(v);
      setRuns([]);
      setComments(v.comments || []);
    } catch (err) {
      setError('Failed to load version details');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRollback = async () => {
    if (!version || !agentId) return;
    if (!confirm(`Rollback to v${version.version}?`)) return;
    try {
      await versionsApi.rollback(agentId, String(version.id));
      navigate(`/agents/${agentId}/versions`);
    } catch {
      alert('Failed to rollback');
    }
  };

  if (isLoading) return <div className="page-loading">Loading version details...</div>;
  if (error || !version) return <div className="page-error">{error ?? 'Version not found'}</div>;

  return (
    <div className="version-detail-page" style={{ maxWidth: 1100, margin: '0 auto', padding: '1.5rem' }}>
      <nav className="breadcrumb" style={{ marginBottom: '1rem', fontSize: '0.9rem', color: '#666' }}>
        <Link to="/agents">Agents</Link>
        {' / '}
        <Link to={`/agents/${agentId}`}>{agentId}</Link>
        {' / '}
        <Link to={`/agents/${agentId}/versions`}>Versions</Link>
        {' / '}
        v{version.version}
      </nav>

      <div className="version-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: 0 }}>v{version.version}</h2>
          <p style={{ color: '#666', margin: '0.25rem 0 0' }}>
            {version.author} · {new Date(version.created_at).toLocaleString()}
          </p>
          {version.changelog && (
            <p style={{ marginTop: '0.5rem', fontStyle: 'italic' }}>{version.changelog}</p>
          )}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={handleRollback} className="btn-secondary">
            🏆 Promote to active
          </button>
          <button
            onClick={() => navigate(`/agents/${agentId}/versions/diff?from=${Math.max(1, version.version - 1)}&to=${version.version}`)}
            className="btn-secondary"
          >
            Diff vs prev
          </button>
        </div>
      </div>

      <section style={{ marginBottom: '2rem' }}>
        <h3>Diff vs Previous</h3>
        {version.version > 1 ? (
          <AgentVersionDiff
            agentId={agentId}
            selectedVersion={version.version}
          />
        ) : (
          <p style={{ color: '#666' }}>This is the first version — no previous version to diff against.</p>
        )}
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h3>Metadata at this version</h3>
        <pre style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px', overflow: 'auto', fontSize: '0.85rem' }}>
          {version.content_snapshot || '(no metadata)'}
        </pre>
      </section>

      <section style={{ marginBottom: '2rem' }}>
        <h3>Runs produced by v{version.version} ({runs.length})</h3>
        {runs.length === 0 ? (
          <p style={{ color: '#666' }}>No runs used this version.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #ddd' }}>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Run ID</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Status</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Created</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Rating</th>
                <th style={{ textAlign: 'left', padding: '0.5rem' }}>Comments</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} style={{ borderBottom: '1px solid #eee' }}>
                  <td style={{ padding: '0.5rem' }}>
                    <Link to={`/runs/${run.id}`} style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                      {run.id.slice(0, 12)}...
                    </Link>
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    <span className={`status-badge status-${run.status}`}>{run.status}</span>
                  </td>
                  <td style={{ padding: '0.5rem', fontSize: '0.85rem' }}>
                    {new Date(run.created_at).toLocaleString()}
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    <RunRatingStars
                      runId={run.id}
                      initialRating={run.rating ?? null}
                    />
                  </td>
                  <td style={{ padding: '0.5rem' }}>
                    {(run.comments_count ?? 0) > 0 ? `💬 ${run.comments_count}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {comments.length > 0 && (
        <section style={{ marginBottom: '2rem' }}>
          <h3>Comments on runs using v{version.version} ({comments.length})</h3>
          <div>
            {comments.map((c) => (
              <div key={c.id} style={{ borderBottom: '1px solid #eee', padding: '0.75rem 0' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: '#666' }}>
                  <strong>{c.author}</strong>
                  <span>{new Date(c.created_at).toLocaleString()}</span>
                </div>
                <p style={{ margin: '0.25rem 0 0' }}>{c.body}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3>Prompt at v{version.version}</h3>
          <button onClick={() => setShowPrompt(!showPrompt)} className="btn-secondary">
            {showPrompt ? 'Hide' : 'Show'} prompt
          </button>
        </div>
        {showPrompt && (
          <pre style={{ background: '#f5f5f5', padding: '1rem', borderRadius: '4px', overflow: 'auto', fontSize: '0.85rem', whiteSpace: 'pre-wrap' }}>
            {version.prompt_snapshot || '(no prompt content)'}
          </pre>
        )}
      </section>
    </div>
  );
}
