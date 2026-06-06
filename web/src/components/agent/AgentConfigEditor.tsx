import { useEffect, useState, KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, AgentDef, ApiError } from '../../api/client';
import { useAgentActions } from '../../hooks/agents';
import { RunnerProfileSection } from '../runner/RunnerProfileSection';
import { AgentToolGrantsPicker } from './AgentToolGrantsPicker';

interface Props {
  agent: AgentDef;
  onSaved: (updated: AgentDef) => void;
  onError: (msg: string) => void;
}

export default function AgentConfigEditor({ agent, onSaved, onError }: Props) {
  const navigate = useNavigate();
  const { patch: patchAgent } = useAgentActions();

  const [workspaceOptions, setWorkspaceOptions] = useState<string[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // Agent identity
  const [description, setDescription] = useState(agent.description);
  const [sessionMode, setSessionMode] = useState(agent.session_mode);
  const [workspace, setWorkspace] = useState(agent.workspace || '');
  const [tags, setTags] = useState<string[]>(agent.tags);
  const [tagInput, setTagInput] = useState('');
  const [webhookUrl, setWebhookUrl] = useState(agent.webhook_url || '');

  // Runner config (kind+model live on the bound runner profile; only
  // agent-level execution overrides are edited here).
  const [timeout, setTimeoutSec] = useState((agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds)));
  const [maxValidationRetries, setMaxValidationRetries] = useState(
    String(agent.runner.max_validation_retries),
  );
  const [maxErrorRetries, setMaxErrorRetries] = useState(String(agent.runner.max_error_retries));
  const [validationEngine, setValidationEngine] = useState<string>(
    agent.runner.output_validation_engine || 'both',
  );

  // Sync local state when the agent prop changes (e.g. after a successful save)
  useEffect(() => {
    setDescription(agent.description);
    setSessionMode(agent.session_mode);
    setWorkspace(agent.workspace || '');
    setTags(agent.tags);
    setTagInput('');
    setWebhookUrl(agent.webhook_url || '');
    setTimeoutSec((agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds)));
    setMaxValidationRetries(String(agent.runner.max_validation_retries));
    setMaxErrorRetries(String(agent.runner.max_error_retries));
    setValidationEngine(agent.runner.output_validation_engine || 'both');
  }, [agent]);

  const addTag = (raw: string) => {
    const trimmed = raw.trim().replace(/,$/, '').trim();
    if (!trimmed) return;
    if (tags.includes(trimmed)) {
      setTagInput('');
      return;
    }
    setTags([...tags, trimmed]);
    setTagInput('');
  };

  const removeTag = (t: string) => {
    setTags(tags.filter((x) => x !== t));
  };

  const onTagKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',' || e.key === 'Tab') {
      if (tagInput.trim()) {
        e.preventDefault();
        addTag(tagInput);
      }
    } else if (e.key === 'Backspace' && !tagInput && tags.length > 0) {
      removeTag(tags[tags.length - 1]);
    }
  };

  useEffect(() => {
    let cancelled = false;
    setLoadingWorkspaces(true);
    api
      .listWorkspaces()
      .then((data) => {
        if (cancelled) return;
        const names = (data as Array<{ name?: unknown }>)
          .map((w) => (typeof w.name === 'string' ? w.name : ''))
          .filter((n): n is string => !!n);
        setWorkspaceOptions(names);
      })
      .catch(() => {
        if (!cancelled) setWorkspaceOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingWorkspaces(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tagsDirty = JSON.stringify(tags) !== JSON.stringify(agent.tags);

  const dirty =
    description !== agent.description ||
    sessionMode !== agent.session_mode ||
    workspace !== (agent.workspace || '') ||
    tagsDirty ||
    webhookUrl !== (agent.webhook_url || '') ||
    timeout !== (agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds)) ||
    maxValidationRetries !== String(agent.runner.max_validation_retries) ||
    maxErrorRetries !== String(agent.runner.max_error_retries) ||
    validationEngine !== (agent.runner.output_validation_engine || 'both');

  const save = async () => {
    const patch: Record<string, unknown> = {};
    const runnerPatch: Record<string, unknown> = {};

    if (description !== agent.description) patch.description = description;
    if (sessionMode !== agent.session_mode) patch.session_mode = sessionMode;
    if (workspace !== (agent.workspace || '')) {
      patch.workspace = workspace.trim() || null;
    }

    // Include any pending input as a tag before saving
    const pending = tagInput.trim();
    const finalTags = pending && !tags.includes(pending) ? [...tags, pending] : tags;
    if (JSON.stringify(finalTags) !== JSON.stringify(agent.tags)) {
      patch.tags = finalTags;
    }

    if (webhookUrl !== (agent.webhook_url || '')) {
      patch.webhook_url = webhookUrl.trim() || null;
    }

    if (timeout !== (agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds))) {
      const n = parseInt(timeout, 10);
      if (Number.isFinite(n) && n > 0) runnerPatch.timeout_seconds = n;
    }
    if (maxValidationRetries !== String(agent.runner.max_validation_retries)) {
      const n = parseInt(maxValidationRetries, 10);
      if (Number.isFinite(n) && n >= 0) runnerPatch.max_validation_retries = n;
    }
    if (maxErrorRetries !== String(agent.runner.max_error_retries)) {
      const n = parseInt(maxErrorRetries, 10);
      if (Number.isFinite(n) && n >= 0) runnerPatch.max_error_retries = n;
    }
    if (validationEngine !== (agent.runner.output_validation_engine || 'both')) {
      runnerPatch.output_validation_engine = validationEngine;
    }
    if (Object.keys(runnerPatch).length) patch.runner = runnerPatch;

    try {
      const res = await patchAgent(agent.id, patch as Partial<AgentDef>);
      onSaved(res.agent);
    } catch (e) {
      const err = e as ApiError;
      onError(`patch failed: ${JSON.stringify(err.detail)}`);
    }
  };

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>
          Configuration
          {dirty && <span className="dirty" style={{ marginLeft: 8 }}>● unsaved</span>}
        </h2>
        <div className="row" style={{ gap: 6 }}>
          <button onClick={() => navigate('/agents/new')}>
            + new agent
          </button>
          <button className="primary" onClick={save} disabled={!dirty}>
            save configuration
          </button>
        </div>
      </div>

      {/* ---- Identity ------------------------------------------------- */}
      <fieldset className="config-fieldset">
        <legend>identity</legend>

        <div className="field">
          <label>description</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="row" style={{ gap: 12 }}>
          <div className="field" style={{ flex: 1, marginBottom: 8 }}>
            <label title="One-shot (JSON in/out, no interactive tools) vs. interactive session.">
              session_mode
            </label>
            <select
              value={sessionMode}
              onChange={(e) => setSessionMode(e.target.value as AgentDef['session_mode'])}
            >
              <option value="headless">headless</option>
              <option value="persistent">persistent</option>
            </select>
          </div>
          <div className="field" style={{ flex: 1, marginBottom: 8 }}>
            <label>workspace</label>
            {workspaceOptions.length > 0 ? (
              <select
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="">(auto-resolved)</option>
                <option value="<ephemeral>">&lt;ephemeral&gt;</option>
                {workspace &&
                  workspace !== '<ephemeral>' &&
                  !workspaceOptions.includes(workspace) && (
                    <option value={workspace}>{workspace} (current)</option>
                  )}
                {workspaceOptions.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
            ) : (
              <input
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
                placeholder={
                  loadingWorkspaces
                    ? 'loading workspaces…'
                    : '(auto-resolved) — use <ephemeral> for tmp'
                }
              />
            )}
          </div>
        </div>

        <div className="field">
          <label>tags</label>
          <div
            className="tag-chip-input"
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 4,
              alignItems: 'center',
              padding: 4,
              border: '1px solid var(--border)',
              borderRadius: 4,
              background: 'var(--bg-input, var(--bg))',
            }}
            onClick={(e) => {
              const target = e.target as HTMLElement;
              if (target.tagName !== 'INPUT') {
                const input = (e.currentTarget as HTMLElement).querySelector('input');
                input?.focus();
              }
            }}
          >
            {tags.map((t) => (
              <span
                key={t}
                className="tag"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '2px 6px',
                  fontSize: 12,
                }}
              >
                {t}
                <button
                  type="button"
                  aria-label={`remove ${t}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    removeTag(t);
                  }}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    padding: 0,
                    margin: 0,
                    cursor: 'pointer',
                    fontSize: 12,
                    lineHeight: 1,
                    color: 'inherit',
                  }}
                >
                  ×
                </button>
              </span>
            ))}
            <input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={onTagKeyDown}
              onBlur={() => {
                if (tagInput.trim()) addTag(tagInput);
              }}
              placeholder={tags.length === 0 ? 'add tags (Enter or comma to add)' : ''}
              style={{
                flex: 1,
                minWidth: 120,
                border: 'none',
                outline: 'none',
                background: 'transparent',
                padding: '2px 4px',
              }}
            />
          </div>
        </div>

      </fieldset>

      {/* ---- Execution -------------------------------------------------- */}
      <RunnerProfileSection agentId={agent.id} />

      <AgentToolGrantsPicker agentId={agent.id} />

      <fieldset className="config-fieldset">
        <legend>execution</legend>

        <div className="field">
          <label>webhook_url</label>
          <input
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://..."
          />
        </div>

        <div className="row" style={{ gap: 12 }}>
          <div className="field" style={{ flex: 1, marginBottom: 8 }}>
            <label>timeout_seconds</label>
            <input value={timeout} onChange={(e) => setTimeoutSec(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1, marginBottom: 8 }}>
            <label>validation_engine</label>
            <select
              value={validationEngine}
              onChange={(e) => setValidationEngine(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="both">both (jsonschema → pydantic)</option>
              <option value="jsonschema">jsonschema only</option>
              <option value="pydantic">pydantic only</option>
            </select>
          </div>
        </div>

        <div className="row" style={{ gap: 12 }}>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <label title="Retries when output fails the JSON schema.">
              max_validation_retries
            </label>
            <input
              type="number"
              min="0"
              value={maxValidationRetries}
              onChange={(e) => setMaxValidationRetries(e.target.value)}
            />
          </div>
          <div className="field" style={{ flex: 1, marginBottom: 0 }}>
            <label title="Retries when the runner errors out (excludes timeouts and validation failures).">
              max_error_retries
            </label>
            <input
              type="number"
              min="0"
              value={maxErrorRetries}
              onChange={(e) => setMaxErrorRetries(e.target.value)}
            />
          </div>
        </div>
      </fieldset>

    </section>
  );
}
