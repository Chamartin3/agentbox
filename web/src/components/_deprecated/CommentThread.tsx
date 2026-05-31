import { useEffect, useState } from 'react';
import { versionsApi, Comment } from '../api/versions';
import './CommentThread.css';

interface CommentThreadProps {
  versionId: string;
}

export default function CommentThread({ versionId }: CommentThreadProps) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [newComment, setNewComment] = useState('');
  const [isPosting, setIsPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadComments();
  }, [versionId]);

  const loadComments = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await versionsApi.getComments(versionId);
      setComments(data.comments);
    } catch (err) {
      console.error('Failed to load comments:', err);
      setError('Failed to load comments');
    } finally {
      setIsLoading(false);
    }
  };

  const handlePostComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim() || isPosting) return;

    setIsPosting(true);
    setError(null);
    try {
      const posted = await versionsApi.postComment(versionId, newComment);
      setComments([...comments, posted]);
      setNewComment('');
    } catch (err) {
      console.error('Failed to post comment:', err);
      setError('Failed to post comment');
    } finally {
      setIsPosting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  if (isLoading) {
    return <div className="comment-thread">Loading comments...</div>;
  }

  return (
    <div className="comment-thread">
      <h3>Comments ({comments.length})</h3>

      {error && <div className="error-message">{error}</div>}

      {comments.length === 0 ? (
        <p className="no-comments">No comments yet.</p>
      ) : (
        <div className="comments-list">
          {comments.map((comment) => (
            <div key={comment.id} className="comment">
              <div className="comment-header">
                <strong>{comment.author}</strong>
                <span className="comment-date">{formatDate(comment.created_at)}</span>
              </div>
              <div className="comment-body">{comment.body}</div>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handlePostComment} className="comment-form">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          rows={3}
          disabled={isPosting}
        />
        <button
          type="submit"
          disabled={!newComment.trim() || isPosting}
          className="btn-primary"
        >
          {isPosting ? 'Posting...' : 'Post Comment'}
        </button>
      </form>
    </div>
  );
}
