import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, AgentDef } from '../api/client';
import AgentVersions from './AgentVersions';
import AgentVersionDiff from './AgentVersionDiff';
import CommentThread from '../components/CommentThread';
import ManifestEditor from '../components/ManifestEditor';
import Toast from '../components/Toast';
import './AgentDetailPageV2.css';

type TabType = 'edit' | 'versions' | 'runs';

export default function AgentDetailPageV2() {
  const { id = '' } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [agentLoaded, setAgentLoaded] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>('edit');
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedVersionNum, setSelectedVersionNum] = useState<number | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    loadAgent();
  }, [id]);

  const loadAgent = async () => {
    try {
      const list = await api.listAgents();
      const a = list.find((x) => x.id === id) || null;
      setAgent(a);
    } catch (e) {
      console.error(e);
    } finally {
      setAgentLoaded(true);
    }
  };

  const flash = (kind: 'ok' | 'error', msg: string) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  if (!agent) {
    if (!agentLoaded) return <p>Loading…</p>;
    return (
      <div className="agent-detail-v2">
        <h1>
          <Link to="/agents">agents</Link> / {id}
        </h1>
        <p>Agent not found. <Link to="/agents">← back to agents</Link></p>
      </div>
    );
  }

  return (
    <div className="agent-detail-v2">
      <header className="agent-header">
        <div className="agent-title">
          <h1>{agent.id}</h1>
          {agent.description && <p className="agent-description">{agent.description}</p>}
        </div>
        <div className="agent-metadata">
          <span className="format-badge">{agent.source_format || 'unknown'}</span>
          <Link to={`/runs?agent=${encodeURIComponent(agent.id)}`} className="btn-secondary">
            View Runs →
          </Link>
        </div>
      </header>

      <div className="tabs">
        <button
          className={`tab-button ${activeTab === 'edit' ? 'active' : ''}`}
          onClick={() => setActiveTab('edit')}
        >
          Edit
        </button>
        <button
          className={`tab-button ${activeTab === 'versions' ? 'active' : ''}`}
          onClick={() => setActiveTab('versions')}
        >
          Versions
        </button>
        <button
          className={`tab-button ${activeTab === 'runs' ? 'active' : ''}`}
          onClick={() => setActiveTab('runs')}
        >
          Runs
        </button>
      </div>

      <div className="tab-content">
        {activeTab === 'edit' && (
          <div className="tab-pane">
            <ManifestEditor
              agent={agent}
              onSaved={(updated) => {
                setAgent(updated);
                flash('ok', 'agent updated');
              }}
              onError={(msg) => flash('error', msg)}
            />
          </div>
        )}

        {activeTab === 'versions' && (
          <div className="tab-pane">
            <div className="versions-container">
              <AgentVersions
                agentId={agent.id}
                onSelectVersion={(versionId, versionNum) => {
                  setSelectedVersionId(versionId);
                  setSelectedVersionNum(versionNum);
                }}
              />

              {selectedVersionNum !== null && (
                <div className="version-details">
                  <h3>Version Comparison</h3>
                  <AgentVersionDiff
                    agentId={agent.id}
                    latestVersion={selectedVersionNum}
                    versions={[]} // Would be populated from AgentVersions state
                  />

                  {selectedVersionId && (
                    <CommentThread versionId={selectedVersionId} />
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'runs' && (
          <div className="tab-pane">
            <p className="dim">
              <Link to={`/runs?agent=${encodeURIComponent(agent.id)}`}>
                View all runs for this agent →
              </Link>
            </p>
          </div>
        )}
      </div>

      {toast && (
        <Toast kind={toast.kind} message={toast.msg} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
