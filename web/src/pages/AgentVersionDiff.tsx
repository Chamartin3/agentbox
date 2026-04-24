import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { versionsApi, VersionSummary, DiffResponse } from '../api/versions';
import './AgentVersionDiff.css';

interface AgentVersionDiffProps {
  agentId?: string;
  latestVersion?: number;
  versions?: VersionSummary[];
}

export default function AgentVersionDiff({
  agentId: propAgentId,
  latestVersion: propLatestVersion,
  versions: propVersions,
}: AgentVersionDiffProps) {
  const { id } = useParams<{ id: string }>();
  const agentId = propAgentId || id || '';
  const [loadedVersions, setLoadedVersions] = useState<VersionSummary[]>(propVersions || []);
  const [loadedLatest, setLoadedLatest] = useState<number>(propLatestVersion || 0);
  const [versionsLoaded, setVersionsLoaded] = useState(!!propVersions);

  useEffect(() => {
    if (!propVersions && agentId) {
      versionsApi.listVersions(agentId).then((data) => {
        setLoadedVersions(data.versions);
        setLoadedLatest(data.latest_version || 0);
        setVersionsLoaded(true);
      }).catch(() => setVersionsLoaded(true));
    }
  }, [agentId, propVersions]);

  const versions = propVersions || loadedVersions;
  const latestVersion = propLatestVersion || loadedLatest;

  const [fromVersion, setFromVersion] = useState<number>(1);
  const [toVersion, setToVersion] = useState<number>(1);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (latestVersion > 1) {
      setFromVersion(latestVersion - 1);
      setToVersion(latestVersion);
    }
  }, [latestVersion]);

  useEffect(() => {
    if (fromVersion >= 0 && toVersion > fromVersion) {
      loadDiff();
    }
  }, [fromVersion, toVersion]);

  const loadDiff = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await versionsApi.diffVersions(agentId, fromVersion, toVersion);
      setDiff(data);
    } catch (err) {
      console.error('Failed to load diff:', err);
      setError('Failed to load diff');
    } finally {
      setIsLoading(false);
    }
  };

  const getLineClass = (type: string) => {
    switch (type) {
      case 'added':
        return 'line-added';
      case 'removed':
        return 'line-removed';
      case 'modified':
        return 'line-modified';
      default:
        return 'line-unchanged';
    }
  };

  return (
    <div className="agent-version-diff">
      <div className="diff-toolbar">
        <div className="version-selectors">
          <label>
            From:
            <select
              value={fromVersion}
              onChange={(e) => setFromVersion(parseInt(e.target.value))}
            >
              {versions.map((v) => (
                <option key={v.id} value={v.version}>
                  v{v.version}
                </option>
              ))}
            </select>
          </label>

          <label>
            To:
            <select value={toVersion} onChange={(e) => setToVersion(parseInt(e.target.value))}>
              {versions.map((v) => (
                <option key={v.id} value={v.version}>
                  v{v.version}
                </option>
              ))}
            </select>
          </label>
        </div>

        <button onClick={loadDiff} disabled={isLoading} className="btn-secondary">
          {isLoading ? 'Loading...' : 'Compare'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {diff && (
        <div className="diff-container">
          <div className="diff-section">
            <h3>Prompt Changes</h3>
            <div className="prompt-diff">
              {diff.prompt_diff.length === 0 ? (
                <p className="no-changes">No changes in prompt content.</p>
              ) : (
                <div className="diff-lines">
                  {diff.prompt_diff.map((line, idx) => (
                    <div key={idx} className={`diff-line ${getLineClass(line.type)}`}>
                      <span className="diff-marker">
                        {line.type === 'added' && '+'}
                        {line.type === 'removed' && '−'}
                        {line.type === 'modified' && '~'}
                      </span>
                      <code>{line.lines.join('\n')}</code>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {diff.metadata_diff.length > 0 && (
            <div className="diff-section">
              <h3>Metadata Changes</h3>
              <table className="metadata-diff">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>From v{fromVersion}</th>
                    <th>To v{toVersion}</th>
                  </tr>
                </thead>
                <tbody>
                  {diff.metadata_diff.map((change, idx) => (
                    <tr key={idx} className="metadata-changed">
                      <td className="field-name">{change.key}</td>
                      <td className="from-value">
                        <code>{JSON.stringify(change.from, null, 2)}</code>
                      </td>
                      <td className="to-value">
                        <code>{JSON.stringify(change.to, null, 2)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {diff.prompt_diff.length === 0 && diff.metadata_diff.length === 0 && (
            <p className="no-changes">No differences between these versions.</p>
          )}
        </div>
      )}
    </div>
  );
}
