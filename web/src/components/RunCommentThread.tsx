import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface RunComment {
  id: number;
  author: string;
  body: string;
  created_at: string;
}

export default function RunCommentThread({ runId }: { runId: string }) {
  const [comments, setComments] = useState<RunComment[]>([]);
  const [draft, setDraft] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await api.listRunComments(runId);
      setComments(data.comments);
    } catch (e) {
      console.error(e);
      setError('failed to load comments');
    }
  };

  useEffect(() => {
    load();
  }, [runId]);

  const post = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = draft.trim();
    if (!body || posting) return;
    setPosting(true);
    setError(null);
    try {
      await api.addRunComment(runId, body);
      setDraft('');
      await load();
    } catch (err) {
      console.error(err);
      setError('failed to post comment');
    } finally {
      setPosting(false);
    }
  };

  return (
    <section className="section">
      <h2 style={{ borderBottom: 'none' }}>
        Comments {comments.length > 0 && <span className="dim">({comments.length})</span>}
      </h2>
      {error && <p className="dim" style={{ color: 'var(--red)' }}>{error}</p>}
      {comments.length === 0 ? (
        <p className="dim" style={{ margin: 0 }}>no comments yet</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
          {comments.map((c) => (
            <div
              key={c.id}
              style={{
                border: '1px solid var(--border)',
                borderRadius: 4,
                padding: '8px 10px',
                background: 'var(--bg-elevated)',
              }}
            >
              <div className="row between" style={{ marginBottom: 4 }}>
                <strong style={{ fontSize: 12 }}>{c.author}</strong>
                <span className="dim" style={{ fontSize: 11 }}>
                  {new Date(c.created_at).toLocaleString()}
                </span>
              </div>
              <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{c.body}</div>
            </div>
          ))}
        </div>
      )}
      <form onSubmit={post} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a note about this run..."
          rows={3}
          disabled={posting}
          style={{ width: '100%', fontFamily: 'inherit', fontSize: 13, padding: 8 }}
        />
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button
            type="submit"
            disabled={!draft.trim() || posting}
            className="primary"
          >
            {posting ? 'Posting…' : 'Post comment'}
          </button>
        </div>
      </form>
    </section>
  );
}
