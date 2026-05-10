import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { versionsApi, VersionSummary, DiffResponse } from '../api/versions';

interface AgentVersionsProps {
  agentId?: string;
}

const PAGE_SIZE = 15;

function diffLineClass(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-meta';
  if (line.startsWith('@@')) return 'diff-hunk';
  if (line.startsWith('+')) return 'diff-add';
  if (line.startsWith('-')) return 'diff-del';
  return 'diff-ctx';
}

function fmtScalar(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}

function isLeaf(v: unknown): boolean {
  return v === null
    || v === undefined
    || typeof v === 'string'
    || typeof v === 'number'
    || typeof v === 'boolean';
}

type LeafChange = { path: string; from: unknown; to: unknown; kind: 'changed' | 'added' | 'removed' };

function flattenChange(path: string, from: unknown, to: unknown, out: LeafChange[]): void {
  if (isLeaf(from) && isLeaf(to)) {
    if (from !== to) out.push({ path, from, to, kind: 'changed' });
    return;
  }
  if (Array.isArray(from) && Array.isArray(to)) {
    const n = Math.max(from.length, to.length);
    for (let i = 0; i < n; i++) {
      if (i >= from.length) out.push({ path: `${path}[${i}]`, from: undefined, to: to[i], kind: 'added' });
      else if (i >= to.length) out.push({ path: `${path}[${i}]`, from: from[i], to: undefined, kind: 'removed' });
      else flattenChange(`${path}[${i}]`, from[i], to[i], out);
    }
    return;
  }
  if (from && to && typeof from === 'object' && typeof to === 'object') {
    const fo = from as Record<string, unknown>;
    const to_ = to as Record<string, unknown>;
    const keys = new Set([...Object.keys(fo), ...Object.keys(to_)]);
    for (const k of keys) {
      if (!(k in fo)) out.push({ path: `${path}.${k}`, from: undefined, to: to_[k], kind: 'added' });
      else if (!(k in to_)) out.push({ path: `${path}.${k}`, from: fo[k], to: undefined, kind: 'removed' });
      else flattenChange(`${path}.${k}`, fo[k], to_[k], out);
    }
    return;
  }
  out.push({ path, from, to, kind: 'changed' });
}

function flattenSide(path: string, value: unknown, kind: 'added' | 'removed', out: LeafChange[]): void {
  if (isLeaf(value)) {
    out.push({ path, from: kind === 'removed' ? value : undefined, to: kind === 'added' ? value : undefined, kind });
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((v, i) => flattenSide(`${path}[${i}]`, v, kind, out));
    return;
  }
  if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      flattenSide(`${path}.${k}`, v, kind, out);
    }
    return;
  }
  out.push({ path, from: kind === 'removed' ? value : undefined, to: kind === 'added' ? value : undefined, kind });
}

