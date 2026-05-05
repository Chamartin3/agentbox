import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { repoApi, RepoResource, RepoType, RepoVersion } from '../api/repo';
import { PromptMode, RepoType as RepoTypeEnum } from '../api/enums';
import Toast from './Toast';

interface Binding {
  id?: string;
  resource_id: string;
  resource_slug?: string;
  resource_type?: string;
  marker: string;
  mode: PromptMode;
  pinned_version_id?: string | null;
  required: boolean;
  display_order: number;
  active_version_id?: string | null;
}

interface PreviewResult {
  rendered_prompt: string;
  unresolved_markers: string[];
  warnings: string[];
}

const MODES: PromptMode[] = [PromptMode.Inline, PromptMode.SkillPrimer, PromptMode.NameOnly, PromptMode.Manifest];
const PICKER_KINDS: Array<RepoType | ''> = ['', RepoTypeEnum.Skill, RepoTypeEnum.Document, RepoTypeEnum.Folder];

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init?.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.clone().json();
    } catch {
      detail = await resp.text();
    }
    throw new Error(
      `HTTP ${resp.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`,
    );
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

function defaultModeForType(t: string | undefined): PromptMode {
  if (t === RepoTypeEnum.Skill) return PromptMode.SkillPrimer;
  if (t === RepoTypeEnum.Folder) return PromptMode.Manifest;
  return PromptMode.Inline;
}

function slugifyMarker(slug: string): string {
  return slug.replace(/[^a-zA-Z0-9_-]+/g, '_').toLowerCase();
}

