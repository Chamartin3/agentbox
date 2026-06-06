import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../../api/client';
import { repoApi, type RepoResource, type RepoVersion } from '../../api/repo';
import { ConflictPolicy, MaterializeMode, RepoType as RepoTypeEnum } from '../../api/enums';
import ResourcePicker from '../resources/ResourcePicker';
import Toast from '../common/Toast';

type OnConflict = ConflictPolicy;

interface Binding {
  id?: string;
  resource_id: string;
  resource_slug?: string | null;
  resource_type?: string | null;
  target_path: string;
  materialize_mode: MaterializeMode;
  on_conflict: OnConflict;
  pinned_version_id?: string | null;
  display_order: number;
  active_version_id?: string | null;
}

interface DryRunEntry {
  binding_id?: string;
  resource_id: string;
  resource_slug?: string;
  resource_type?: string;
  version_id?: string;
  target_path: string;
  file_count?: number;
  materialize_mode?: string;
  on_conflict?: string;
}

interface DryRunConflict {
  binding_id?: string | null;
  issue: string;
}

interface DryRunResult {
  entries: DryRunEntry[];
  conflicts: DryRunConflict[];
}

import { apiRequest as req } from '../../api/http';

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: string } | string | undefined;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.detail === 'string') return d.detail;
    return `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}


function defaultTargetPath(r: RepoResource): string {
  if (r.type === RepoTypeEnum.Skill) {
    const name = r.slug.replace(/^skill:/, '');
    return `.claude/skills/${name}`;
  }
  return r.slug.replace(/^(document|folder):/, '');
}

export default function WorkspaceResourcesEditor({ workspaceId }: { workspaceId: string }) {
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [dryRun, setDryRun] = useState<DryRunResult | null>(null);
  const [versionsCache, setVersionsCache] = useState<Record<string, RepoVersion[]>>({});
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
        `/api/workspaces/${encodeURIComponent(workspaceId)}/resources`,
      );
      setBindings(data.items || []);
      setDirty(false);
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to load bindings') });
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => { refresh(); }, [refresh]);

  // Lazy-load versions for each resource in bindings so the dropdown can show pinning options.
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

  const updateBinding = (idx: number, patch: Partial<Binding>) => {
    setBindings((bs) => bs.map((b, i) => (i === idx ? { ...b, ...patch } : b)));
    setDirty(true);
  };

  const removeBinding = (idx: number) => {
    setBindings((bs) => bs.filter((_, i) => i !== idx).map((b, i) => ({ ...b, display_order: i })));
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

  const onPick = (rs: RepoResource[]) => {
    setBindings((bs) => {
      const newRows: Binding[] = rs.map((r, i) => ({
        resource_id: r.id,
        resource_slug: r.slug,
        resource_type: r.type,
        target_path: defaultTargetPath(r),
        materialize_mode: r.type === RepoTypeEnum.Skill ? MaterializeMode.Symlink : MaterializeMode.Copy,
        on_conflict: ConflictPolicy.Error,
        pinned_version_id: null,
        display_order: bs.length + i,
        active_version_id: r.active_version_id ?? null,
      }));
      return [...bs, ...newRows];
    });
    setPicking(false);
    setDirty(true);
  };

  const attachedIds = new Set(bindings.map((b) => b.resource_id));

  const save = async () => {
    setBusy(true);
    try {
      const body = {
        bindings: bindings.map((b, i) => ({
          resource_id: b.resource_id,
          target_path: b.target_path || null,
          materialize_mode: b.materialize_mode,
          on_conflict: b.on_conflict,
          pinned_version_id: b.pinned_version_id || null,
          display_order: i,
        })),
        reason: 'ui edit',
      };
      await req(`/api/workspaces/${encodeURIComponent(workspaceId)}/resources`, {
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

  const runDryRun = async () => {
    try {
      const body = {
        bindings: bindings.map((b, i) => ({
          resource_id: b.resource_id,
          target_path: b.target_path || null,
          materialize_mode: b.materialize_mode,
          on_conflict: b.on_conflict,
          pinned_version_id: b.pinned_version_id || null,
          display_order: i,
        })),
      };
      const r = await req<DryRunResult>(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/resources/dry-run`,
        { method: 'POST', body: JSON.stringify(body) },
      );
      setDryRun(r);
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'dry-run failed') });
    }
  };

  const focusBindingPath = (bindingId: string | null | undefined) => {
    if (!bindingId) return;
    const idx = bindings.findIndex((b) => b.id === bindingId);
    if (idx < 0) return;
    const el = document.getElementById(`binding-target-${idx}`) as HTMLInputElement | null;
    if (el) {
      el.focus();
      el.select();
    }
  };

  const removeBindingById = (bindingId: string | null | undefined) => {
    if (!bindingId) return;
    const idx = bindings.findIndex((b) => b.id === bindingId);
    if (idx < 0) return;
    removeBinding(idx);
  };

  if (loading) return <p className="dim">loading workspace resources…</p>;

  return (
    <section className="form-panel">
      <div className="row between" style={{ marginBottom: 8 }}>
        <div>
          <h3 style={{ marginTop: 0, marginBottom: 2 }}>Resource bindings</h3>
          <p className="dim" style={{ fontSize: 12, margin: 0 }}>
            Materialized into the workspace at run time.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button onClick={() => setPicking(true)}>+ add resource</button>
          <button onClick={runDryRun} disabled={bindings.length === 0}>preview</button>
        </div>
      </div>

      {bindings.length === 0 ? (
        <p className="dim">No bindings. Click "+ add resource" to attach a document, folder, or skill.</p>
      ) : (
        <table style={{ fontSize: 12, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: 56 }}>order</th>
              <th>resource</th>
              <th>target path</th>
              <th>mode</th>
              <th>on conflict</th>
              <th>version</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {bindings.map((b, i) => {
              const versions = versionsCache[b.resource_id] || [];
              return (
                <tr key={b.id ?? `new-${i}`}>
                  <td>
                    <div className="row" style={{ gap: 2 }}>
                      <button onClick={() => moveBinding(i, -1)} disabled={i === 0} style={{ padding: '0 6px' }}>↑</button>
                      <button onClick={() => moveBinding(i, 1)} disabled={i === bindings.length - 1} style={{ padding: '0 6px' }}>↓</button>
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
                      id={`binding-target-${i}`}
                      value={b.target_path}
                      onChange={(e) => updateBinding(i, { target_path: e.target.value })}
                      style={{ width: '100%', padding: '2px 6px', fontFamily: 'monospace', fontSize: 12 }}
                    />
                  </td>
                  <td>
                    <select
                      value={b.materialize_mode}
                      onChange={(e) => updateBinding(i, { materialize_mode: e.target.value as MaterializeMode })}
                    >
                      <option value="copy">copy</option>
                      <option value="symlink">symlink</option>
                    </select>
                  </td>
                  <td>
                    <select
                      value={b.on_conflict}
                      onChange={(e) => updateBinding(i, { on_conflict: e.target.value as OnConflict })}
                    >
                      <option value="error">error</option>
                      <option value="overwrite">overwrite</option>
                      <option value="skip">skip</option>
                    </select>
                  </td>
                  <td>
                    <select
                      value={b.pinned_version_id ?? ''}
                      onChange={(e) => updateBinding(i, { pinned_version_id: e.target.value || null })}
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
                    <button onClick={() => removeBinding(i)} style={{ color: 'crimson' }}>remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {dirty && (
        <div className="row" style={{ marginTop: 12, gap: 8, alignItems: 'center' }}>
          <button onClick={save} disabled={busy} className="primary">
            {busy ? 'saving…' : 'save bindings'}
          </button>
          <button onClick={refresh} disabled={busy} style={{ background: 'var(--bg-secondary)' }}>
            discard
          </button>
        </div>
      )}

      {dryRun && (
        <div
          style={{
            marginTop: 12,
            padding: 8,
            border: '1px solid var(--border, #333)',
            borderRadius: 4,
          }}
        >
          <div className="row between">
            <strong style={{ fontSize: 12 }}>Preview tree</strong>
            <button onClick={() => setDryRun(null)}>close</button>
          </div>
          <p className="dim" style={{ fontSize: 11, margin: '4px 0' }}>
            {dryRun.entries.length} entries · {dryRun.conflicts.length} conflicts
          </p>

          {dryRun.conflicts.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <strong style={{ fontSize: 12, color: 'var(--error, #b91c1c)' }}>Conflicts</strong>
              <table style={{ fontSize: 11, width: '100%', marginTop: 4 }}>
                <thead>
                  <tr><th>issue</th><th style={{ width: 200 }}></th></tr>
                </thead>
                <tbody>
                  {dryRun.conflicts.map((c, i) => (
                    <tr key={`${c.binding_id ?? 'noid'}-${i}`}>
                      <td style={{ color: 'var(--error, #b91c1c)' }}>{c.issue}</td>
                      <td>
                        {c.binding_id && (
                          <div className="row" style={{ gap: 4 }}>
                            <button onClick={() => focusBindingPath(c.binding_id)} style={{ fontSize: 11 }}>
                              change path
                            </button>
                            <button
                              onClick={() => removeBindingById(c.binding_id)}
                              style={{ fontSize: 11, color: 'crimson' }}
                            >
                              remove
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {dryRun.entries.length > 0 && (
            <table style={{ fontSize: 11, width: '100%' }}>
              <thead>
                <tr>
                  <th>target path</th>
                  <th>resource</th>
                  <th>mode</th>
                  <th>files</th>
                </tr>
              </thead>
              <tbody>
                {dryRun.entries.map((e, i) => (
                  <tr key={`${e.binding_id ?? 'noid'}-${i}`}>
                    <td className="mono">{e.target_path}</td>
                    <td><code>{e.resource_slug || e.resource_id.slice(0, 12)}</code></td>
                    <td>{e.materialize_mode}</td>
                    <td>{e.file_count ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {picking && (
        <ResourcePicker
          excludeIds={attachedIds}
          allowUpload
          onPick={onPick}
          onClose={() => setPicking(false)}
        />
      )}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </section>
  );
}
