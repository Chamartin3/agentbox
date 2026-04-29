import { useEffect, useState } from 'react';
import { api, AgentDef, ApiError } from '../api/client';

type BundleFile = {
  kind: string;
  relative_path: string;
  sha256: string;
  source_uri: string | null;
};

interface Props {
  agent: AgentDef;
  bundleFiles?: BundleFile[];
  onSaved: (updated: AgentDef) => void;
  onError: (msg: string) => void;
}

export default function ManifestEditor({ agent, bundleFiles = [], onSaved, onError }: Props) {
  const [runnerKind, setRunnerKind] = useState(agent.runner.kind);
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [workspaceOptions, setWorkspaceOptions] = useState<string[]>([]);
  const [loadingWorkspaces, setLoadingWorkspaces] = useState(false);

  // Agent identity
  const [description, setDescription] = useState(agent.description);
  const [sessionMode, setSessionMode] = useState(agent.session_mode);
  const [workspace, setWorkspace] = useState(agent.workspace || '');
  const [tags, setTags] = useState(agent.tags.join(', '));
  const [webhookUrl, setWebhookUrl] = useState(agent.webhook_url || '');

  // Runner config
  const [model, setModel] = useState(agent.runner.model || '');
  const [timeout, setTimeoutSec] = useState(String(agent.runner.timeout_seconds));
  const [maxValidationRetries, setMaxValidationRetries] = useState(
    String(agent.runner.max_validation_retries),
  );
  const [maxErrorRetries, setMaxErrorRetries] = useState(String(agent.runner.max_error_retries));
  const [validationEngine, setValidationEngine] = useState<string>(
    agent.runner.output_validation_engine || 'both',
  );

  // Composition (bundle resources)
  const [inputSchema, setInputSchema] = useState(agent.composition?.input_schema || '');
  const [outputSchema, setOutputSchema] = useState(agent.composition?.output_schema || '');
  const [userTemplate, setUserTemplate] = useState(agent.composition?.user_template || '');
  const [outputValidation, setOutputValidation] = useState(
    agent.composition?.output_validation || 'strict',
  );

  // Available bundle resources, grouped by kind
  const schemaFiles = bundleFiles.filter(
    (f) => f.kind === 'output_schema' || f.kind === 'input_schema' || f.kind === 'schema',
  );
  const inputSchemaFiles = bundleFiles.filter((f) => f.kind === 'input_schema');
  const outputSchemaFiles = bundleFiles.filter(
    (f) => f.kind === 'output_schema' || f.kind === 'schema',
  );
  const templateFiles = bundleFiles.filter((f) => f.kind === 'user_template');

  // Sync local state when the agent prop changes (e.g. after a successful save)
  useEffect(() => {
    setRunnerKind(agent.runner.kind);
    setDescription(agent.description);
    setSessionMode(agent.session_mode);
    setWorkspace(agent.workspace || '');
    setTags(agent.tags.join(', '));
    setWebhookUrl(agent.webhook_url || '');
    setModel(agent.runner.model || '');
    setTimeoutSec(String(agent.runner.timeout_seconds));
    setMaxValidationRetries(String(agent.runner.max_validation_retries));
    setMaxErrorRetries(String(agent.runner.max_error_retries));
    setValidationEngine(agent.runner.output_validation_engine || 'both');
    setInputSchema(agent.composition?.input_schema || '');
    setOutputSchema(agent.composition?.output_schema || '');
    setUserTemplate(agent.composition?.user_template || '');
    setOutputValidation(agent.composition?.output_validation || 'strict');
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

  const compHas = (k: keyof NonNullable<AgentDef['composition']>, v: unknown) => {
    const cur = (agent.composition?.[k] ?? '') as unknown;
    return (v ?? '') !== (cur ?? '');
  };

  const dirty =
    runnerKind !== agent.runner.kind ||
    description !== agent.description ||
    sessionMode !== agent.session_mode ||
    workspace !== (agent.workspace || '') ||
    tags !== agent.tags.join(', ') ||
    webhookUrl !== (agent.webhook_url || '') ||
    model !== (agent.runner.model || '') ||
    timeout !== String(agent.runner.timeout_seconds) ||
    maxValidationRetries !== String(agent.runner.max_validation_retries) ||
    maxErrorRetries !== String(agent.runner.max_error_retries) ||
    validationEngine !== (agent.runner.output_validation_engine || 'both') ||
    compHas('input_schema', inputSchema) ||
    compHas('output_schema', outputSchema) ||
    compHas('user_template', userTemplate) ||
    compHas('output_validation', outputValidation);

  const save = async () => {
    const patch: Record<string, unknown> = {};
    const runnerPatch: Record<string, unknown> = {};
    const compositionPatch: Record<string, unknown> = {};

    if (description !== agent.description) patch.description = description;
    if (sessionMode !== agent.session_mode) patch.session_mode = sessionMode;
    if (workspace !== (agent.workspace || '')) {
      patch.workspace = workspace.trim() || null;
    }

    const newTags = tags.split(',').map((t) => t.trim()).filter(Boolean);
    if (JSON.stringify(newTags) !== JSON.stringify(agent.tags)) {
      patch.tags = newTags;
    }

    if (webhookUrl !== (agent.webhook_url || '')) {
      patch.webhook_url = webhookUrl.trim() || null;
    }

    if (runnerKind !== agent.runner.kind) runnerPatch.kind = runnerKind;
    if (model !== (agent.runner.model || '')) {
      runnerPatch.model = model.trim() || null;
    }
    if (timeout !== String(agent.runner.timeout_seconds)) {
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

    if (compHas('input_schema', inputSchema)) {
      compositionPatch.input_schema = inputSchema.trim() || null;
    }
    if (compHas('output_schema', outputSchema)) {
      compositionPatch.output_schema = outputSchema.trim() || null;
    }
    if (compHas('user_template', userTemplate)) {
      compositionPatch.user_template = userTemplate.trim() || null;
    }
    if (compHas('output_validation', outputValidation)) {
      compositionPatch.output_validation = outputValidation;
    }
    if (Object.keys(compositionPatch).length) patch.composition = compositionPatch;

    try {
      const res = await api.patchAgent(agent.id, patch as Partial<AgentDef>);
      onSaved(res.agent);
    } catch (e) {
      const err = e as ApiError;
      onError(`patch failed: ${JSON.stringify(err.detail)}`);
    }
  };

  const renderSchemaField = (
    label: string,
    value: string,
    onChange: (v: string) => void,
    options: BundleFile[],
    hint: string,
  ) => (
    <div className="field">
      <label>{label}</label>
      {options.length > 0 ? (
        <select value={value} onChange={(e) => onChange(e.target.value)} style={{ width: '100%' }}>
          <option value="">(none)</option>
          {value && !options.find((o) => o.relative_path === value) && (
            <option value={value}>{value} (current — not in bundle)</option>
          )}
          {options.map((f) => (
            <option key={f.relative_path} value={f.relative_path}>
              {f.relative_path}
            </option>
          ))}
        </select>
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={hint}
        />
      )}
      <p className="dim" style={{ fontSize: 11, marginTop: 4 }}>
        Bundle-relative path. Add files via the agent bundle directory, then they appear here.
      </p>
    </div>
  );

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>
          Configuration
          {dirty && <span className="dirty" style={{ marginLeft: 8 }}>● unsaved</span>}
        </h2>
        <button className="primary" onClick={save} disabled={!dirty}>
          save configuration
        </button>
      </div>

      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Identity, runner, and composition resources. Tools, MCP servers, and permissions live
        in the workspace — manage them there.
      </p>

      {/* ---- Identity ------------------------------------------------- */}
      <fieldset className="config-fieldset">
        <legend>identity</legend>

        <div className="field">
          <label>description</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div className="field">
          <label>session_mode</label>
          <select
            value={sessionMode}
            onChange={(e) => setSessionMode(e.target.value as AgentDef['session_mode'])}
          >
            <option value="headless">headless</option>
            <option value="persistent">persistent</option>
          </select>
          <p className="dim" style={{ fontSize: 11, marginTop: 4 }}>
            One-shot (JSON in/out, no interactive tools) vs. interactive session.
          </p>
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

        <div className="field">
          <label>tags</label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="comma-separated tags"
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
      </fieldset>

      {/* ---- Runner --------------------------------------------------- */}
      <fieldset className="config-fieldset">
        <legend>runner</legend>

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
            <option value="token">token</option>
          </select>
        </div>

        <div className="field">
          <label>model</label>
          {modelOptions.length > 0 ? (
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="">(default)</option>
              {!modelOptions.includes(model) && model && (
                <option value={model}>{model} (current)</option>
              )}
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
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
          <label>output_validation_engine</label>
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

        <div className="row" style={{ gap: 12 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>max_validation_retries</label>
            <input
              type="number"
              min="0"
              value={maxValidationRetries}
              onChange={(e) => setMaxValidationRetries(e.target.value)}
            />
            <p className="dim" style={{ fontSize: 11, marginTop: 4 }}>
              Retries when output fails the JSON schema.
            </p>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>max_error_retries</label>
            <input
              type="number"
              min="0"
              value={maxErrorRetries}
              onChange={(e) => setMaxErrorRetries(e.target.value)}
            />
            <p className="dim" style={{ fontSize: 11, marginTop: 4 }}>
              Retries when the runner errors out (excludes timeouts and validation failures).
            </p>
          </div>
        </div>
      </fieldset>

      {/* ---- Composition resources ----------------------------------- */}
      <fieldset className="config-fieldset">
        <legend>composition resources</legend>
        <p className="dim" style={{ fontSize: 11, marginTop: 0 }}>
          Bundle files attached to this agent — input/output schemas and templates.
          Add files to the agent bundle directory; they appear here once imported.
        </p>

        {renderSchemaField(
          'input_schema',
          inputSchema,
          setInputSchema,
          inputSchemaFiles,
          'e.g. input_schema.json',
        )}
        {renderSchemaField(
          'output_schema',
          outputSchema,
          setOutputSchema,
          outputSchemaFiles,
          'e.g. output_schema.json',
        )}
        {renderSchemaField(
          'user_template',
          userTemplate,
          setUserTemplate,
          templateFiles,
          'e.g. prompts/user.md',
        )}

        <div className="field">
          <label>output_validation</label>
          <select
            value={outputValidation}
            onChange={(e) => setOutputValidation(e.target.value)}
            style={{ width: '100%' }}
          >
            <option value="strict">strict (fail run on schema violation)</option>
            <option value="warn">warn (log only)</option>
            <option value="off">off (no validation)</option>
          </select>
        </div>

        {schemaFiles.length === 0 && templateFiles.length === 0 && (
          <p className="dim" style={{ fontSize: 11 }}>
            No bundle resources stored for this agent version. Add files to the agent bundle
            directory; <code>agentbox versioning backfill-bundles</code> imports them.
          </p>
        )}
      </fieldset>
    </section>
  );
}