function errStr(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

interface ResourcePickerProps {
  onPick: (r: RepoResource) => void;
  onClose: () => void;
}

function ResourcePicker({ onPick, onClose }: ResourcePickerProps) {
  const [items, setItems] = useState<RepoResource[]>([]);
  const [q, setQ] = useState('');
  const [kind, setKind] = useState<RepoType | ''>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    repoApi
      .list({ q: q || undefined, type: (kind as RepoType) || undefined, limit: 50 })
      .then((p) => setItems(p.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [q, kind]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg, #1a1a1a)',
          padding: 16,
          borderRadius: 6,
          width: 'min(720px, 90vw)',
          maxHeight: '80vh',
          overflow: 'auto',
          border: '1px solid var(--border, #333)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Pick a resource</h3>
          <button onClick={onClose}>x</button>
        </div>
        <div className="row" style={{ gap: 8, marginBottom: 8 }}>
          <input
            placeholder="search…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ flex: 1, padding: '6px 10px' }}
            autoFocus
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as RepoType | '')}
            style={{ padding: '6px 10px' }}
          >
            {PICKER_KINDS.map((k) => (
              <option key={k || 'all'} value={k}>
                {k || 'all types'}
              </option>
            ))}
          </select>
        </div>
        {loading ? (
          <p className="dim">loading…</p>
        ) : items.length === 0 ? (
          <p className="dim">no resources found</p>
        ) : (
          <table style={{ fontSize: 12, width: '100%' }}>
            <thead>
              <tr>
                <th>Slug</th>
                <th>Type</th>
                <th>Name</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <code>{r.slug}</code>
                  </td>
                  <td>
                    <span className="tag">{r.type}</span>
                  </td>
                  <td>{r.display_name}</td>
                  <td>
                    <button onClick={() => onPick(r)}>pick</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

interface PreviewModalProps {
  preview: PreviewResult;
  onClose: () => void;
}

function PreviewModal({ preview, onClose }: PreviewModalProps) {
  const highlighted = useMemo(() => {
    const esc = preview.rendered_prompt
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    return esc.replace(
      /\{\{\s*(resource|skill|document|folder|system_fragment):[^}]+\}\}/g,
      (m) => `<mark>${m}</mark>`,
    );
  }, [preview.rendered_prompt]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--bg, #1a1a1a)',
          padding: 16,
          borderRadius: 6,
          width: 'min(960px, 92vw)',
          maxHeight: '85vh',
          overflow: 'auto',
          border: '1px solid var(--border, #333)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Rendered prompt preview</h3>
          <button onClick={onClose}>x</button>
        </div>
        {preview.unresolved_markers.length > 0 && (
          <p style={{ color: 'var(--warning, #b45309)', fontSize: 12 }}>
            unresolved markers: {preview.unresolved_markers.join(', ')}
          </p>
        )}
        {preview.warnings.length > 0 && (
          <ul style={{ fontSize: 12, color: 'var(--warning, #b45309)' }}>
            {preview.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
        <pre
          style={{
            background: 'var(--bg-secondary, #111)',
            padding: 12,
            borderRadius: 4,
            fontSize: 12,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </div>
    </div>
  );
}

interface Props {
  agentId: string;
}

export default function AgentPromptResourcesEditor({ agentId }: Props) {
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [pickerForRow, setPickerForRow] = useState<number | null>(null);
  const [versionCache, setVersionCache] = useState<Record<string, RepoVersion[]>>({});
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await req<{ items: Binding[] }>(
        `/api/agents/${encodeURIComponent(agentId)}/prompt-resources`,
      );
      setBindings(data.items || []);
      setDirty(false);
      setError(null);
    } catch (e) {
      setError(errStr(e, 'failed to load prompt resources'));
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  // Load versions lazily for each bound resource.
  useEffect(() => {
    const missing = bindings
      .map((b) => b.resource_id)
      .filter((id) => !(id in versionCache));
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.all(
      missing.map((id) =>
        repoApi
          .versions(id)
          .then((r) => [id, r.items] as const)
          .catch(() => [id, [] as RepoVersion[]] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      setVersionCache((prev) => {
        const next = { ...prev };
        for (const [id, items] of entries) next[id] = items;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [bindings, versionCache]);

  const updateBinding = (idx: number, patch: Partial<Binding>) => {
    setBindings((bs) => bs.map((b, i) => (i === idx ? { ...b, ...patch } : b)));
    setDirty(true);
  };

  const removeBinding = (idx: number) => {
    setBindings((bs) => bs.filter((_, i) => i !== idx));
    setDirty(true);
  };

  const moveBinding = (idx: number, dir: -1 | 1) => {
    const next = [...bindings];
    const swap = idx + dir;
    if (swap < 0 || swap >= next.length) return;
    const a = next[idx];
    const b = next[swap];
    if (!a || !b) return;
    next[idx] = b;
    next[swap] = a;
    setBindings(next.map((bb, i) => ({ ...bb, display_order: i })));
    setDirty(true);
  };

  const onPick = (r: RepoResource) => {
    if (pickerForRow !== null) {
      updateBinding(pickerForRow, {
        resource_id: r.id,
        resource_slug: r.slug,
        resource_type: r.type,
        active_version_id: r.active_version_id ?? null,
        pinned_version_id: null,
        mode: defaultModeForType(r.type),
      });
      setPickerForRow(null);
      setPicking(false);
      return;
    }
    setBindings((prev) => [
      ...prev,
      {
        resource_id: r.id,
        resource_slug: r.slug,
        resource_type: r.type,
        marker: `resource:${slugifyMarker(r.slug)}`,
        mode: defaultModeForType(r.type),
        pinned_version_id: null,
        required: true,
        display_order: prev.length,
        active_version_id: r.active_version_id ?? null,
      },
    ]);
    setPicking(false);
    setDirty(true);
  };

  const save = async () => {
    if (reason.trim().length < 3) {
      setToast({ kind: 'error', msg: 'reason required (min 3 chars)' });
      return;
    }
    setBusy(true);
    try {
      const body = {
        bindings: bindings.map((b, i) => ({
          resource_id: b.resource_id,
          marker: b.marker,
          mode: b.mode,
          pinned_version_id: b.pinned_version_id || null,
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
      setToast({ kind: 'error', msg: errStr(e, 'failed to save bindings') });
    } finally {
      setBusy(false);
    }
  };

  const renderPreview = async () => {
    setBusy(true);
    try {
      const promptDoc = await req<{ content: string }>(
        `/api/agents/${encodeURIComponent(agentId)}/prompt`,
      );
      const result = await req<PreviewResult>(
        `/api/agents/${encodeURIComponent(agentId)}/prompt-resources/preview`,
        {
          method: 'POST',
          body: JSON.stringify({
            template: promptDoc.content || '',
            bindings: bindings.map((b, i) => ({
              resource_id: b.resource_id,
              marker: b.marker,
              mode: b.mode,
              pinned_version_id: b.pinned_version_id || null,
              required: b.required,
              display_order: i,
            })),
          }),
        },
      );
      setPreview(result);
    } catch (e) {
      setToast({ kind: 'error', msg: errStr(e, 'failed to render preview') });
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="stack">
        <h2>Prompt Resources</h2>
        <p className="dim">loading…</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Prompt Resources</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={renderPreview} disabled={busy}>
            Render preview
          </button>
          <button
            onClick={() => {
              setPickerForRow(null);
              setPicking(true);
            }}
          >
            + Add binding
          </button>
        </div>
      </div>

      {error && <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>}

      <p className="dim" style={{ fontSize: 12, margin: 0 }}>
        Bindings splice resource content into the system prompt at named markers (e.g.{' '}
        <code>{'{{resource:cv-writing}}'}</code>).
      </p>

      <table>
        <thead>
          <tr>
            <th style={{ width: 60 }}>Order</th>
            <th>Marker</th>
            <th>Resource</th>
            <th>Mode</th>
            <th>Version</th>
            <th style={{ width: 70, textAlign: 'center' }}>Required</th>
            <th style={{ width: 60 }}></th>
          </tr>
        </thead>
        <tbody>
          {bindings.length === 0 ? (
            <tr>
              <td colSpan={7} className="dim" style={{ textAlign: 'center', padding: 24 }}>
                no bindings yet — click "+ Add binding"
              </td>
            </tr>
          ) : (
            bindings.map((b, i) => {
              const versions = versionCache[b.resource_id] || [];
              return (
                <tr key={`${b.resource_id}-${i}`}>
                  <td>
                    <div style={{ display: 'flex', gap: 2 }}>
                      <button
                        onClick={() => moveBinding(i, -1)}
                        disabled={i === 0}
                        style={{ padding: '0 6px' }}
                      >
                        ↑
                      </button>
                      <button
                        onClick={() => moveBinding(i, 1)}
                        disabled={i === bindings.length - 1}
                        style={{ padding: '0 6px' }}
                      >
                        ↓
                      </button>
                    </div>
                  </td>
                  <td>
                    <input
                      type="text"
                      value={b.marker}
                      onChange={(e) => updateBinding(i, { marker: e.target.value })}
                      placeholder="resource:my-marker"
                      style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
                    />
                  </td>
                  <td>
                    {b.resource_slug ? (
                      <Link to={`/resources/${encodeURIComponent(b.resource_id)}`}>
                        <code>{b.resource_slug}</code>
                      </Link>
                    ) : (
                      <code className="dim">{b.resource_id.slice(0, 12)}…</code>
                    )}
                    {b.resource_type && (
                      <span className="tag" style={{ marginLeft: 4 }}>
                        {b.resource_type}
                      </span>
                    )}
                    <button
                      onClick={() => {
                        setPickerForRow(i);
                        setPicking(true);
                      }}
                      style={{ marginLeft: 6, fontSize: 11 }}
                    >
                      change
                    </button>
                  </td>
                  <td>
                    <select
                      value={b.mode}
                      onChange={(e) => updateBinding(i, { mode: e.target.value as PromptMode })}
                    >
                      {MODES.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      value={b.pinned_version_id || ''}
                      onChange={(e) =>
                        updateBinding(i, { pinned_version_id: e.target.value || null })
                      }
                    >
                      <option value="">latest</option>
                      {versions.map((v) => (
                        <option key={v.id} value={v.id}>
                          v{v.version_number}
                          {v.is_draft ? ' (draft)' : ''}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td style={{ textAlign: 'center' }}>
                    <input
                      type="checkbox"
                      checked={b.required}
                      onChange={(e) => updateBinding(i, { required: e.target.checked })}
                    />
                  </td>
                  <td>
                    <button
                      onClick={() => removeBinding(i)}
                      style={{ color: 'var(--error, crimson)' }}
                    >
                      remove
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {dirty && (
        <div
          className="form-panel"
          style={{ display: 'flex', gap: 8, alignItems: 'center', padding: 12 }}
        >
          <input
            type="text"
            placeholder="reason (bumps agent version, min 3 chars)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            style={{ flex: 1, padding: '6px 10px' }}
          />
          <button onClick={save} disabled={busy || reason.trim().length < 3}>
            {busy ? 'saving…' : 'Save bindings'}
          </button>
          <button onClick={refresh} disabled={busy} style={{ background: 'var(--bg-secondary)' }}>
            Discard
          </button>
        </div>
      )}

      {picking && (
        <ResourcePicker
          onPick={onPick}
          onClose={() => {
            setPicking(false);
            setPickerForRow(null);
          }}
        />
      )}

      {preview && <PreviewModal preview={preview} onClose={() => setPreview(null)} />}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
