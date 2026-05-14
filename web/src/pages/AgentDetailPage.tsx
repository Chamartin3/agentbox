import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, AgentDef, ApiError } from '../api/client';
import { versionsApi, VersionSummary } from '../api/versions';
import AgentVersions from './AgentVersions';
import ManifestEditor from '../components/ManifestEditor';
import MarkdownEditor from '../components/MarkdownEditor';
import AgentRunsList from '../components/AgentRunsList';
import AgentResourcesEditor from '../components/AgentResourcesEditor';
import Toast from '../components/Toast';
import './AgentDetailPage.css';

type TabType = 'configuration' | 'composition' | 'versions' | 'runs';

export default function AgentDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [agentLoaded, setAgentLoaded] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('configuration');
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);

  const [prompt, setPrompt] = useState<string>('');
  const [promptDirty, setPromptDirty] = useState(false);
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [changelog, setChangelog] = useState('');

  useEffect(() => {
    loadAgent();
    loadPrompt();
    loadVersions();
  }, [id]);

  const loadPrompt = async () => {
    if (!id) return;
    setLoadingPrompt(true);
    try {
      const doc = await api.getPrompt(id);
      setPrompt(doc.content);
      setPromptDirty(false);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 400) setPrompt('');
      else console.error(e);
    } finally {
      setLoadingPrompt(false);
    }
  };

  const loadVersions = async () => {
    if (!id) return;
    try {
      const data = await versionsApi.listVersions(id);
      setVersions(data.versions);
      setActiveVersion(data.active_version ?? data.latest_version);
      const draft = data.versions.find((v) => v.is_draft);
      setDraftVersion(draft ? draft.version : null);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (promptDirty) saveDraft();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [promptDirty, prompt]);

  const saveDraft = async () => {
    if (!id) return;
    try {
      const v = await versionsApi.savePromptRevision(id, prompt, changelog || 'draft from UI', false);
      setPromptDirty(false);
      setChangelog('');
      flash('ok', `draft v${v.version} created`);
      await loadVersions();
      await loadAgent();
    } catch (e) {
      flash('error', `draft save failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const publish = async () => {
    if (!id) return;
    try {
      const v = await versionsApi.savePromptRevision(id, prompt, changelog || 'publish from UI', true);
      setPromptDirty(false);
      setChangelog('');
      flash('ok', `published v${v.version}`);
      await loadVersions();
      await loadAgent();
    } catch (e) {
      flash('error', `publish failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const loadAgent = async () => {
    try {
      const detail = await api.getAgent(id);
      setAgent(detail.agent);
      setCurrentVersion(detail.current_version);
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
      <div className="agent-detail">
        <h1>
          <Link to="/agents">agents</Link> / {id}
        </h1>
        <p>Agent not found. <Link to="/agents">← back to agents</Link></p>
      </div>
    );
  }

  return (
    <div className="agent-detail">
      <header className="agent-header">
        <div className="agent-title">
          <h1>{agent.id}</h1>
          {agent.description && <p className="agent-description">{agent.description}</p>}
        </div>
        <div className="agent-metadata">
          <span className="tag">{agent.source_format || 'unknown'}</span>
          {currentVersion != null && (
            <span className="tag">v{currentVersion}</span>
          )}
          <Link to={`/runs?agent=${encodeURIComponent(agent.id)}`}>
            View Runs →
          </Link>
        </div>
      </header>

      <div className="tabs">
        <button
          className={`tab-button ${activeTab === 'configuration' ? 'active' : ''}`}
          onClick={() => setActiveTab('configuration')}
        >
          Configuration
        </button>
        <button
          className={`tab-button ${activeTab === 'composition' ? 'active' : ''}`}
          onClick={() => setActiveTab('composition')}
        >
          Composition
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
        {activeTab === 'configuration' && (
          <div className="tab-pane stack">
            <ManifestEditor
              agent={agent}
              onSaved={(updated) => {
                setAgent(updated);
                loadAgent();
                flash('ok', 'agent updated');
              }}
              onError={(msg) => flash('error', msg)}
            />
          </div>
        )}

        {activeTab === 'composition' && (
          <div className="tab-pane stack">
            <section className="section">
              <div className="row between" style={{ marginBottom: 8 }}>
                <h2 style={{ border: 'none', margin: 0 }}>Prompt</h2>
                <div className="row" style={{ gap: 6 }}>
                  {activeVersion != null && (
                    <span className="dim" style={{ fontSize: 11 }}>
                      active v{activeVersion}
                      {draftVersion != null && (
                        <span className="dirty"> · draft v{draftVersion}</span>
                      )}
                    </span>
                  )}
                  <button
                    onClick={saveDraft}
                    disabled={!promptDirty || loadingPrompt}
                    className="primary"
                    style={{ fontSize: 11, padding: '4px 10px' }}
                  >
                    Save Draft
                  </button>
                </div>
              </div>

              {loadingPrompt && versions.length === 0 ? (
                <p className="dim">loading…</p>
              ) : (
                <>
                  <MarkdownEditor
                    value={prompt}
                    onChange={(v) => {
                      setPrompt(v);
                      setPromptDirty(true);
                    }}
                  />

                  <div className="row" style={{ gap: 8, marginTop: 10 }}>
                    <input
                      type="text"
                      value={changelog}
                      onChange={(e) => setChangelog(e.target.value)}
                      placeholder="Changelog (optional)"
                      style={{ flex: 1, maxWidth: 300 }}
                    />
                    <button onClick={publish} disabled={loadingPrompt}>
                      Publish
                    </button>
                  </div>

                  <p className="dim" style={{ marginTop: 12, fontSize: 11 }}>
                    Full prompt + agent version history lives in the <strong>Versions</strong> tab.
                  </p>
                </>
              )}
            </section>

            <AgentResourcesEditor
              agentId={id}
              promptTemplate={prompt}
              outputValidation={agent.composition?.output_validation || 'strict'}
              onChangeOutputValidation={async (next) => {
                try {
                  const updated = await api.patchAgent(id, {
                    composition: { output_validation: next },
                  } as unknown as Partial<AgentDef>);
                  setAgent(updated.agent);
                  flash('ok', `output_validation → ${next}`);
                } catch (err) {
                  const e2 = err as ApiError;
                  flash('error', `update failed: ${JSON.stringify(e2.detail)}`);
                }
              }}
            />
          </div>
        )}

        {activeTab === 'versions' && (
          <div className="tab-pane">
            <AgentVersions agentId={agent.id} />
          </div>
        )}

        {activeTab === 'runs' && (
          <div className="tab-pane">
            <AgentRunsList agentId={agent.id} />
          </div>
        )}
      </div>

      {toast && (
        <Toast kind={toast.kind} msg={toast.msg} />
      )}
    </div>
  );
}
