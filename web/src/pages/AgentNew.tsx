import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError, RunnerKind } from '../api/client';

// ---- validation helpers ---------------------------------------------------

function isValidId(id: string): boolean {
  return /^[a-z0-9][a-z0-9_-]*$/.test(id) && id.length >= 1 && id.length <= 128;
}

// ---- step types -----------------------------------------------------------

type Step = 1 | 2 | 3 | 4 | 5;

const STEP_LABELS: Record<Step, string> = {
  1: 'Identity',
  2: 'Runner',
  3: 'Prompt',
  4: 'Tools',
  5: 'Review',
};

const RUNNER_KINDS: RunnerKind[] = ['claude_code', 'opencode', 'pydantic_ai'];

// ---- wizard ---------------------------------------------------------------

export default function AgentNew() {
  const navigate = useNavigate();

  // Step tracking
  const [step, setStep] = useState<Step>(1);

  // Step 1: Identity
  const [agentId, setAgentId] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [idError, setIdError] = useState<string | null>(null);

  // Step 2: Runner
  const [runnerKind, setRunnerKind] = useState<RunnerKind>('claude_code');
  const [model, setModel] = useState('');
  const [timeoutSec, setTimeoutSec] = useState('600');
  const [outputSchemaPath, setOutputSchemaPath] = useState('');
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Step 3: Prompt
  const [promptMode, setPromptMode] = useState<'inline' | 'none'>('inline');
  const [prompt, setPrompt] = useState('');

  // Step 4: Tools
  const [toolsText, setToolsText] = useState('');

  // Step 5: Review & submit
  const [author, setAuthor] = useState('');
  const [changelog, setChangelog] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Load model options when runner kind changes
  useEffect(() => {
    let cancelled = false;
    setLoadingModels(true);
    api
      .listRunnerModels(runnerKind)
      .then((res) => {
        if (cancelled) return;
        setModelOptions(res.models);
        // reset model if no longer valid
        if (!res.models.includes(model)) setModel('');
      })
      .catch(() => {
        if (!cancelled) setModelOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingModels(false);
      });
    return () => { cancelled = true; };
  }, [runnerKind]);

  // ---- navigation ----------------------------------------------------------

  const validateStep1 = (): boolean => {
    if (!agentId) { setIdError('Agent ID is required.'); return false; }
    if (!isValidId(agentId)) {
      setIdError('Use lowercase letters, digits, hyphens, or underscores. Must start with a letter or digit.');
      return false;
    }
    setIdError(null);
    return true;
  };

  const canProceed = (): boolean => {
    if (step === 1) return !!agentId && !idError;
    if (step === 5) return !!author && changelog.length >= 3;
    return true;
  };

  const goNext = () => {
    if (step === 1 && !validateStep1()) return;
    if (step < 5) setStep((s) => (s + 1) as Step);
  };

  const goPrev = () => {
    if (step > 1) setStep((s) => (s - 1) as Step);
  };

  // ---- submit --------------------------------------------------------------

  const handleSubmit = async () => {
    if (!validateStep1()) { setStep(1); return; }
    if (!author || changelog.length < 3) return;

    setSubmitting(true);
    setSubmitError(null);

    const tools = toolsText
      .split('\n')
      .map((t) => t.trim())
      .filter(Boolean);

    const parsedTags = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const runner = {
      kind: runnerKind,
      model: model || null,
      timeout_seconds: parseInt(timeoutSec, 10) || 600,
      output_schema_path: outputSchemaPath.trim() || null,
      allowed_tools: [],
      extra_args: [],
      mcp_config_path: null,
      agents_config_path: null,
      settings_path: null,
      config_path: null,
      command: null,
      output_validation_engine: 'both' as const,
      max_validation_retries: 1,
      max_error_retries: 0,
    };

    try {
      const result = await api.createAgent({
        id: agentId,
        description,
        runner,
        prompt: promptMode === 'inline' && prompt.trim() ? prompt.trim() : undefined,
        tools,
        tags: parsedTags,
        author,
        changelog,
      });

      navigate(`/agents/${result.agent_id}`);
    } catch (e) {
      const err = e as ApiError;
      const detail = err.detail as Record<string, unknown> | string | null;
      if (typeof detail === 'object' && detail && 'code' in detail && detail['code'] === 'already_exists') {
        setSubmitError(`An agent with ID "${agentId}" already exists.`);
      } else {
        setSubmitError(`Create failed (HTTP ${err.status}): ${JSON.stringify(err.detail)}`);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ---- render helpers ------------------------------------------------------

  const renderStepIndicator = () => (
    <div className="wizard-steps">
      {([1, 2, 3, 4, 5] as Step[]).map((s) => (
        <div key={s} className={`wizard-step ${s === step ? 'active' : s < step ? 'done' : ''}`}>
          <span className="wizard-step-num">{s < step ? '✓' : s}</span>
          <span className="wizard-step-label">{STEP_LABELS[s]}</span>
        </div>
      ))}
    </div>
  );

  const renderStep1 = () => (
    <div className="stack">
      <h2 style={{ border: 'none', margin: 0 }}>Identity</h2>
      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Set the stable identifier and metadata for this agent.
      </p>

      <div className="field">
        <label>id *</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <input
            value={agentId}
            onChange={(e) => { setAgentId(e.target.value); setIdError(null); }}
            onBlur={validateStep1}
            placeholder="my-agent (lowercase, digits, hyphens, underscores)"
            autoFocus
          />
          {idError && <span style={{ color: 'var(--red)', fontSize: 11 }}>{idError}</span>}
        </div>
      </div>

      <div className="field">
        <label>description *</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What does this agent do?"
        />
      </div>

      <div className="field">
        <label>tags</label>
        <input
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          placeholder="comma-separated, e.g. analysis, cv, draft"
        />
      </div>
    </div>
  );

  const renderStep2 = () => (
    <div className="stack">
      <h2 style={{ border: 'none', margin: 0 }}>Runner</h2>
      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Choose which backend executes this agent.
      </p>

      <div className="field">
        <label>kind *</label>
        <select
          value={runnerKind}
          onChange={(e) => setRunnerKind(e.target.value as RunnerKind)}
          style={{ width: '100%' }}
        >
          {RUNNER_KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
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
        <label>timeout (s)</label>
        <input
          type="number"
          min="1"
          value={timeoutSec}
          onChange={(e) => setTimeoutSec(e.target.value)}
        />
      </div>

      <div className="field">
        <label>output_schema_path</label>
        <input
          value={outputSchemaPath}
          onChange={(e) => setOutputSchemaPath(e.target.value)}
          placeholder="optional, e.g. output_schema.json"
        />
      </div>
    </div>
  );

  const renderStep3 = () => (
    <div className="stack">
      <h2 style={{ border: 'none', margin: 0 }}>Prompt</h2>
      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Provide an inline system prompt. You can edit and version it later from the agent detail page.
      </p>

      <div className="range-toggle" style={{ marginBottom: 8 }}>
        <button
          className={promptMode === 'inline' ? 'active' : ''}
          onClick={() => setPromptMode('inline')}
          type="button"
        >
          Inline prompt
        </button>
        <button
          className={promptMode === 'none' ? 'active' : ''}
          onClick={() => setPromptMode('none')}
          type="button"
        >
          No prompt yet
        </button>
      </div>

      {promptMode === 'inline' && (
        <div className="field" style={{ alignItems: 'flex-start' }}>
          <label style={{ paddingTop: 6 }}>system prompt</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={14}
            placeholder="You are an assistant that…"
            style={{ width: '100%', resize: 'vertical', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
          />
        </div>
      )}

      {promptMode === 'none' && (
        <p className="dim" style={{ fontSize: 12 }}>
          The agent will be created without a prompt. Add one from the Composition tab after creation.
        </p>
      )}
    </div>
  );

  const renderStep4 = () => (
    <div className="stack">
      <h2 style={{ border: 'none', margin: 0 }}>Tools / MCP</h2>
      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Allowed tools — one per line (e.g. <code>Read</code>, <code>Write</code>, <code>Bash</code>).
        MCP server configuration lives in the workspace.
      </p>

      <div className="field" style={{ alignItems: 'flex-start' }}>
        <label style={{ paddingTop: 6 }}>tools</label>
        <textarea
          value={toolsText}
          onChange={(e) => setToolsText(e.target.value)}
          rows={8}
          placeholder={'Read\nWrite\nBash\n...'}
          style={{ width: '100%', resize: 'vertical', fontFamily: 'ui-monospace, monospace', fontSize: 12 }}
        />
      </div>
    </div>
  );

  const renderReviewRow = (label: string, value: string) => (
    <tr key={label}>
      <td className="dim" style={{ fontSize: 12, paddingRight: 12, whiteSpace: 'nowrap', verticalAlign: 'top' }}>{label}</td>
      <td style={{ fontSize: 12, fontFamily: 'monospace', wordBreak: 'break-word' }}>{value || '—'}</td>
    </tr>
  );

  const renderStep5 = () => {
    const tools = toolsText.split('\n').map((t) => t.trim()).filter(Boolean);
    const parsedTags = tags.split(',').map((t) => t.trim()).filter(Boolean);

    return (
      <div className="stack">
        <h2 style={{ border: 'none', margin: 0 }}>Review &amp; Create</h2>
        <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
          Check the summary below, then provide your author handle and a changelog entry.
        </p>

        <div className="section" style={{ padding: 12 }}>
          <table style={{ width: '100%' }}>
            <tbody>
              {renderReviewRow('id', agentId)}
              {renderReviewRow('description', description)}
              {renderReviewRow('tags', parsedTags.join(', '))}
              {renderReviewRow('runner.kind', runnerKind)}
              {renderReviewRow('runner.model', model || '(default)')}
              {renderReviewRow('runner.timeout_seconds', timeoutSec)}
              {renderReviewRow('runner.output_schema_path', outputSchemaPath)}
              {renderReviewRow('prompt', promptMode === 'inline' ? `${prompt.slice(0, 80)}${prompt.length > 80 ? '…' : ''}` : '(none)')}
              {renderReviewRow('tools', tools.length ? tools.join(', ') : '(none)')}
            </tbody>
          </table>
        </div>

        <div className="field">
          <label>author *</label>
          <input
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="your handle or email"
            autoFocus
          />
        </div>

        <div className="field">
          <label>changelog *</label>
          <input
            value={changelog}
            onChange={(e) => setChangelog(e.target.value)}
            placeholder="Initial creation (min 3 chars)"
          />
          {changelog.length > 0 && changelog.length < 3 && (
            <span style={{ color: 'var(--red)', fontSize: 11, gridColumn: '2/-1' }}>At least 3 characters required.</span>
          )}
        </div>

        {submitError && (
          <div className="section error-card" style={{ padding: 12 }}>
            <p style={{ margin: 0, color: 'var(--red)', fontSize: 12 }}>{submitError}</p>
          </div>
        )}
      </div>
    );
  };

  // ---- main render ---------------------------------------------------------

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <div className="row between">
        <h1 style={{ margin: 0 }}>New Agent</h1>
        <button className="link-btn" onClick={() => navigate('/agents')}>
          ← back to agents
        </button>
      </div>

      {renderStepIndicator()}

      <div className="section">
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}
        {step === 4 && renderStep4()}
        {step === 5 && renderStep5()}
      </div>

      <div className="row between">
        <button onClick={goPrev} disabled={step === 1 || submitting}>
          ← back
        </button>

        <div className="row" style={{ gap: 8 }}>
          {step < 5 ? (
            <button
              className="primary"
              onClick={goNext}
              disabled={!canProceed()}
            >
              next →
            </button>
          ) : (
            <button
              className="primary"
              onClick={handleSubmit}
              disabled={submitting || !author || changelog.length < 3}
            >
              {submitting ? 'creating…' : 'create agent'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
