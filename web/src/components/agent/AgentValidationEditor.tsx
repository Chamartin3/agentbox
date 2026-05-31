import { useCallback, useEffect, useState } from 'react';
import {
  ApiError,
  api,
  type AgentValidationView,
  type Validator,
} from '../../api/client';

type Direction = 'input' | 'output';

interface HttpValidatorLike {
  kind: 'http';
  endpoint?: string;
  timeout_seconds?: number;
  description?: string;
}
interface ScriptValidatorLike {
  kind: 'script';
  resource_id?: string;
  pinned_version_id?: string | null;
  description?: string;
}

function errMsg(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === 'string') return err.detail;
    return JSON.stringify(err.detail);
  }
  return (err as Error).message || String(err);
}

function validatorConfigSummary(v: Validator): string {
  if (v.kind === 'http') {
    const h = v as HttpValidatorLike;
    const t = h.timeout_seconds ? ` · ${h.timeout_seconds}s` : '';
    return `${h.endpoint || '—'}${t}`;
  }
  if (v.kind === 'script') {
    const s = v as ScriptValidatorLike;
    const p = s.pinned_version_id ? ` @ ${s.pinned_version_id}` : '';
    return `${s.resource_id || '—'}${p}`;
  }
  return JSON.stringify(v);
}

function validatorDescription(v: Validator): string {
  const d = (v as HttpValidatorLike | ScriptValidatorLike).description;
  return typeof d === 'string' ? d : '';
}

function newValidator(kind: 'http' | 'script'): Validator {
  if (kind === 'http')
    return { kind: 'http', endpoint: '', timeout_seconds: 5, description: '' } as Validator;
  return { kind: 'script', resource_id: '', description: '' } as Validator;
}

// ---------- per-row inline editor -----------------------------------------

function ValidatorRowEditor({
  draft,
  onChange,
}: {
  draft: Validator;
  onChange: (next: Validator) => void;
}) {
  const desc = validatorDescription(draft);
  const descBox = (
    <textarea
      value={desc}
      placeholder="Constraint (e.g. Sum must be > 100) — rendered into the system prompt"
      onChange={(e) =>
        onChange({ ...(draft as object), description: e.target.value } as Validator)
      }
      rows={2}
      style={{ width: '100%', fontSize: 12, resize: 'vertical' }}
    />
  );

  if (draft.kind === 'http') {
    const h = draft as HttpValidatorLike;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        {descBox}
        <div className="row" style={{ gap: 6, alignItems: 'center' }}>
          <input
            type="text"
            value={h.endpoint || ''}
            placeholder="https://example.com/validate"
            onChange={(e) =>
              onChange({ ...draft, kind: 'http', endpoint: e.target.value })
            }
            style={{ flex: 1, fontSize: 12 }}
          />
          <input
            type="number"
            min={1}
            max={300}
            value={h.timeout_seconds ?? 5}
            onChange={(e) =>
              onChange({ ...draft, kind: 'http', timeout_seconds: Number(e.target.value) || 1 })
            }
            style={{ width: 64, fontSize: 12 }}
            title="timeout (seconds)"
          />
        </div>
      </div>
    );
  }
  if (draft.kind === 'script') {
    const s = draft as ScriptValidatorLike;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
        {descBox}
        <div className="row" style={{ gap: 6, alignItems: 'center' }}>
          <input
            type="text"
            value={s.resource_id || ''}
            placeholder="resource_id"
            onChange={(e) =>
              onChange({ ...draft, kind: 'script', resource_id: e.target.value })
            }
            style={{ flex: 1, fontSize: 12 }}
          />
          <input
            type="text"
            value={s.pinned_version_id || ''}
            placeholder="pinned_version_id (optional)"
            onChange={(e) =>
              onChange({ ...draft, kind: 'script', pinned_version_id: e.target.value || null })
            }
            style={{ width: 200, fontSize: 12 }}
          />
        </div>
      </div>
    );
  }
  return <code style={{ flex: 1, fontSize: 11 }}>{JSON.stringify(draft)}</code>;
}

// ---------- direction section ---------------------------------------------

