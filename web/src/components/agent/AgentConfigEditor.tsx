import { useEffect, useState } from 'react';
import { api, AgentDef, ApiError } from '../../api/client';
import { useAgentActions } from '../../hooks/agents';
import { RunnerProfileSection } from '../runner/RunnerProfileSection';
import { AgentToolGrantsPicker } from './AgentToolGrantsPicker';

interface Props {
  agent: AgentDef;
  onSaved: (updated: AgentDef) => void;
  onError: (msg: string) => void;
}

const DEFAULT_WS = '__default__';

export default function AgentConfigEditor({ agent, onSaved, onError }: Props) {
  const { patch: patchAgent } = useAgentActions();

  const [workspaceOptions, setWorkspaceOptions] = useState<string[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // "" (null) → default auto workspace; otherwise a named workspace.
  const [workspace, setWorkspace] = useState(agent.workspace || '');
  const [webhookUrl, setWebhookUrl] = useState(agent.webhook_url || '');
  const [timeout, setTimeoutSec] = useState(
    agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds),
  );
  const [maxValidationRetries, setMaxValidationRetries] = useState(
    String(agent.runner.max_validation_retries),
  );
  const [maxErrorRetries, setMaxErrorRetries] = useState(String(agent.runner.max_error_retries));
  const [validationEngine, setValidationEngine] = useState<string>(
    agent.runner.output_validation_engine || 'both',
  );

  useEffect(() => {
    setWorkspace(agent.workspace || '');
    setWebhookUrl(agent.webhook_url || '');
    setTimeoutSec(agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds));
    setMaxValidationRetries(String(agent.runner.max_validation_retries));
    setMaxErrorRetries(String(agent.runner.max_error_retries));
    setValidationEngine(agent.runner.output_validation_engine || 'both');
  }, [agent]);

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
      .catch(() => { if (!cancelled) setWorkspaceOptions([]); })
      .finally(() => { if (!cancelled) setLoadingWorkspaces(false); });
    return () => { cancelled = true; };
  }, []);

  const currentWsValue = workspace.trim() || null;
  const originalWsValue = agent.workspace || null;

  const dirty =
    currentWsValue !== originalWsValue ||
    webhookUrl !== (agent.webhook_url || '') ||
    timeout !== (agent.runner.timeout_seconds == null ? '' : String(agent.runner.timeout_seconds)) ||
    maxValidationRetries !== String(agent.runner.max_validation_retries) ||
    maxErrorRetries !== String(agent.runner.max_error_retries) ||
    validationEngine !== (agent.runner.output_validation_engine || 'both');

  const save = async () => {
    const patch: Record<string, unknown> = {};
    const runnerPatch: Record<string, unknown> = {};

    if (currentWsValue !== originalWsValue) patch.workspace = currentWsValue;

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

  const selectValue = workspace === '' ? DEFAULT_WS : workspace;

  return (
    <section className="section">
      {dirty && (
        <div className="config-savebar">
          <span className="dirty">● unsaved changes</span>
          <button className="primary" onClick={save}>save</button>
        </div>
      )}

      {/* ---- Runner profile + Workspace (side by side, responsive) ------ */}
      <div className="config-two-col">
        <RunnerProfileSection agentId={agent.id} />

        {/* Workspace drives the tool catalog below */}
        <fieldset className="config-fieldset">
          <legend>workspace</legend>
          <div className="field" style={{ marginBottom: 0 }}>
            <select
              value={selectValue}
              onChange={(e) => setWorkspace(e.target.value === DEFAULT_WS ? '' : e.target.value)}
              style={{ width: '100%' }}
            >
            <option value={DEFAULT_WS}>Default — dedicated per-agent workspace</option>
            {workspace && !workspaceOptions.includes(workspace) && (
              <option value={workspace}>{workspace}</option>
            )}
            {workspaceOptions.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
            </select>
            <p className="field-hint">
              {workspace
                ? <>Shared workspace — the tool catalog below comes from it.</>
                : <>Dedicated workspace at <code>workspaces/{agent.id}/</code>, created on first run. Tools come from the global catalog.</>}
              {loadingWorkspaces && ' · loading…'}
            </p>
          </div>
        </fieldset>
      </div>

      {/* ---- Tools (catalog served by the selected workspace) ---------- */}
      <AgentToolGrantsPicker agentId={agent.id} workspaceId={workspace || null} />

      {/* ---- Execution (runtime knobs) --------------------------------- */}
      <fieldset className="config-fieldset">
        <legend>execution</legend>

        <div className="field">
          <label>webhook URL</label>
          <input
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://… (optional completion callback)"
          />
        </div>

        <div className="row" style={{ gap: 12 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>timeout (seconds)</label>
            <input value={timeout} onChange={(e) => setTimeoutSec(e.target.value)} placeholder="none" />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>output validation</label>
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
          <div className="field" style={{ flex: 1 }}>
            <label title="Retries when output fails the JSON schema.">max validation retries</label>
            <input type="number" min="0" value={maxValidationRetries} onChange={(e) => setMaxValidationRetries(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label title="Retries when the runner errors out.">max error retries</label>
            <input type="number" min="0" value={maxErrorRetries} onChange={(e) => setMaxErrorRetries(e.target.value)} />
          </div>
        </div>
      </fieldset>
    </section>
  );
}
