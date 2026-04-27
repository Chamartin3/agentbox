import { useEffect, useState } from 'react';
import { api, AgentDef, ApiError } from '../api/client';

interface Props {
  agent: AgentDef;
  onSaved: (updated: AgentDef) => void;
  onError: (msg: string) => void;
}

export default function ManifestEditor({ agent, onSaved, onError }: Props) {
  const [runnerKind, setRunnerKind] = useState(agent.runner.kind);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [workspaceOptions, setWorkspaceOptions] = useState<string[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // Agent fields
  const [description, setDescription] = useState(agent.description);
  const [sessionMode, setSessionMode] = useState(agent.session_mode);
  const [workspace, setWorkspace] = useState(agent.workspace || '');
  const [tags, setTags] = useState(agent.tags.join(', '));
  const [tools, setTools] = useState(agent.tools.join(', '));
  const [webhookUrl, setWebhookUrl] = useState(agent.webhook_url || '');
  const [headless, setHeadless] = useState(agent.headless);

  // Runner fields
  const [model, setModel] = useState(agent.runner.model || '');
  const [timeout, setTimeoutSec] = useState(String(agent.runner.timeout_seconds));
  const [outputSchemaPath, setOutputSchemaPath] = useState(agent.runner.output_schema_path || '');
  const [maxValidationRetries, setMaxValidationRetries] = useState(String(agent.runner.max_validation_retries));
  const [maxErrorRetries, setMaxErrorRetries] = useState(String(agent.runner.max_error_retries));

  // Sync local state when the agent prop changes (e.g. after a successful save)
  useEffect(() => {
    setRunnerKind(agent.runner.kind);
    setDescription(agent.description);
    setSessionMode(agent.session_mode);
    setWorkspace(agent.workspace || '');
    setTags(agent.tags.join(', '));
    setTools(agent.tools.join(', '));
    setWebhookUrl(agent.webhook_url || '');
    setHeadless(agent.headless);
    setModel(agent.runner.model || '');
    setTimeoutSec(String(agent.runner.timeout_seconds));
    setOutputSchemaPath(agent.runner.output_schema_path || '');
    setMaxValidationRetries(String(agent.runner.max_validation_retries));
    setMaxErrorRetries(String(agent.runner.max_error_retries));
  }, [agent]);

  useEffect(() => {
    let cancelled = false;
    setLoadingModels(true);
    api
      .listRunnerModels(runnerKind)
      .then((res) => {
        if (cancelled) return;
        setModelOptions(res.models);
        if (runnerKind !== agent.runner.kind && !res.models.includes(model)) {
          setModel('');
        }
      })
      .catch(() => {
        if (!cancelled) setModelOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingModels(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runnerKind]);

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

  const dirty =
    runnerKind !== agent.runner.kind ||
    description !== agent.description ||
    sessionMode !== agent.session_mode ||
    workspace !== (agent.workspace || '') ||
    tags !== agent.tags.join(', ') ||
    tools !== agent.tools.join(', ') ||
    webhookUrl !== (agent.webhook_url || '') ||
    headless !== agent.headless ||
    model !== (agent.runner.model || '') ||
    timeout !== String(agent.runner.timeout_seconds) ||
    outputSchemaPath !== (agent.runner.output_schema_path || '') ||
    maxValidationRetries !== String(agent.runner.max_validation_retries) ||
    maxErrorRetries !== String(agent.runner.max_error_retries);

  const save = async () => {
    const patch: Record<string, unknown> = {};
    const runnerPatch: Record<string, unknown> = {};

    if (description !== agent.description) patch.description = description;
    if (sessionMode !== agent.session_mode) patch.session_mode = sessionMode;
    if (workspace !== (agent.workspace || '')) {
      patch.workspace = workspace.trim() || null;
    }

    const newTags = tags.split(',').map((t) => t.trim()).filter(Boolean);
    if (JSON.stringify(newTags) !== JSON.stringify(agent.tags)) {
      patch.tags = newTags;
    }

    const newTools = tools.split(',').map((t) => t.trim()).filter(Boolean);
    if (JSON.stringify(newTools) !== JSON.stringify(agent.tools)) {
      patch.tools = newTools;
    }

    if (webhookUrl !== (agent.webhook_url || '')) {
      patch.webhook_url = webhookUrl.trim() || null;
    }

    if (headless !== agent.headless) {
      patch.headless = headless;
    }

    if (runnerKind !== agent.runner.kind) {
      runnerPatch.kind = runnerKind;
    }
    if (model !== (agent.runner.model || '')) {
      runnerPatch.model = model.trim() || null;
    }
    if (timeout !== String(agent.runner.timeout_seconds)) {
      const n = parseInt(timeout, 10);
      if (Number.isFinite(n) && n > 0) runnerPatch.timeout_seconds = n;
    }
    if (outputSchemaPath !== (agent.runner.output_schema_path || '')) {
      runnerPatch.output_schema_path = outputSchemaPath.trim() || null;
    }
    if (maxValidationRetries !== String(agent.runner.max_validation_retries)) {
      const n = parseInt(maxValidationRetries, 10);
      if (Number.isFinite(n) && n >= 0) runnerPatch.max_validation_retries = n;
    }
    if (maxErrorRetries !== String(agent.runner.max_error_retries)) {
      const n = parseInt(maxErrorRetries, 10);
      if (Number.isFinite(n) && n >= 0) runnerPatch.max_error_retries = n;
    }
    if (Object.keys(runnerPatch).length) patch.runner = runnerPatch;

    try {
      const res = await api.patchAgent(agent.id, patch as Partial<AgentDef>);
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
        <button className="primary" onClick={save} disabled={!dirty}>save configuration</button>
      </div>

      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Identity and execution defaults. Tools, MCP servers, and permissions belong to the
        workspace — manage them there.
      </p>

      <div className="field">
        <label>description</label>
        <input value={description} onChange={(e) => setDescription(e.target.value)} />
      </div>
      <div className="field">
        <label>session_mode</label>
        <select value={sessionMode} onChange={(e) => setSessionMode(e.target.value as AgentDef['session_mode'])}>
          <option value="headless">headless</option>
          <option value="persistent">persistent</option>
        </select>
      </div>
      <div className="field">
        <label>workspace</label>
        {workspaceOptions.length > 0 ? (
          <select
            value={workspace}
            onChange={(e) => setWorkspace(e.target.value)}
            style={{ width: '100%' }}
          >
            <option value="">(auto-resolved)</option>
            <option value="<ephemeral">&lt;ephemeral&gt;</option>
            {workspace &&
              workspace !== '<ephemeral>' &&
              !workspaceOptions.includes(workspace) && (
                <option value={workspace}>{workspace} (current)</option>
              )}
            {workspaceOptions.map((w) => (
              <option key={w} value={w}>{w}</option>
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
      <div className="field">
        <label>tags</label>
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="comma-separated tags"
        />
      </div>
      <div className="field">
        <label>tools</label>
        <input
          value={tools}
          onChange={(e) => setTools(e.target.value)}
          placeholder="comma-separated tool names"
        />
      </div>
      <div className="field">
        <label>webhook_url</label>
        <input
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder="https://..."
        />
      </div>
      <div className="field row">
        <label>
          <input
            type="checkbox"
            checked={headless}
            onChange={(e) => setHeadless(e.target.checked)}
          />
          headless (no interactive tools)
        </label>
      </div>

      <h3 style={{ margin: '14px 0 8px', color: 'var(--fg-muted)', fontSize: 13 }}>runner</h3>
      <div className="field">
        <label>kind</label>
        <select
          value={runnerKind}
          onChange={(e) => setRunnerKind(e.target.value)}
          style={{ width: '100%' }}
        >
          <option value="claude_code">claude_code</option>
          <option value="opencode">opencode</option>
          <option value="pydantic_ai">pydantic_ai</option>
        </select>
      </div>
      <div className="field">
        <label>model</label>
        {modelOptions.length > 0 ? (
          <select value={model} onChange={(e) => setModel(e.target.value)} style={{ width: '100%' }}>
            <option value="">(default)</option>
            {!modelOptions.includes(model) && model && (
              <option value={model}>{model} (current)</option>
            )}
            {modelOptions.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        ) : (
          <input
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={loadingModels ? 'loading models…' : '(default)'}
          />
        )}
      </div>
      <div className="field">
        <label>timeout_seconds</label>
        <input value={timeout} onChange={(e) => setTimeoutSec(e.target.value)} />
      </div>
      <div className="field">
        <label>output_schema_path</label>
        <input
          value={outputSchemaPath}
          onChange={(e) => setOutputSchemaPath(e.target.value)}
          placeholder="e.g. output_schema.json"
        />
      </div>
      <div className="field">
        <label>max_validation_retries</label>
        <input
          type="number"
          min="0"
          value={maxValidationRetries}
          onChange={(e) => setMaxValidationRetries(e.target.value)}
        />
      </div>
      <div className="field">
        <label>max_error_retries</label>
        <input
          type="number"
          min="0"
          value={maxErrorRetries}
          onChange={(e) => setMaxErrorRetries(e.target.value)}
        />
      </div>
    </section>
  );
}
