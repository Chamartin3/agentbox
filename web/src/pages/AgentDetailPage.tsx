import { useEffect, useMemo, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { api, AgentDef, ApiError } from '../api/client';
import { useAgentActions } from '../hooks/agents';
import { useRunsPage, useRunStats } from '../hooks/runs';
import { versionsApi, VersionSummary } from '../api/versions';
import AgentVersions from './AgentVersions';
import AgentConfigEditor from '../components/agent/AgentConfigEditor';
import MarkdownEditor from '../components/common/MarkdownEditor';
import RunsTable, { RunRow } from '../components/runs/RunsTable';
import RunsDashboard from '../components/runs/RunsDashboard';
import AgentResourcesEditor from '../components/agent/AgentResourcesEditor';
import AgentValidationEditor from '../components/agent/AgentValidationEditor';
import LiveComposedPromptPreview, { type PreviewResult } from '../components/agent/LiveComposedPromptPreview';
import Toast from '../components/common/Toast';
import { useToast } from '../hooks/toast';
import './AgentDetailPage.css';

type TabType = 'configuration' | 'composition' | 'versions' | 'runs';

const TABS: TabType[] = ['configuration', 'composition', 'versions', 'runs'];

function parseTab(value: string | undefined): TabType {
  return (TABS as string[]).includes(value ?? '') ? (value as TabType) : 'configuration';
}

const AGENT_PAGE_SIZE = 25;

function AgentRunsTab({
  agentId,
  versions,
}: {
  agentId: string;
  versions: VersionSummary[];
}) {
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [versionFilter, setVersionFilter] = useState<number | ''>('');

  const isLiveView = page === 1 && !statusFilter && versionFilter === '';

  const filterQuery = useMemo(
    () => ({
      agent: agentId,
      status: statusFilter || undefined,
      agent_version: versionFilter === '' ? undefined : versionFilter,
    }),
    [agentId, statusFilter, versionFilter],
  );

  const pagedQuery = useMemo(
    () => ({ ...filterQuery, limit: AGENT_PAGE_SIZE, offset: (page - 1) * AGENT_PAGE_SIZE }),
    [filterQuery, page],
  );
  const runsQ = useRunsPage(pagedQuery);
  const statsQ = useRunStats(filterQuery);
  const data = runsQ.data;
  const stats = statsQ.data;
  const loading = runsQ.loading || statsQ.loading;

  useEffect(() => {
    if (!isLiveView) return;
    const h = window.setInterval(() => {
      runsQ.refresh();
      statsQ.refresh();
    }, 4000);
    return () => window.clearInterval(h);
    // ponytail: refresh fns are stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLiveView]);

  const items = data?.items ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.total / Math.max(1, data.limit))) : 1;

  const runRows: RunRow[] = useMemo(
    () =>
      items.map((r) => ({
        id: r.id,
        agent_id: r.agent_id,
        status: r.status,
        started_at: r.created_at,
        finished_at: r.finished_at,
        backend: r.backend ?? null,
        configured_model: r.configured_model ?? null,
        reported_model: r.model ?? null,
        agent_version: r.agent_version ?? null,
        agent_version_id: r.agent_version_id ?? null,
        input_tokens: r.input_tokens ?? null,
        output_tokens: r.output_tokens ?? null,
        cache_read_tokens: r.cache_read_tokens ?? null,
        cache_creation_tokens: r.cache_write_tokens ?? null,
        cost_usd: r.cost_usd ?? null,
        duration_ms: r.duration_ms ?? null,
      })),
    [items],
  );

  const STATUSES = [
    { value: '', label: 'All' },
    { value: 'ok', label: 'OK' },
    { value: 'failed', label: 'Failed' },
    { value: 'error', label: 'Error' },
    { value: 'incomplete', label: 'Incomplete' },
    { value: 'timeout', label: 'Timeout' },
    { value: 'running', label: 'Running' },
  ];

  return (
    <div className="tab-pane stack">
      <div className="row between" style={{ alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="range-toggle" role="tablist" aria-label="Status">
            {STATUSES.map((s) => (
              <button
                key={s.value || 'all'}
                className={statusFilter === s.value ? 'active' : ''}
                onClick={() => {
                  setStatusFilter(s.value);
                  setPage(1);
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
          <select
            value={versionFilter === '' ? '' : String(versionFilter)}
            onChange={(e) => {
              const v = e.target.value;
              setVersionFilter(v === '' ? '' : Number(v));
              setPage(1);
            }}
            title="Filter by agent version"
          >
            <option value="">All versions</option>
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                v{v.version}
              </option>
            ))}
          </select>
        </div>
        <span className="dim">
          {data ? `${data.total.toLocaleString()} match${data.total === 1 ? '' : 'es'}` : ''}
          {loading ? ' · loading…' : ''}
        </span>
      </div>

      <RunsDashboard stats={stats} scope={{ agentId }} />

      <RunsTable
        items={runRows}
        columns={['run', 'version', 'status', 'started', 'duration', 'runner', 'model', 'tokens']}
        emptyMessage="no runs for this agent"
        loading={loading}
      />

      {data && data.total > AGENT_PAGE_SIZE && (
        <div className="row between">
          <span className="dim">
            page {page} of {totalPages} · showing {items.length} of {data.total}
          </span>
          <div className="row">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading}>
              ← prev
            </button>
            <button onClick={() => setPage((p) => p + 1)} disabled={!data.has_more || loading}>
              next →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentDetailPage() {
  const { id = '', tab: tabParam } = useParams<{ id: string; tab?: string }>();
  const navigate = useNavigate();
  const activeTab = parseTab(tabParam);
  const setActiveTab = (next: TabType) => {
    navigate(`/agents/${encodeURIComponent(id)}/${next}`);
  };
  const [agent, setAgent] = useState<AgentDef | null>(null);
  const [agentLoaded, setAgentLoaded] = useState(false);
  const [currentVersion, setCurrentVersion] = useState<number | null>(null);
  const { toast, flash } = useToast();
  const agentActions = useAgentActions();

  const [prompt, setPrompt] = useState<string>('');
  const [promptDirty, setPromptDirty] = useState(false);
  const [loadingPrompt, setLoadingPrompt] = useState(false);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [changelog, setChangelog] = useState('');
  const [composedPreview, setComposedPreview] = useState<PreviewResult | null>(null);

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
          {agent.disabled_at && (
            <span
              className="tag"
              title={`disabled at ${agent.disabled_at}`}
              style={{ background: '#c0392b', color: '#fff' }}
            >
              disabled
            </span>
          )}
          <button
            onClick={async () => {
              try {
                const r = agent.disabled_at
                  ? await agentActions.enable(agent.id)
                  : await agentActions.disable(agent.id);
                setAgent({ ...agent, disabled_at: r.disabled_at });
                flash('ok', r.disabled_at ? 'agent disabled' : 'agent enabled');
              } catch (e) {
                flash('error', `toggle failed: ${e instanceof Error ? e.message : String(e)}`);
              }
            }}
            style={{ fontSize: 12 }}
          >
            {agent.disabled_at ? 'Enable' : 'Disable'}
          </button>
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
            <AgentConfigEditor
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
          <div className="tab-pane">
            <section className="composition-section">
              <div className="composition-section-header">
                <h3>Prompt</h3>
                <div className="composition-section-meta">
                  {activeVersion != null && (
                    <span>
                      active v{activeVersion}
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
              hideInlinePreview
              onPreview={setComposedPreview}
              outputValidation={agent.composition?.output_validation || 'strict'}
              onChangeOutputValidation={async (next) => {
                try {
                  const updated = await agentActions.patch(id, {
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

            <AgentValidationEditor
              agentId={id}
              hasOutputSchema={!!composedPreview?.output_schema}
            />

            {composedPreview && <LiveComposedPromptPreview preview={composedPreview} />}
          </div>
        )}

        {activeTab === 'versions' && (
          <div className="tab-pane">
            <AgentVersions agentId={agent.id} />
          </div>
        )}

        {activeTab === 'runs' && (
          <AgentRunsTab agentId={agent.id} versions={versions} />
        )}
      </div>

      {toast && (
        <Toast kind={toast.kind} msg={toast.msg} />
      )}
    </div>
  );
}
