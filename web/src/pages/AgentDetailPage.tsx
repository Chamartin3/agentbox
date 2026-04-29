import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, AgentDef, ApiError, PromptVersionSummary } from '../api/client';
import AgentVersions from './AgentVersions';
import AgentVersionDiff from './AgentVersionDiff';
import CommentThread from '../components/CommentThread';
import ManifestEditor from '../components/ManifestEditor';
import MarkdownEditor from '../components/MarkdownEditor';
import AgentRunsList from '../components/AgentRunsList';
import Toast from '../components/Toast';
import './AgentDetailPage.css';

type TabType = 'configuration' | 'composition' | 'versions' | 'runs';

function fmtNum(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function SizeBadge({ text }: { text: string }) {
  const chars = text.length;
  const tokens = Math.ceil(chars / 4);
  return (
    <span
      className="dim"
      style={{ fontWeight: 400, fontSize: 12, marginLeft: 10 }}
      title={`${chars.toLocaleString()} chars · ~${tokens.toLocaleString()} tokens (chars / 4 heuristic)`}
    >
      · {fmtNum(chars)} chars · ~{fmtNum(tokens)} tokens
    </span>
  );
}

type BundleFile = {
  kind: string;
  relative_path: string;
  sha256: string;
  source_uri: string | null;
  char_count?: number;
};

function CountChip({ chars, label }: { chars: number; label?: string }) {
  const tokens = Math.ceil(chars / 4);
  return (
    <span
      className="dim"
      style={{ fontSize: 11, fontFamily: 'var(--mono, monospace)' }}
      title={`${chars.toLocaleString()} chars · ~${tokens.toLocaleString()} tokens (chars / 4 heuristic)`}
    >
      {label ? `${label}: ` : ''}
      {fmtNum(chars)}c · ~{fmtNum(tokens)}t
    </span>
  );
}

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
              bundleFiles={bundleFiles}
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
                  {agent.composition.input_schema && (
                    <>
                      <dt>Input schema</dt>
                      <dd><code>{agent.composition.input_schema}</code></dd>
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
              <h2>
                Bundle Files{' '}
                <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>· stored in DB</span>
                {bundleFiles.length > 0 && (
                  <span style={{ marginLeft: 10 }}>
                    <CountChip
                      chars={bundleFiles.reduce((s, f) => s + (f.char_count || 0), 0)}
                      label="total"
                    />
                  </span>
                )}
              </h2>
              {bundleFiles.length === 0 ? (
                <p className="dim">No bundle files stored for this agent version. Run <code>agentbox versioning backfill-bundles</code> to import.</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>Kind</th>
                      <th>Path</th>
                      <th>Size</th>
                      <th>Source</th>
                      <th>SHA</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bundleFiles.map((f) => (
                      <tr key={f.relative_path}>
                        <td><span className="pill">{f.kind}</span></td>
                        <td className="mono">{f.relative_path}</td>
                        <td className="dim mono" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                          {f.char_count != null ? (
                            <CountChip chars={f.char_count} />
                          ) : (
                            '—'
                          )}
                        </td>
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
              <h2>
                Final Composed System Prompt{' '}
                <span className="dim" style={{ fontWeight: 400, fontSize: 12 }}>
                  · references + schema appended
                </span>
                {composedSystem && (
                  <SizeBadge text={composedSystem} />
                )}
              </h2>
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
                <h2>
                  Final Composed User Template
                  {composedUser && <SizeBadge text={composedUser} />}
                </h2>
                {composedUser ? (
                  <pre className="composed-block">{composedUser}</pre>
                ) : (
                  <p className="dim">(empty)</p>
                )}
              </section>
            )}

            {(composedSystem || composedUser) && (() => {
              const sysChars = (composedSystem || '').length;
              const userChars = (composedUser || '').length;
              const promptBodyChars = (prompt || '').length;
              const bundleTotal = bundleFiles.reduce((s, f) => s + (f.char_count || 0), 0);
              // Filter bundle files by kind so we can break out schemas etc.
              const byKind: Record<string, number> = {};
              for (const f of bundleFiles) {
                byKind[f.kind] = (byKind[f.kind] || 0) + (f.char_count || 0);
              }
              const totalChars = sysChars + userChars;
              const rows: Array<{ label: string; chars: number; note?: string }> = [
                { label: 'Prompt body (editable system.md)', chars: promptBodyChars },
                ...Object.entries(byKind)
                  .filter(([k]) => k !== 'system')
                  .map(([k, c]) => ({ label: `Bundle · ${k}`, chars: c })),
                { label: 'Final composed system prompt', chars: sysChars, note: 'prompt + references + schema instructions' },
                { label: 'Final composed user template', chars: userChars },
              ];
              return (
                <section className="section">
                  <h2>
                    Composed payload breakdown
                    <span style={{ marginLeft: 10 }}>
                      <CountChip chars={totalChars} label="payload" />
                    </span>
                  </h2>
                  <table style={{ marginTop: 4 }}>
                    <thead>
                      <tr>
                        <th>Component</th>
                        <th style={{ textAlign: 'right' }}>Chars</th>
                        <th style={{ textAlign: 'right' }}>~Tokens</th>
                        <th style={{ textAlign: 'right' }}>% of payload</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const tokens = Math.ceil(r.chars / 4);
                        const pct = totalChars > 0 ? Math.round((r.chars / totalChars) * 100) : 0;
                        return (
                          <tr key={r.label}>
                            <td>
                              {r.label}
                              {r.note && (
                                <span className="dim" style={{ fontSize: 11, marginLeft: 6 }}>
                                  · {r.note}
                                </span>
                              )}
                            </td>
                            <td className="mono" style={{ textAlign: 'right' }}>
                              {r.chars.toLocaleString()}
                            </td>
                            <td className="mono dim" style={{ textAlign: 'right' }}>
                              ~{tokens.toLocaleString()}
                            </td>
                            <td className="mono dim" style={{ textAlign: 'right' }}>
                              {pct}%
                            </td>
                          </tr>
                        );
                      })}
                      <tr style={{ borderTop: '1px solid var(--border)', fontWeight: 600 }}>
                        <td>Total sent to model (system + user)</td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          {totalChars.toLocaleString()}
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          ~{Math.ceil(totalChars / 4).toLocaleString()}
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>100%</td>
                      </tr>
                      <tr>
                        <td className="dim" style={{ fontSize: 11 }}>
                          Raw bundle files (system + references + schemas, before composition)
                        </td>
                        <td className="mono dim" style={{ textAlign: 'right', fontSize: 11 }}>
                          {bundleTotal.toLocaleString()}
                        </td>
                        <td className="mono dim" style={{ textAlign: 'right', fontSize: 11 }}>
                          ~{Math.ceil(bundleTotal / 4).toLocaleString()}
                        </td>
                        <td className="mono dim" style={{ textAlign: 'right', fontSize: 11 }}>
                          —
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  <p className="dim" style={{ marginTop: 10, fontSize: 11 }}>
                    Token estimate uses the OpenAI heuristic of ~4 chars per token.
                    Real tokenization varies by model (Claude / DeepSeek / GPT each
                    differ by ±15%). The composed totals already include the
                    references and the schema instruction block appended at
                    composition time, so they are what the model actually receives.
                  </p>
                </section>
              );
            })()}
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
            <AgentRunsList agentId={agent.id} />
          </div>
        )}
      </div>

      {toast && (
        <Toast kind={toast.kind} message={toast.msg} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
