import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { repoApi, type RepoResource, type RepoType, type RepoVersion } from '../api/repo';
import ResourcePicker from './ResourcePicker';
import Toast from './Toast';
import LiveComposedPromptPreview from './LiveComposedPromptPreview';

type PromptMode = 'inline' | 'skill_primer' | 'name_only' | 'manifest';
type SchemaSlot = 'input_schema' | 'output_schema';

interface Binding {
  id?: string;
  resource_id: string;
  resource_slug?: string | null;
  resource_type?: RepoType | null;
  resource_display_name?: string | null;
  marker?: string | null;
  mode?: PromptMode | null;
  slot?: SchemaSlot | null;
  attach_as_reference: boolean;
  pinned_version_id?: string | null;
  required: boolean;
  display_order: number;
  active_version_id?: string | null;
}

interface PreviewRef {
  binding_id: string;
  resource_id: string;
  display_name?: string | null;
}

interface PreviewSchema {
  binding_id: string;
  resource_id: string;
  display_name?: string | null;
  content_hash: string;
  text: string;
}

interface CharPart {
  label: string;
  chars: number;
}

interface PreviewResult {
  rendered_prompt: string;
  unresolved_markers: string[];
  warnings: string[];
  references: PreviewRef[];
  input_schema: PreviewSchema | null;
  output_schema: PreviewSchema | null;
  raw_text_output: boolean;
  char_breakdown?: CharPart[];
  total_chars?: number;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail: unknown;
    try { detail = await resp.clone().json(); } catch { detail = await resp.text(); }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: string } | string | undefined;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.detail === 'string') return d.detail;
    return `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}


function defaultModeFor(type: RepoType | null | undefined): PromptMode {
  if (type === 'skill') return 'skill_primer';
  if (type === 'folder') return 'manifest';
  return 'inline';
}

function defaultMarkerFor(type: RepoType | null | undefined): string {
  if (type === 'skill') return 'skills';
  if (type === 'folder') return 'folders';
  return 'documents';
}

interface Props {
  agentId: string;
  promptTemplate: string;
  onPreview?: (result: PreviewResult | null) => void;
  outputValidation?: string;
  onChangeOutputValidation?: (next: string) => void;
  hideInlinePreview?: boolean;
}

export default function AgentResourcesEditor({
  agentId,
  promptTemplate,
  onPreview,
  outputValidation,
  onChangeOutputValidation,
  hideInlinePreview,
}: Props) {
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<{ kind: 'binding' | 'input_schema' | 'output_schema' } | null>(null);
  const [versionsCache, setVersionsCache] = useState<Record<string, RepoVersion[]>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);
  const [splicingId, setSplicingId] = useState<string | null>(null);
  const [nameDrafts, setNameDrafts] = useState<Record<string, string>>({});
  const [savingName, setSavingName] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await req<{ items: Binding[] }>(
        `/api/agents/${encodeURIComponent(agentId)}/prompt-resources`,
      );
      const items = (data.items || []).map((b) => ({
        ...b,
        attach_as_reference: !!b.attach_as_reference,
        required: b.required ?? true,
      }));
      setBindings(items);
      setDirty(false);
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to load bindings') });
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => { refresh(); }, [refresh]);

  // Lazy-load versions for pin dropdown.
  useEffect(() => {
    const missing = bindings
      .map((b) => b.resource_id)
      .filter((id, i, arr) => arr.indexOf(id) === i && !(id in versionsCache));
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map(async (id) => {
        try {
          const v = await repoApi.versions(id);
          return [id, v.items] as const;
        } catch {
          return [id, [] as RepoVersion[]] as const;
        }
      }),
    ).then((pairs) => {
      if (cancelled) return;
      setVersionsCache((prev) => {
        const next = { ...prev };
        for (const [id, items] of pairs) next[id] = items;
        return next;
      });
    });
    return () => { cancelled = true; };
  }, [bindings, versionsCache]);

  // Live preview: re-fetch on edits with debounce.
  useEffect(() => {
    const body = {
      template: promptTemplate,
      bindings: bindings.map((b) => ({
        resource_id: b.resource_id,
        marker: b.slot ? null : (b.marker || null),
        mode: b.slot ? null : (b.marker ? (b.mode ?? defaultModeFor(b.resource_type)) : (b.resource_type === 'skill' ? (b.mode ?? null) : null)),
        slot: b.slot ?? null,
        attach_as_reference: b.attach_as_reference,
        pinned_version_id: b.pinned_version_id ?? null,
        required: b.slot || !b.marker ? false : b.required,
        display_order: b.display_order,
      })),
    };
    const handle = setTimeout(async () => {
      try {
        const r = await req<PreviewResult>(
          `/api/agents/${encodeURIComponent(agentId)}/prompt-resources/preview`,
          { method: 'POST', body: JSON.stringify(body) },
        );
        setPreview(r);
        onPreview?.(r);
      } catch (e) {
        console.error('preview failed', e);
        setToast({ kind: 'error', msg: errMsg(e, 'preview failed') });
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [agentId, promptTemplate, bindings, onPreview]);

  const markerBindings = useMemo(
    () => bindings.filter((b) => !b.slot),
    [bindings],
  );
  const inputSchema = useMemo(
    () => bindings.find((b) => b.slot === 'input_schema') ?? null,
    [bindings],
  );
  const outputSchema = useMemo(
    () => bindings.find((b) => b.slot === 'output_schema') ?? null,
    [bindings],
  );

  const updateAt = (idx: number, patch: Partial<Binding>) => {
    setBindings((bs) => bs.map((b, i) => (i === idx ? { ...b, ...patch } : b)));
    setDirty(true);
  };

  const removeAt = (idx: number) => {
    setBindings((bs) => bs.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const removeSlot = (slot: SchemaSlot) => {
    setBindings((bs) => bs.filter((b) => b.slot !== slot));
    setDirty(true);
  };

  const moveBinding = (idx: number, dir: -1 | 1) => {
    setBindings((bs) => {
      const next = [...bs];
      const swap = idx + dir;
      if (swap < 0 || swap >= next.length) return bs;
      [next[idx], next[swap]] = [next[swap], next[idx]];
      return next.map((b, i) => ({ ...b, display_order: i }));
    });
    setDirty(true);
  };

  const onPickBinding = (rs: RepoResource[]) => {
    setBindings((bs) => {
      const newRows: Binding[] = rs.map((r, i) => ({
        resource_id: r.id,
        resource_slug: r.slug,
        resource_type: r.type,
        resource_display_name: r.display_name,
        marker: null,
        mode: r.type === 'skill' ? defaultModeFor(r.type) : null,
        slot: null,
        attach_as_reference: r.type === 'document' || r.type === 'folder',
        pinned_version_id: null,
        required: true,
        display_order: bs.length + i,
        active_version_id: r.active_version_id ?? null,
      }));
      return [...bs, ...newRows];
    });
    setPicker(null);
    setDirty(true);
  };

  const saveDisplayName = async (b: Binding) => {
    const key = b.id ?? b.resource_id;
    const draft = (nameDrafts[key] ?? b.resource_display_name ?? '').trim();
    if (!draft || draft === (b.resource_display_name ?? '')) {
      setNameDrafts((d) => {
        const next = { ...d };
        delete next[key];
        return next;
      });
      return;
    }
    setSavingName(key);
    try {
      const updated = await repoApi.update(b.resource_id, { display_name: draft });
      setBindings((bs) =>
        bs.map((row) =>
          row.resource_id === b.resource_id
            ? { ...row, resource_display_name: updated.display_name }
            : row,
        ),
      );
      setNameDrafts((d) => {
        const next = { ...d };
        delete next[key];
        return next;
      });
      setToast({ kind: 'ok', msg: 'name updated' });
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to rename resource') });
    } finally {
      setSavingName(null);
    }
  };

  const onPickSchema = (slot: SchemaSlot) => (rs: RepoResource[]) => {
    const r = rs[0];
    if (!r) return;
    setBindings((bs) => {
      const filtered = bs.filter((b) => b.slot !== slot);
      const newB: Binding = {
        resource_id: r.id,
        resource_slug: r.slug,
        resource_type: r.type,
        resource_display_name: r.display_name,
        marker: null,
        mode: null,
        slot,
        attach_as_reference: true,
        pinned_version_id: null,
        required: false,
        display_order: filtered.length,
        active_version_id: r.active_version_id ?? null,
      };
      return [...filtered, newB];
    });
    setPicker(null);
    setDirty(true);
  };

  const attachedIds = useMemo(
    () => new Set(bindings.filter((b) => !b.slot).map((b) => b.resource_id)),
    [bindings],
  );

  const save = async () => {
    setBusy(true);
    try {
      const body = {
        bindings: bindings.map((b, i) => ({
          resource_id: b.resource_id,
          marker: b.slot ? null : (b.marker || null),
          mode: b.slot ? null : (b.marker ? (b.mode ?? defaultModeFor(b.resource_type)) : (b.resource_type === 'skill' ? (b.mode ?? null) : null)),
          slot: b.slot ?? null,
          attach_as_reference: b.attach_as_reference,
          pinned_version_id: b.pinned_version_id ?? null,
          required: b.slot || !b.marker ? false : b.required,
          display_order: i,
        })),
        reason: 'ui edit',
      };
      await req(`/api/agents/${encodeURIComponent(agentId)}/prompt-resources`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      setToast({ kind: 'ok', msg: 'bindings saved' });
      await refresh();
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to save bindings') });
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className="dim">loading agent resources…</p>;

  return (
    <section className="composition-section">
      <div className="composition-section-header">
        <h3>Resource bindings</h3>
        <div className="composition-section-meta">
          <button onClick={() => setPicker({ kind: 'binding' })} style={{ fontSize: 11, padding: '4px 10px' }}>
            + add resource
          </button>
        </div>
      </div>
      <p className="composition-section-subtitle">
        Schemas (input/output) and reference documents attached to the composed prompt. Use the row menu for advanced options.
      </p>

      {markerBindings.length === 0 ? (
        <p className="dim">No bindings yet. Click "+ add resource" to attach one.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: 56 }}>↕</th>
              <th>name</th>
              <th style={{ width: 90 }}>type</th>
              <th style={{ width: 80 }}>active</th>
              <th style={{ width: 140 }}>version</th>
              <th style={{ width: 40 }}></th>
            </tr>
          </thead>
          <tbody>
            {markerBindings.map((b) => {
              const idx = bindings.indexOf(b);
              const versions = versionsCache[b.resource_id] || [];
              const rowKey = b.id ?? `new-${idx}`;
              const nameKey = b.id ?? b.resource_id;
              const refDisabled = b.resource_type === 'skill' || b.resource_type === 'schema' || b.resource_type === 'script';
              // ref_* markers were assigned by the legacy/migration importer
              // for reference-only bindings — they should not surface splice UI.
              const isLegacyRef = !!b.marker && /^ref_/.test(b.marker);
              const isSplice = !!b.marker && !isLegacyRef;
              const isActive = b.attach_as_reference || isSplice;
              const draft = nameDrafts[nameKey];
              const nameValue = draft !== undefined ? draft : (b.resource_display_name ?? '');
              const menuShown = menuOpen === rowKey;
              const splicing = splicingId === rowKey;
              return (
                <Fragment key={rowKey}>
                  <tr>
                    <td>
                      <div className="row" style={{ gap: 2 }}>
                        <button onClick={() => moveBinding(idx, -1)} style={{ padding: '0 6px' }}>↑</button>
                        <button onClick={() => moveBinding(idx, 1)} style={{ padding: '0 6px' }}>↓</button>
                      </div>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 4, alignItems: 'center' }}>
                        <input
                          value={nameValue}
                          placeholder={b.resource_slug || ''}
                          onChange={(e) =>
                            setNameDrafts((d) => ({ ...d, [nameKey]: e.target.value }))
                          }
                          onBlur={() => {
                            if (draft !== undefined) saveDisplayName(b);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                            if (e.key === 'Escape') {
                              setNameDrafts((d) => {
                                const next = { ...d };
                                delete next[nameKey];
                                return next;
                              });
                            }
                          }}
                          disabled={savingName === nameKey}
                          style={{ flex: 1, padding: '2px 6px', fontSize: 12 }}
                        />
                        {isSplice && (
                          <span
                            className="tag"
                            title={`spliced via {{resource:${b.marker}}}`}
                            style={{ fontSize: 10 }}
                          >
                            splice
                          </span>
                        )}
                      </div>
                      <div className="dim" style={{ fontSize: 10, marginTop: 2 }}>
                        <Link to={`/workspaces/resources/${encodeURIComponent(b.resource_id)}`}>
                          <code>{b.resource_slug || b.resource_id.slice(0, 12)}</code>
                        </Link>
                      </div>
                    </td>
                    <td>
                      {b.resource_type && (
                        <span className="tag">{b.resource_type}</span>
                      )}
                    </td>
                    <td>
                      <label className="row" style={{ gap: 4 }} title={refDisabled && !isSplice ? `not applicable for ${b.resource_type}` : ''}>
                        <input
                          type="checkbox"
                          disabled={refDisabled && !isSplice}
                          checked={isActive}
                          onChange={(e) => {
                            const next = e.target.checked;
                            if (isSplice) {
                              // splice rows: turning off clears the marker
                              updateAt(idx, next
                                ? { attach_as_reference: !refDisabled }
                                : { marker: null, mode: b.resource_type === 'skill' ? b.mode : null, attach_as_reference: false });
                            } else {
                              updateAt(idx, { attach_as_reference: next });
                            }
                          }}
                        />
                      </label>
                    </td>
                    <td>
                      <select
                        value={b.pinned_version_id ?? ''}
                        onChange={(e) => updateAt(idx, { pinned_version_id: e.target.value || null })}
                      >
                        <option value="">active</option>
                        {versions.map((v) => (
                          <option key={v.id} value={v.id}>
                            v{v.version_number}{v.is_draft ? ' (draft)' : ''}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td style={{ position: 'relative' }}>
                      <button
                        onClick={() => setMenuOpen(menuShown ? null : rowKey)}
                        style={{ padding: '2px 8px' }}
                        title="more options"
                      >⋮</button>
                      {menuShown && (
                        <div
                          style={{
                            position: 'absolute', right: 0, top: '100%', zIndex: 10,
                            background: 'var(--bg, #1a1a1a)', border: '1px solid var(--border, #333)',
                            borderRadius: 4, padding: 4, minWidth: 180, fontSize: 12,
                            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                          }}
                        >
                          <button
                            onClick={() => {
                              setSplicingId(splicing ? null : rowKey);
                              setMenuOpen(null);
                              if (!isSplice && !splicing) {
                                updateAt(idx, {
                                  marker: defaultMarkerFor(b.resource_type),
                                  mode: defaultModeFor(b.resource_type),
                                });
                              }
                            }}
                            style={{ display: 'block', width: '100%', textAlign: 'left', padding: '4px 8px', background: 'none', border: 'none', cursor: 'pointer' }}
                          >
                            {isSplice ? 'Edit splice marker…' : 'Splice into template…'}
                          </button>
                          {b.resource_type === 'skill' && (
                            <div style={{ padding: '4px 8px' }}>
                              <div className="dim" style={{ fontSize: 10, marginBottom: 2 }}>skill render mode</div>
                              <select
                                value={b.mode ?? 'skill_primer'}
                                onChange={(e) => updateAt(idx, { mode: e.target.value as PromptMode })}
                                style={{ width: '100%' }}
                              >
                                <option value="skill_primer">skill_primer</option>
                                <option value="name_only">name_only</option>
                              </select>
                            </div>
                          )}
                          <button
                            onClick={() => { setMenuOpen(null); removeAt(idx); }}
                            style={{ display: 'block', width: '100%', textAlign: 'left', padding: '4px 8px', background: 'none', border: 'none', color: 'crimson', cursor: 'pointer' }}
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  {(splicing || isSplice) && (
                    <tr>
                      <td></td>
                      <td colSpan={5} style={{ paddingTop: 0 }}>
                        <div className="row" style={{ gap: 6, alignItems: 'center', fontSize: 11 }}>
                          <span className="dim">splice marker:</span>
                          <code style={{ fontSize: 11 }}>{'{{resource:'}</code>
                          <input
                            value={b.marker ?? ''}
                            placeholder={defaultMarkerFor(b.resource_type)}
                            onChange={(e) => updateAt(idx, { marker: e.target.value || null })}
                            style={{ width: 140, padding: '2px 6px', fontFamily: 'monospace', fontSize: 11 }}
                          />
                          <code style={{ fontSize: 11 }}>{'}}'}</code>
                          {b.marker && !promptTemplate.includes(`{{resource:${b.marker}}}`) && (
                            <span style={{ color: 'orange', fontSize: 11 }}>
                              ⚠ marker not found in prompt template
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: 16 }}>
        <div className="dim" style={{ fontSize: 11, marginBottom: 6 }}>
          Schema slots · optional · when no output schema is set the agent's
          output is treated as raw text
        </div>
        <table style={{ fontSize: 12, width: '100%' }}>
          <tbody>
            {(['input_schema', 'output_schema'] as SchemaSlot[]).map((slot) => {
              const b = slot === 'input_schema' ? inputSchema : outputSchema;
              const isOutput = slot === 'output_schema';
              const slotIdx = b ? bindings.indexOf(b) : -1;
              return (
                <tr key={slot}>
                  <td style={{ width: 140, padding: '3px 6px' }}>
                    <strong>{slot === 'input_schema' ? 'Input schema' : 'Output schema'}</strong>
                  </td>
                  <td style={{ padding: '3px 6px' }}>
                    {b ? (
                      <Link to={`/workspaces/resources/${encodeURIComponent(b.resource_id)}`}>
                        {b.resource_display_name || b.resource_slug || b.resource_id.slice(0, 12)}
                      </Link>
                    ) : (
                      <span className="dim">— none —</span>
                    )}
                  </td>
                  <td style={{ padding: '3px 6px', width: 70 }}>
                    {b && (
                      <label
                        className="row"
                        style={{ gap: 4, fontSize: 11, alignItems: 'center' }}
                        title="When unchecked, the schema is kept on the agent but not rendered into the composed prompt"
                      >
                        <input
                          type="checkbox"
                          checked={b.attach_as_reference}
                          onChange={(e) =>
                            updateAt(slotIdx, { attach_as_reference: e.target.checked })
                          }
                        />
                        <span className="dim">active</span>
                      </label>
                    )}
                  </td>
                  <td style={{ padding: '3px 6px' }}>
                    {isOutput && onChangeOutputValidation && (
                      <div className="row" style={{ gap: 4, alignItems: 'center', fontSize: 11 }}>
                        <span className="dim">validation:</span>
                        <select
                          value={outputValidation || 'strict'}
                          onChange={(e) => onChangeOutputValidation(e.target.value)}
                          style={{ fontSize: 11, padding: '1px 4px' }}
                          title="How the executor responds when output does not match the schema"
                        >
                          <option value="strict">strict</option>
                          <option value="warn">warn</option>
                          <option value="off">off</option>
                        </select>
                      </div>
                    )}
                  </td>
                  <td style={{ width: 1, padding: '3px 6px', whiteSpace: 'nowrap' }}>
                    {b ? (
                      <button onClick={() => removeSlot(slot)} style={{ color: 'crimson', fontSize: 11 }}>remove</button>
                    ) : (
                      <button onClick={() => setPicker({ kind: slot })} style={{ fontSize: 11 }}>+ set / upload</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {dirty && (
        <div className="row" style={{ marginTop: 12, gap: 8, alignItems: 'center' }}>
          <button onClick={save} disabled={busy} className="primary">
            {busy ? 'saving…' : 'Save'}
          </button>
          <button onClick={refresh} disabled={busy}>discard</button>
        </div>
      )}

      {!hideInlinePreview && preview && <LiveComposedPromptPreview preview={preview} />}

      {picker?.kind === 'binding' && (
        <ResourcePicker
          excludeIds={attachedIds}
          allowUpload
          onPick={onPickBinding}
          onClose={() => setPicker(null)}
        />
      )}
      {picker?.kind === 'input_schema' && (
        <ResourcePicker
          filterType="schema"
          allowUpload
          title="Pick or upload input schema"
          onPick={onPickSchema('input_schema')}
          onClose={() => setPicker(null)}
        />
      )}
      {picker?.kind === 'output_schema' && (
        <ResourcePicker
          filterType="schema"
          allowUpload
          title="Pick or upload output schema"
          onPick={onPickSchema('output_schema')}
          onClose={() => setPicker(null)}
        />
      )}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </section>
  );
}
