import { useEffect, useState, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { versionsApi, VersionSummary } from '../api/versions';
import RatingStars from '../components/RatingStars';
import './AgentVersions.css';

interface AgentVersionsProps {
  agentId?: string;
  onSelectVersion?: (versionId: string, versionNumber: number) => void;
}

type FilterType = 'all' | 'has-comments' | 'has-rating';

export default function AgentVersions({ agentId: propAgentId, onSelectVersion }: AgentVersionsProps) {
  const { id } = useParams<{ id: string }>();
  const agentId = propAgentId || id || '';
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest'>('newest');
  const [selectedForDiff, setSelectedForDiff] = useState<string | null>(null);

  useEffect(() => {
    loadVersions();
  }, [agentId]);

  const loadVersions = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await versionsApi.listVersions(agentId);
      setVersions(data.versions);
    } catch (err) {
      console.error('Failed to load versions:', err);
      setError('Failed to load versions');
    } finally {
      setIsLoading(false);
    }
  };

  const filteredVersions = useMemo(() => {
    let result = [...versions];

    if (filter === 'has-comments') {
      result = result.filter((v) => v.has_comments);
    } else if (filter === 'has-rating') {
      result = result.filter((v) => v.rating !== null);
    }

    if (sortBy === 'oldest') {
      result.reverse();
    }

    return result;
  }, [versions, filter, sortBy]);

  const handleRollback = async (versionId: string) => {
    if (!confirm('Are you sure you want to rollback to this version?')) return;

    try {
      await versionsApi.rollback(agentId, versionId);
      // Reload versions after rollback
      await loadVersions();
    } catch (err) {
      console.error('Failed to rollback:', err);
      alert('Failed to rollback to this version');
    }
  };

  const handleDiffClick = (versionId: string) => {
    if (selectedForDiff === versionId) {
      setSelectedForDiff(null);
    } else {
      setSelectedForDiff(versionId);
    }
  };

  if (isLoading) {
    return <div className="agent-versions">Loading versions...</div>;
  }

  return (
    <div className="agent-versions">
      <div className="versions-toolbar">
        <div className="toolbar-filters">
          <label>
            Filter:
            <select value={filter} onChange={(e) => setFilter(e.target.value as FilterType)}>
              <option value="all">All Versions</option>
              <option value="has-comments">Has Comments</option>
              <option value="has-rating">Has Rating</option>
            </select>
          </label>

          <label>
            Sort:
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'newest' | 'oldest')}>
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
            </select>
          </label>
        </div>

        <button onClick={loadVersions} className="btn-secondary">
          Refresh
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {filteredVersions.length === 0 ? (
        <p className="no-versions">No versions match the current filter.</p>
      ) : (
        <table className="versions-table">
          <thead>
            <tr>
              <th>Version</th>
              <th>Author</th>
              <th>Created</th>
              <th>Changelog</th>
              <th>Rating</th>
              <th>Comments</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredVersions.map((version) => (
              <tr
                key={version.id}
                className={selectedForDiff === version.id ? 'selected-for-diff' : ''}
              >
                <td className="version-cell">
                  v{version.version}
                  {version.is_legacy && <span className="legacy-badge">legacy</span>}
                </td>
                <td>{version.author}</td>
                <td className="date-cell">
                  {new Date(version.created_at).toLocaleDateString()}
                </td>
                <td className="changelog-cell" title={version.changelog}>
                  {version.changelog || '—'}
                </td>
                <td>
                  <RatingStars
                    versionId={version.id}
                    initialRating={version.rating}
                    onRatingChange={() => loadVersions()}
                  />
                </td>
                <td className="center-cell">
                  {version.has_comments ? (
                    <span className="comment-indicator">💬</span>
                  ) : (
                    <span className="empty-cell">—</span>
                  )}
                </td>
                <td className="actions-cell">
                  <button
                    onClick={() => onSelectVersion?.(version.id, version.version)}
                    className="btn-small"
                    title="View this version"
                  >
                    View
                  </button>
                  <button
                    onClick={() => handleDiffClick(version.id)}
                    className={`btn-small ${selectedForDiff === version.id ? 'active' : ''}`}
                    title="Compare with current"
                  >
                    Diff
                  </button>
                  {!version.is_legacy && (
                    <button
                      onClick={() => handleRollback(version.id)}
                      className="btn-small btn-danger"
                      title="Rollback to this version"
                    >
                      Rollback
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="versions-footer">
        Showing {filteredVersions.length} of {versions.length} versions
      </div>
    </div>
  );
}
