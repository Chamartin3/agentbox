import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { repoApi, type RepoResource, type RepoType, type RepoVersion } from '../api/repo';
import Toast from './Toast';

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

interface PreviewResult {
  rendered_prompt: string;
  unresolved_markers: string[];
  warnings: string[];
  references: PreviewRef[];
  input_schema: PreviewSchema | null;
  output_schema: PreviewSchema | null;
  raw_text_output: boolean;
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

interface ResourcePickerProps {
  filterType?: RepoType | null;
  onPick: (r: RepoResource) => void;
  onClose: () => void;
}

function ResourcePicker({ filterType, onPick, onClose }: ResourcePickerProps) {
  const [items, setItems] = useState<RepoResource[]>([]);
  const [q, setQ] = useState('');
  const [type, setType] = useState<RepoType | ''>(filterType ?? '');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    repoApi
      .list({ q: q || undefined, type: (type as RepoType) || undefined, limit: 50 })
      .then((p) => { if (!cancelled) setItems(p.items); })
      .catch((e) => { if (!cancelled) { setItems([]); setErr(errMsg(e, 'failed to load resources')); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [q, type]);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg, #1a1a1a)', padding: 16, borderRadius: 6,
          width: 'min(720px, 90vw)', maxHeight: '80vh', overflow: 'auto',
          border: '1px solid var(--border, #333)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>
            {filterType ? `Pick ${filterType}` : 'Add resource'}
          </h3>
          <button onClick={onClose}>close</button>
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 8 }}>
          <input
            placeholder="search slug or name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, padding: '6px 10px' }}
            autoFocus
          />
          {!filterType && (
            <select value={type} onChange={(e) => setType(e.target.value as RepoType | '')} style={{ padding: '6px 10px' }}>
              <option value="">all types</option>
              <option value="document">document</option>
              <option value="folder">folder</option>
              <option value="skill">skill</option>
              <option value="schema">schema</option>
            </select>
          )}
        </div>
        {err && <p style={{ color: 'crimson', fontSize: 12 }}>{err}</p>}
        {loading ? (
          <p className="dim">loading…</p>
        ) : items.length === 0 ? (
          <p className="dim">no resources match</p>
        ) : (
          <table style={{ fontSize: 12, width: '100%' }}>
            <thead><tr><th>Slug</th><th>Type</th><th>Name</th><th></th></tr></thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td><code>{r.slug}</code></td>
                  <td><span className="tag">{r.type}</span></td>
                  <td>{r.display_name}</td>
                  <td><button onClick={() => onPick(r)}>add</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
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
}

export default function AgentResourcesEditor({ agentId, promptTemplate, onPreview }: Props) {
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<{ kind: 'binding' | 'input_schema' | 'output_schema' } | null>(null);
  const [versionsCache, setVersionsCache] = useState<Record<string, RepoVersion[]>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);

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
        marker: b.slot ? null : (b.marker ?? defaultMarkerFor(b.resource_type)),
        mode: b.slot ? null : (b.mode ?? defaultModeFor(b.resource_type)),
        slot: b.slot ?? null,
        attach_as_reference: b.attach_as_reference,
        pinned_version_id: b.pinned_version_id ?? null,
        required: b.required,
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

  const onPickBinding = (r: RepoResource) => {
    const newB: Binding = {
      resource_id: r.id,
      resource_slug: r.slug,
      resource_type: r.type,
      resource_display_name: r.display_name,
      marker: defaultMarkerFor(r.type),
      mode: defaultModeFor(r.type),
      slot: null,
      attach_as_reference: r.type === 'document' || r.type === 'folder',
      pinned_version_id: null,
      required: true,
      display_order: bindings.length,
      active_version_id: r.active_version_id ?? null,
    };
    setBindings((bs) => [...bs, newB]);
    setPicker(null);
    setDirty(true);
  };

  const onPickSchema = (slot: SchemaSlot) => (r: RepoResource) => {
    // Drop any existing row for this slot first.
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
        attach_as_reference: false,
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

  const reasonInvalid = reason.trim().length < 3;

  const save = async () => {
    if (reasonInvalid) {
      setToast({ kind: 'error', msg: 'reason is required (min 3 chars)' });
      return;
    }
    setBusy(true);
    try {
      const body = {
        bindings: bindings.map((b, i) => ({
          resource_id: b.resource_id,
          marker: b.slot ? null : (b.marker ?? defaultMarkerFor(b.resource_type)),
          mode: b.slot ? null : (b.mode ?? defaultModeFor(b.resource_type)),
          slot: b.slot ?? null,
          attach_as_reference: b.attach_as_reference,
          pinned_version_id: b.pinned_version_id ?? null,
          required: b.required,
          display_order: i,
        })),
        reason: reason.trim(),
      };
      await req(`/api/agents/${encodeURIComponent(agentId)}/prompt-resources`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      setReason('');
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
    <section className="form-panel">
      <div className="row between" style={{ marginBottom: 8 }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 2 }}>Resource bindings</h3>
          <p className="dim" style={{ fontSize: 12, margin: 0 }}>
            Resources spliced into the system prompt and optionally
            attached as references. Toggle "Reference" to also append
            a resource into the composed prompt's References section.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button onClick={() => setPicker({ kind: 'binding' })}>+ add resource</button>
        </div>
      </div>

      {markerBindings.length === 0 ? (
        <p className="dim">No bindings yet. Click "+ add resource" to attach one.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: 56 }}>order</th>
              <th>resource</th>
              <th>marker</th>
              <th>mode</th>
              <th>reference</th>
              <th>version</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {markerBindings.map((b) => {
              const idx = bindings.indexOf(b);
              const versions = versionsCache[b.resource_id] || [];
              const refDisabled = b.resource_type === 'skill' || b.resource_type === 'schema' || b.resource_type === 'script';
              return (
                <tr key={b.id ?? `new-${idx}`}>
                  <td>
                    <div className="row" style={{ gap: 2 }}>
                      <button onClick={() => moveBinding(idx, -1)} style={{ padding: '0 6px' }}>↑</button>
                      <button onClick={() => moveBinding(idx, 1)} style={{ padding: '0 6px' }}>↓</button>
                    </div>
                  </td>
                  <td>
                    <Link to={`/workspaces/resources/${encodeURIComponent(b.resource_id)}`}>
                      <code>{b.resource_slug || b.resource_id.slice(0, 12)}</code>
                    </Link>
                    {b.resource_type && (
                      <span className="tag" style={{ marginLeft: 4 }}>{b.resource_type}</span>
                    )}
                  </td>
                  <td>
                    <input
                      value={b.marker ?? ''}
                      onChange={(e) => updateAt(idx, { marker: e.target.value })}
                      style={{ width: 120, padding: '2px 6px', fontFamily: 'monospace', fontSize: 12 }}
                    />
                  </td>
                  <td>
                    <select
                      value={b.mode ?? defaultModeFor(b.resource_type)}
                      onChange={(e) => updateAt(idx, { mode: e.target.value as PromptMode })}
                    >
                      {b.resource_type === 'document' && <option value="inline">inline</option>}
                      {b.resource_type === 'folder' && <option value="manifest">manifest</option>}
                      {b.resource_type === 'skill' && (
                        <>
                          <option value="skill_primer">skill_primer</option>
                          <option value="name_only">name_only</option>
                        </>
                      )}
                      {!b.resource_type && <option value="inline">inline</option>}
                    </select>
                  </td>
                  <td>
                    <label className="row" style={{ gap: 4 }} title={refDisabled ? `not applicable for ${b.resource_type}` : ''}>
                      <input
                        type="checkbox"
                        disabled={refDisabled}
                        checked={b.attach_as_reference}
                        onChange={(e) => updateAt(idx, { attach_as_reference: e.target.checked })}
                      />
                      <span className="dim" style={{ fontSize: 11 }}>attach</span>
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
                  <td>
                    <button onClick={() => removeAt(idx)} style={{ color: 'crimson' }}>remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: 4 }}>Schema slots <span className="dim" style={{ fontSize: 11, fontWeight: 400 }}>· optional</span></h3>
        <p className="dim" style={{ fontSize: 12, marginTop: 0 }}>
          Both schemas are optional. When no output schema is set, the agent's output is treated as raw text.
        </p>
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: 140 }}>slot</th>
              <th>resource</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(['input_schema', 'output_schema'] as SchemaSlot[]).map((slot) => {
              const b = slot === 'input_schema' ? inputSchema : outputSchema;
              return (
                <tr key={slot}>
                  <td><strong>{slot === 'input_schema' ? 'Input schema' : 'Output schema'}</strong></td>
                  <td>
                    {b ? (
                      <>
                        <Link to={`/workspaces/resources/${encodeURIComponent(b.resource_id)}`}>
                          <code>{b.resource_slug || b.resource_id.slice(0, 12)}</code>
                        </Link>
                        {b.resource_type && (
                          <span className="tag" style={{ marginLeft: 4 }}>{b.resource_type}</span>
                        )}
                      </>
                    ) : (
                      <span className="dim">— none —</span>
                    )}
                  </td>
                  <td>
                    {b ? (
                      <button onClick={() => removeSlot(slot)} style={{ color: 'crimson' }}>remove</button>
                    ) : (
                      <button onClick={() => setPicker({ kind: slot })}>+ set</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {dirty && (
        <div style={{ marginTop: 12 }}>
          <label style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
            Reason for change <span className="dim">(required, min 3 chars)</span>
          </label>
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <input
              placeholder="why are you changing these bindings?"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              style={{
                flex: 1,
                padding: '6px 10px',
                borderColor: reasonInvalid ? 'var(--error, #b91c1c)' : undefined,
              }}
            />
            <button onClick={save} disabled={busy || reasonInvalid} className="primary">
              {busy ? 'saving…' : 'Save'}
            </button>
            <button onClick={refresh} disabled={busy}>discard</button>
          </div>
        </div>
      )}

      {preview && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ marginTop: 0, marginBottom: 4 }}>
            Live composed prompt
            {preview.raw_text_output && (
              <span className="tag" style={{ marginLeft: 8 }}>raw-text output</span>
            )}
          </h3>
          {preview.warnings.length > 0 && (
            <ul className="dim" style={{ fontSize: 11, marginTop: 4 }}>
              {preview.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          <pre
            style={{
              background: 'var(--bg-soft, #111)', padding: 10, borderRadius: 4,
              fontSize: 11, maxHeight: 400, overflow: 'auto',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            }}
          >
            {preview.rendered_prompt}
          </pre>
        </div>
      )}

      {picker?.kind === 'binding' && (
        <ResourcePicker onPick={onPickBinding} onClose={() => setPicker(null)} />
      )}
      {picker?.kind === 'input_schema' && (
        <ResourcePicker filterType="schema" onPick={onPickSchema('input_schema')} onClose={() => setPicker(null)} />
      )}
      {picker?.kind === 'output_schema' && (
        <ResourcePicker filterType="schema" onPick={onPickSchema('output_schema')} onClose={() => setPicker(null)} />
      )}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </section>
  );
}