export default function AgentVersions({ agentId: propAgentId }: AgentVersionsProps) {
  const { id } = useParams<{ id: string }>();
  const agentId = propAgentId || id || '';

  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<VersionSummary | null>(null);
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffErr, setDiffErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await versionsApi.listVersions(agentId);
      setVersions(data.versions);
      setActiveId(data.active_version_id ?? null);
      const av = data.active_version ?? data.latest_version ?? null;
      setActiveVersion(av);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'failed to load versions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (agentId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId]);

  const totalPages = Math.max(1, Math.ceil(versions.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages - 1);
  const paged = useMemo(
    () => versions.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE),
    [versions, currentPage],
  );

  useEffect(() => {
    if (!selected || activeVersion == null || selected.version === activeVersion) {
      setDiff(null);
      setDiffErr(null);
      return;
    }
    let cancelled = false;
    setDiffLoading(true);
    setDiffErr(null);
    versionsApi
      .diffVersions(agentId, activeVersion, selected.version)
      .then((d) => { if (!cancelled) setDiff(d); })
      .catch((e) => {
        if (!cancelled) setDiffErr(e instanceof Error ? e.message : 'failed to load diff');
      })
      .finally(() => { if (!cancelled) setDiffLoading(false); });
    return () => { cancelled = true; };
  }, [selected, activeVersion, agentId]);

  const activate = async (v: VersionSummary) => {
    setBusy(true);
    try {
      await versionsApi.activate(agentId, v.version);
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'failed to activate');
    } finally {
      setBusy(false);
    }
  };

  if (loading && versions.length === 0) {
    return <p className="dim" style={{ padding: 12 }}>loading versions…</p>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {err && <p style={{ color: 'crimson', fontSize: 12 }}>{err}</p>}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #333)' }}>
            <th style={{ padding: '6px 8px', width: 60 }}>Version</th>
            <th style={{ padding: '6px 8px', width: 80 }}>Status</th>
            <th style={{ padding: '6px 8px' }}>Changelog</th>
            <th style={{ padding: '6px 8px', width: 120 }}>Author</th>
            <th style={{ padding: '6px 8px', width: 140 }}>Created</th>
            <th style={{ padding: '6px 8px', width: 110 }}></th>
          </tr>
        </thead>
        <tbody>
          {paged.map((v) => {
            const isActive = v.id === activeId;
            const isSelected = selected?.id === v.id;
            return (
              <tr
                key={v.id}
                onClick={() => setSelected(isSelected ? null : v)}
                style={{
                  cursor: 'pointer',
                  background: isSelected
                    ? 'rgba(80,150,255,0.18)'
                    : isActive
                    ? 'rgba(80,200,120,0.10)'
                    : 'transparent',
                  borderBottom: '1px solid var(--border, #2a2a2a)',
                  borderLeft: isActive ? '3px solid var(--green, #3fb950)' : '3px solid transparent',
                }}
              >
                <td style={{ padding: '6px 8px', fontFamily: 'var(--mono, monospace)' }}>
                  v{v.version}
                </td>
                <td style={{ padding: '6px 8px', fontSize: 11 }}>
                  {isActive && (
                    <span style={{ color: 'var(--green, #3fb950)', fontWeight: 600 }}>● active</span>
                  )}
                  {!isActive && v.is_draft && (
                    <span style={{ color: 'var(--yellow, #d29922)' }}>draft</span>
                  )}
                  {!isActive && !v.is_draft && (
                    <span className="dim">—</span>
                  )}
                </td>
                <td style={{ padding: '6px 8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 0 }} title={v.changelog}>
                  {v.changelog || <span className="dim">—</span>}
                </td>
                <td style={{ padding: '6px 8px', fontSize: 11 }} className="dim">{v.author || '—'}</td>
                <td style={{ padding: '6px 8px', fontSize: 11 }} className="dim">
                  {new Date(v.created_at).toLocaleString()}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'right' }}>
                  {!isActive && (
                    <button
                      onClick={(e) => { e.stopPropagation(); activate(v); }}
                      disabled={busy}
                      className="primary"
                      style={{ fontSize: 11, padding: '2px 10px' }}
                    >
                      Activate
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div className="row" style={{ alignItems: 'center', gap: 8, fontSize: 11 }}>
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
            style={{ fontSize: 11 }}
          >
            ← prev
          </button>
          <span className="dim" style={{ flex: 1, textAlign: 'center' }}>
            page {currentPage + 1} of {totalPages} · {versions.length} version{versions.length === 1 ? '' : 's'}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={currentPage >= totalPages - 1}
            style={{ fontSize: 11 }}
          >
            next →
          </button>
        </div>
      )}

      {selected && (
        <div
          style={{
            border: '1px solid var(--border, #333)',
            borderRadius: 4,
            padding: 12,
            background: 'var(--bg-elevated, #161b22)',
          }}
        >
          <div className="row between" style={{ alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>
              Diff: v{activeVersion} (active) → v{selected.version}
            </strong>
            <button onClick={() => setSelected(null)} style={{ fontSize: 11 }}>close</button>
          </div>
          {diffLoading && <p className="dim" style={{ fontSize: 12 }}>loading diff…</p>}
          {diffErr && <p style={{ color: 'crimson', fontSize: 12 }}>{diffErr}</p>}
          {!diffLoading && !diffErr && selected.version === activeVersion && (
            <p className="dim" style={{ fontSize: 12 }}>This is the active version.</p>
          )}
          {diff && (() => {
            const cd = (diff.content_diff || {}) as {
              added?: Record<string, unknown>;
              removed?: Record<string, unknown>;
              changed?: Record<string, { from: unknown; to: unknown }>;
            };
            const hasPrompt = diff.prompt_diff && diff.prompt_diff.trim().length > 0;
            const IRRELEVANT = new Set(['prompt_path', 'source_path', 'source_format', 'prompt']);
            const keep = (k: string) => !IRRELEVANT.has(k);
            const leaves: LeafChange[] = [];
            for (const [k, v] of Object.entries(cd.changed || {})) {
              if (!keep(k)) continue;
              flattenChange(k, v.from, v.to, leaves);
            }
            for (const [k, v] of Object.entries(cd.added || {})) {
              if (!keep(k)) continue;
              flattenSide(k, v, 'added', leaves);
            }
            for (const [k, v] of Object.entries(cd.removed || {})) {
              if (!keep(k)) continue;
              flattenSide(k, v, 'removed', leaves);
            }
            const hasConfig = leaves.length > 0;
            if (!hasPrompt && !hasConfig) {
              return <p className="dim" style={{ fontSize: 12 }}>No differences.</p>;
            }
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {hasPrompt && (
                  <div>
                    <div style={{ fontSize: 11, marginBottom: 4 }} className="dim">Prompt</div>
                    <pre
                      style={{
                        fontFamily: 'var(--mono, monospace)', fontSize: 12, margin: 0, padding: 8,
                        background: 'var(--bg, #0d1117)', border: '1px solid var(--border, #2a2a2a)',
                        borderRadius: 3, overflow: 'auto', maxHeight: 480, whiteSpace: 'pre',
                      }}
                    >
                      {diff.prompt_diff.split('\n').map((line, i) => (
                        <div
                          key={i}
                          className={diffLineClass(line)}
                          style={{
                            color:
                              line.startsWith('+') && !line.startsWith('+++')
                                ? 'var(--green, #3fb950)'
                                : line.startsWith('-') && !line.startsWith('---')
                                ? 'var(--red, #f85149)'
                                : line.startsWith('@@')
                                ? 'var(--accent, #58a6ff)'
                                : 'var(--fg-muted, #8b949e)',
                          }}
                        >
                          {line || ' '}
                        </div>
                      ))}
                    </pre>
                  </div>
                )}
                {hasConfig && (
                  <div>
                    <div style={{ fontSize: 11, marginBottom: 4 }} className="dim">
                      Configuration · {leaves.length} change{leaves.length === 1 ? '' : 's'}
                    </div>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12 }}>
                      {leaves.map((c, i) => {
                        const tag =
                          c.kind === 'added' ? { txt: '+ added', color: 'var(--green, #3fb950)' }
                          : c.kind === 'removed' ? { txt: '− removed', color: 'var(--red, #f85149)' }
                          : { txt: '~ changed', color: 'var(--yellow, #d29922)' };
                        return (
                          <li
                            key={`${c.path}-${i}`}
                            style={{
                              padding: '6px 8px',
                              borderBottom: '1px solid var(--border, #2a2a2a)',
                              display: 'grid',
                              gridTemplateColumns: '80px 1fr',
                              gap: 8,
                              alignItems: 'baseline',
                            }}
                          >
                            <span style={{ color: tag.color, fontSize: 11, fontWeight: 600 }}>{tag.txt}</span>
                            <div>
                              <div style={{ fontFamily: 'var(--mono, monospace)', color: 'var(--fg, #eee)' }}>
                                {c.path}
                              </div>
                              {c.kind !== 'added' && (
                                <div style={{ color: 'var(--red, #f85149)', fontFamily: 'var(--mono, monospace)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, marginTop: 2 }}>
                                  − {fmtScalar(c.from)}
                                </div>
                              )}
                              {c.kind !== 'removed' && (
                                <div style={{ color: 'var(--green, #3fb950)', fontFamily: 'var(--mono, monospace)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 11, marginTop: 2 }}>
                                  + {fmtScalar(c.to)}
                                </div>
                              )}
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}
