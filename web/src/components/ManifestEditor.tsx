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
  const [description, setDescription] = useState(agent.description);
  const [sessionMode, setSessionMode] = useState(agent.session_mode);
  const [workspace, setWorkspace] = useState(agent.workspace || '');
  const [model, setModel] = useState(agent.runner.model || '');
  const [timeout, setTimeoutSec] = useState(String(agent.runner.timeout_seconds));

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
    model !== (agent.runner.model || '') ||
    timeout !== String(agent.runner.timeout_seconds);

  const save = async () => {
    const patch: Record<string, unknown> = {};
    const runnerPatch: Record<string, unknown> = {};

    if (description !== agent.description) patch.description = description;
    if (sessionMode !== agent.session_mode) patch.session_mode = sessionMode;
    if (workspace !== (agent.workspace || '')) {
      patch.workspace = workspace.trim() || null;
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
          Manifest
          {dirty && <span className="dirty" style={{ marginLeft: 8 }}>● unsaved</span>}
        </h2>
        <button className="primary" onClick={save} disabled={!dirty}>save manifest</button>
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
            <option value="<ephemeral>">&lt;ephemeral&gt;</option>
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
    </section>
  );
}