function DirectionSection({
  direction,
  validators,
  hasOutputSchema,
  busy,
  onSaveValidators,
}: {
  direction: Direction;
  validators: Validator[];
  hasOutputSchema: boolean;
  busy: boolean;
  onSaveValidators: (next: Validator[]) => Promise<void>;
}) {
  const showSchemaRow = direction === 'output' && hasOutputSchema;
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<Validator | null>(null);
  const [adding, setAdding] = useState<'http' | 'script' | null>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const cancelEdit = () => {
    setEditingIndex(null);
    setDraft(null);
    setAdding(null);
    setErr(null);
  };
  const beginEdit = (i: number) => {
    setAdding(null);
    setEditingIndex(i);
    setDraft({ ...validators[i] });
    setErr(null);
  };
  const beginAdd = (kind: 'http' | 'script') => {
    setEditingIndex(null);
    setAdding(kind);
    setDraft(newValidator(kind));
    setAddMenuOpen(false);
    setErr(null);
  };
  const saveRow = async () => {
    if (!draft) return;
    setSaving(true);
    setErr(null);
    try {
      let next: Validator[];
      if (adding) next = [...validators, draft];
      else if (editingIndex != null) {
        next = validators.slice();
        next[editingIndex] = draft;
      } else return;
      await onSaveValidators(next);
      cancelEdit();
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setSaving(false);
    }
  };
  const deleteRow = async (i: number) => {
    setSaving(true);
    setErr(null);
    try {
      const next = validators.slice();
      next.splice(i, 1);
      await onSaveValidators(next);
    } catch (e) {
      setErr(errMsg(e));
    } finally {
      setSaving(false);
    }
  };

  const totalRows = (showSchemaRow ? 1 : 0) + validators.length + (adding ? 1 : 0);
  const isEmpty = validators.length === 0 && !adding;

  return (
    <div className="code-block" style={{ marginBottom: 8 }}>
      <div
        className="code-block-bar row between"
        style={{ alignItems: 'center', gap: 8, flexWrap: 'wrap' }}
      >
        <div className="row" style={{ gap: 8, alignItems: 'baseline' }}>
          <strong>{direction === 'output' ? 'Output' : 'Input'} validators</strong>
        </div>
        <div className="row" style={{ gap: 6, alignItems: 'center', position: 'relative' }}>
          <button
            onClick={() => setAddMenuOpen((o) => !o)}
            className="primary"
            style={{ fontSize: 11, padding: '2px 10px' }}
            disabled={busy || saving || adding != null || editingIndex != null}
          >
            + Add validator ▾
          </button>
          {addMenuOpen && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                right: 0,
                marginTop: 4,
                background: 'var(--bg, #1a1a1a)',
                border: '1px solid var(--border, #333)',
                borderRadius: 4,
                boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
                zIndex: 5,
                minWidth: 180,
              }}
            >
              <button
                onClick={() => beginAdd('http')}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  fontSize: 12,
                  padding: '6px 10px',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <span className="pill">http</span> HTTP callback
              </button>
              <button
                onClick={() => beginAdd('script')}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  fontSize: 12,
                  padding: '6px 10px',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <span className="pill">script</span> Script resource
              </button>
            </div>
          )}
        </div>
      </div>

      <div style={{ padding: 10 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ textAlign: 'left', opacity: 0.7 }}>
              <th style={{ padding: '4px 6px', width: 30 }}>#</th>
              <th style={{ padding: '4px 6px', width: 80 }}>Type</th>
              <th style={{ padding: '4px 6px' }}>Constraint</th>
              <th style={{ padding: '4px 6px', width: 220 }}>Config</th>
              <th style={{ padding: '4px 6px', width: 140, textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {showSchemaRow && (
              <tr style={{ borderTop: '1px solid var(--border, #333)' }}>
                <td style={{ padding: '6px 6px' }}>1</td>
                <td style={{ padding: '6px 6px' }}>
                  <span className="pill ok">schema</span>
                </td>
                <td style={{ padding: '6px 6px' }}>
                  Output must conform to the JSON Schema below.
                </td>
                <td style={{ padding: '6px 6px' }} className="dim">
                  from <code>output_schema</code> binding
                </td>
                <td style={{ padding: '6px 6px', textAlign: 'right' }} className="dim">
                  read-only
                </td>
              </tr>
            )}
            {validators.map((v, i) => {
              const rowNum = (showSchemaRow ? 2 : 1) + i;
              const isEditing = editingIndex === i;
              return (
                <tr key={i} style={{ borderTop: '1px solid var(--border, #333)' }}>
                  <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>{rowNum}</td>
                  <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>
                    <span className="pill">{v.kind}</span>
                  </td>
                  {isEditing && draft ? (
                    <td colSpan={2} style={{ padding: '6px 6px' }}>
                      <ValidatorRowEditor draft={draft} onChange={setDraft} />
                    </td>
                  ) : (
                    <>
                      <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>
                        {validatorDescription(v) || (
                          <span className="dim">— no constraint text —</span>
                        )}
                      </td>
                      <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>
                        <code style={{ fontSize: 11 }}>{validatorConfigSummary(v)}</code>
                      </td>
                    </>
                  )}
                  <td style={{ padding: '6px 6px', textAlign: 'right', verticalAlign: 'top' }}>
                    {isEditing ? (
                      <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => void saveRow()}
                          disabled={saving}
                          className="primary"
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          {saving ? 'Saving…' : 'Save'}
                        </button>
                        <button
                          onClick={cancelEdit}
                          disabled={saving}
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                        <button
                          onClick={() => beginEdit(i)}
                          disabled={busy || saving || adding != null || editingIndex != null}
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => void deleteRow(i)}
                          disabled={busy || saving || adding != null || editingIndex != null}
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {adding && draft && (
              <tr
                style={{
                  borderTop: '1px solid var(--border, #333)',
                  background: 'rgba(80,180,120,0.06)',
                }}
              >
                <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>{totalRows}</td>
                <td style={{ padding: '6px 6px', verticalAlign: 'top' }}>
                  <span className="pill">{adding}</span>
                </td>
                <td colSpan={2} style={{ padding: '6px 6px' }}>
                  <ValidatorRowEditor draft={draft} onChange={setDraft} />
                </td>
                <td style={{ padding: '6px 6px', textAlign: 'right', verticalAlign: 'top' }}>
                  <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                    <button
                      onClick={() => void saveRow()}
                      disabled={saving}
                      className="primary"
                      style={{ fontSize: 11, padding: '2px 8px' }}
                    >
                      {saving ? 'Saving…' : 'Add'}
                    </button>
                    <button
                      onClick={cancelEdit}
                      disabled={saving}
                      style={{ fontSize: 11, padding: '2px 8px' }}
                    >
                      Cancel
                    </button>
                  </div>
                </td>
              </tr>
            )}
            {!showSchemaRow && isEmpty && (
              <tr style={{ borderTop: '1px solid var(--border, #333)' }}>
                <td colSpan={5} style={{ padding: '8px 6px' }} className="dim">
                  no validators — use “+ Add validator” to create one
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {err && <p style={{ color: '#c44', fontSize: 12, margin: '6px 0 0' }}>{err}</p>}
      </div>
    </div>
  );
}

// ---------- main panel ----------------------------------------------------

export default function AgentValidationEditor({
  agentId,
  hasOutputSchema = false,
}: {
  agentId: string;
  hasOutputSchema?: boolean;
}) {
  const [view, setView] = useState<AgentValidationView | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [topErr, setTopErr] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setTopErr(null);
    try {
      const v = await api.getAgentValidation(agentId);
      setView(v);
    } catch (e) {
      setTopErr(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const saveValidators = async (direction: Direction, next: Validator[]) => {
    setBusy(true);
    setTopErr(null);
    try {
      await api.setAgentValidation(agentId, {
        [direction]: { validators: next },
        reason: `edit ${direction} validators`,
        actor: 'web',
      } as never);
      await loadAll();
    } catch (e) {
      setTopErr(errMsg(e));
      throw e;
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="composition-section">
      <div className="composition-section-header">
        <h3>Validation</h3>
        <div className="composition-section-meta">
          <span>{view?.agent_version_id ? `v${view.agent_version_id}` : '—'}</span>
          <button
            onClick={() => void loadAll()}
            disabled={loading || busy}
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            Refresh
          </button>
        </div>
      </div>

      {topErr && <p style={{ color: '#c44', fontSize: 12, margin: '0 0 8px' }}>{topErr}</p>}

      {loading && !view ? (
        <p className="dim" style={{ fontSize: 12 }}>
          loading…
        </p>
      ) : (
        (['output', 'input'] as const).map((direction) => (
          <DirectionSection
            key={direction}
            direction={direction}
            validators={view?.[direction]?.validators || []}
            hasOutputSchema={hasOutputSchema}
            busy={busy}
            onSaveValidators={(next) => saveValidators(direction, next)}
          />
        ))
      )}
    </section>
  );
}
