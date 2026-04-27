import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, AgentDef, ApiError, PromptVersionSummary } from '../api/client';
import AgentVersions from './AgentVersions';
import AgentVersionDiff from './AgentVersionDiff';
import CommentThread from '../components/CommentThread';
import ManifestEditor from '../components/ManifestEditor';
import MarkdownEditor from '../components/MarkdownEditor';
import Toast from '../components/Toast';
import './AgentDetailPage.css';

type TabType = 'configuration' | 'composition' | 'versions' | 'runs';

type BundleFile = {
  kind: string;
  relative_path: string;
  sha256: string;
  source_uri: string | null;
};

export default function AgentDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [agentLoaded, setAgentLoaded] = useState(false);
  const [composedSystem, setComposedSystem] = useState<string | null>(null);
  const [composedUser, setComposedUser] = useState<string | null>(null);
  const [bundleFiles, setBundleFiles] = useState<BundleFile[]>([]);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('configuration');
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedVersionNum, setSelectedVersionNum] = useState<number | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);

  const [prompt, setPrompt] = useState<string>('');
  const [promptDirty, setPromptDirty] = useState(false);
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [versions, setVersions] = useState<PromptVersionSummary[]>([]);
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
      const data = await api.listPromptVersions(id);
      setVersions(data.versions);
      setActiveVersion(data.active_version);
      setDraftVersion(data.draft_version);
    } catch (e) {
      const err = e as ApiError;
      if (err.status !== 404) console.error(e);
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
      const doc = await api.savePromptDraft(id, prompt);
      setPrompt(doc.content);
      setPromptDirty(false);
      flash('ok', 'draft saved');
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `draft save failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const publish = async () => {
    if (!id) return;
    try {
      const doc = await api.publishPrompt(id, changelog);
      setPrompt(doc.content);
      setPromptDirty(false);
      setChangelog('');
      flash('ok', `published (${doc.size} bytes)`);
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `publish failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const rollback = async (targetVersion: number) => {
    if (!id) return;
    try {
      const doc = await api.rollbackPrompt(id, targetVersion);
      setPrompt(doc.content);
      setPromptDirty(false);
      flash('ok', `rolled back to v${targetVersion}`);
      loadVersions();
    } catch (e) {
      const err = e as ApiError;
      flash('error', `rollback failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const loadVersionContent = async (version: number) => {
    if (!id) return;
    setLoadingPrompt(true);
    try {
      const data = await api.getPromptVersion(id, version);
      setPrompt(data.content);
      setPromptDirty(false);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingPrompt(false);
    }
  };

  const loadAgent = async () => {
    try {
      const detail = await api.getAgent(id);
      setAgent(detail.agent);
      setComposedSystem(detail.composed_system);
      setComposedUser(detail.composed_user);
      setBundleFiles(detail.bundle_files || []);
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
                flash('ok', 'agent updated');
              }}
              onError={(msg) => flash('error', msg)}
            />

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

                  {versions.length > 0 && (
                    <div style={{ marginTop: 16 }}>
                      <h3 style={{ fontSize: 13, color: 'var(--fg-muted)', marginBottom: 8 }}>
                        Version History
                      </h3>
                      <table>
                        <thead>
                          <tr>
                            <th>Version</th>
                            <th>Author</th>
                            <th>Date</th>
                            <th>Changelog</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {versions.map((v) => (
                            <tr key={v.version}>
                              <td>
                                {v.version === activeVersion && (
                                  <span className="pill ok" style={{ marginRight: 6 }}>active</span>
                                )}
                                {v.is_draft && (
                                  <span className="pill running" style={{ marginRight: 6 }}>draft</span>
                                )}
                                v{v.version}
                              </td>
                              <td className="dim">{v.author}</td>
                              <td className="dim">{new Date(v.created_at).toLocaleDateString()}</td>
                              <td className="dim">{v.changelog || '—'}</td>
                              <td>
                                <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                                  <button
                                    className="link-btn"
                                    onClick={() => loadVersionContent(v.version)}
                                    style={{ fontSize: 11 }}
                                  >
                                    load
                                  </button>
                                  {v.version !== activeVersion && !v.is_draft && (
                                    <button
                                      className="link-btn"
                                      onClick={() => rollback(v.version)}
                                      style={{ fontSize: 11, color: 'var(--red)' }}
                                    >
                                      rollback
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </section>
          </div>
        )}

        {activeTab === 'composition' && (
          <div className="tab-pane stack">
            {agent.composition ? (
              <section className="section">
                <h2>Recipe <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· declared in agent.toml</span></h2>
                <dl className="composition-dl">
                  <dt>System prompt</dt>
                  <dd><code>{agent.composition.system}</code></dd>
                  <dt>Transport</dt>
                  <dd><code>{agent.composition.transport}</code></dd>
                  {agent.composition.user_template && (
                    <>
                      <dt>User template</dt>
                      <dd><code>{agent.composition.user_template}</code></dd>
                    </>
                  )}
                  {agent.composition.output_schema && (
                    <>
                      <dt>Output schema</dt>
                      <dd><code>{agent.composition.output_schema}</code></dd>
                    </>
                  )}
                  <dt>Validation</dt>
                  <dd><code>{agent.composition.output_validation}</code></dd>
                  {agent.composition.references.length > 0 && (
                    <>
                      <dt>References</dt>
                      <dd>
                        <ul className="reference-list">
                          {agent.composition.references.map((ref, i) => {
                            const path = typeof ref === 'string' ? ref : ref.path;
                            const heading = typeof ref === 'string' ? null : ref.heading;
                            return (
                              <li key={i}>
                                <code>{path}</code>
                                {heading && <span className="dim"> → {heading}</span>}
                              </li>
                            );
                          })}
                        </ul>
                      </dd>
                    </>
                  )}
                </dl>
              </section>
            ) : (
              <section className="section">
                <p className="dim">This agent does not declare a <code>[composition]</code> block.</p>
              </section>
            )}

            <section className="section">
              <h2>Bundle Files <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· stored in DB</span></h2>
              {bundleFiles.length === 0 ? (
                <p className="dim">No bundle files stored for this agent version. Run <code>agentbox versioning backfill-bundles</code> to import.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Kind</th>
                      <th>Path</th>
                      <th>Source</th>
                      <th>SHA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bundleFiles.map((f) => (
                      <tr key={f.relative_path}>
                        <td><span className="pill">{f.kind}</span></td>
                        <td className="mono">{f.relative_path}</td>
                        <td className="dim mono" style={{ fontSize: 11 }}>
                          {f.source_uri || '—'}
                        </td>
                        <td className="dim mono" style={{ fontSize: 11 }}>
                          {f.sha256.slice(0, 12)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="section">
              <h2>Final Composed System Prompt <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· references + schema appended</span></h2>
              {composedSystem ? (
                <pre className="composed-block">{composedSystem}</pre>
              ) : (
                <p className="dim">
                  No composition rendered. Bundle files may not be imported yet.
                </p>
              )}
            </section>

            {composedUser !== null && (
              <section className="section">
                <h2>Final Composed User Template</h2>
                {composedUser ? (
                  <pre className="composed-block">{composedUser}</pre>
                ) : (
                  <p className="dim">(empty)</p>
                )}
              </section>
            )}
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
