import { useEffect, useState, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import { repoApi, RepoResource, RepoVersion, RepoType } from '../api/repo';
import { RepoType as RepoTypeEnum } from '../api/enums';

function fmtDate(s?: string): string {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString();
}

const PRE_STYLE: React.CSSProperties = {
  background: 'var(--code-bg, #0d1117)',
  color: 'var(--code-fg, #c9d1d9)',
  padding: 12,
  borderRadius: 4,
  maxHeight: 480,
  overflow: 'auto',
  fontSize: 12,
  whiteSpace: 'pre-wrap',
};

// --- KindViewer subcomponents ---

interface SchemaProp {
  name: string;
  type: string;
  required: boolean;
  description: string;
  children?: SchemaProp[];
}

function extractProps(schema: Record<string, unknown> | null | undefined): SchemaProp[] {
  if (!schema || typeof schema !== 'object') return [];
  const props = (schema.properties as Record<string, unknown>) || {};
  const required = new Set<string>(Array.isArray(schema.required) ? (schema.required as string[]) : []);
  const result: SchemaProp[] = [];
  for (const [name, raw] of Object.entries(props)) {
    const def = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
    let type = (def.type as string) || (def.$ref ? '$ref' : 'any');
    if (Array.isArray(def.type)) type = (def.type as string[]).join('|');
    if (def.enum) type = `${type} (enum)`;
    const description = (def.description as string) || '';
    const node: SchemaProp = { name, type, required: required.has(name), description };
    if (type === 'object' && def.properties) {
      node.children = extractProps(def);
    } else if (type === 'array' && def.items && typeof def.items === 'object') {
      const items = def.items as Record<string, unknown>;
      if (items.properties) {
        node.type = 'array<object>';
        node.children = extractProps(items);
      } else if (items.type) {
        node.type = `array<${items.type as string}>`;
      }
    }
    result.push(node);
  }
  return result;
}

function SchemaRow({ prop, depth }: { prop: SchemaProp; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = (prop.children?.length ?? 0) > 0;
  return (
    <>
      <tr>
        <td style={{ paddingLeft: 8 + depth * 18 }}>
          {hasChildren ? (
            <button
              onClick={() => setOpen((v) => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, marginRight: 4 }}
            >
              {open ? '▾' : '▸'}
            </button>
          ) : (
            <span style={{ display: 'inline-block', width: 14 }} />
          )}
          <code>{prop.name}</code>
        </td>
        <td className="dim" style={{ fontSize: 12 }}>{prop.type}</td>
        <td>{prop.required ? '✓' : '—'}</td>
        <td style={{ fontSize: 12 }}>{prop.description}</td>
      </tr>
      {open && hasChildren && prop.children!.map((c) => (
        <SchemaRow key={`${prop.name}.${c.name}`} prop={c} depth={depth + 1} />
      ))}
    </>
  );
}

function SchemaViewer({ content }: { content: string }) {
  const [showRaw, setShowRaw] = useState(false);
  let parsed: Record<string, unknown> | null = null;
  let parseError: string | null = null;
  try {
    parsed = JSON.parse(content);
  } catch (e) {
    parseError = String(e);
  }
  const props = extractProps(parsed);
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8 }}>
        <button onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? 'show table' : 'show raw JSON'}
        </button>
      </div>
      {showRaw || parseError || props.length === 0 ? (
        <pre style={PRE_STYLE}>{parseError ? `Parse error: ${parseError}\n\n${content}` : content}</pre>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Property</th>
              <th>Type</th>
              <th>Required</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {props.map((p) => (
              <SchemaRow key={p.name} prop={p} depth={0} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function DocumentViewer({ content }: { content: string }) {
  // TODO: install react-markdown to render markdown with formatting.
  return <pre style={PRE_STYLE}>{content}</pre>;
}

function fmtBytes(n: number | null): string {
  if (n == null) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function FolderTree({
  resourceId,
  versionId,
}: {
  resourceId: string;
  versionId?: string;
}) {
  const [entries, setEntries] = useState<Array<{ relative_path: string; size_bytes: number | null; mime_type: string | null }>>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    repoApi.tree(resourceId, versionId)
      .then((r) => { if (!cancelled) { setEntries(r.entries); setErr(null); } })
      .catch((e) => { if (!cancelled) setErr(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [resourceId, versionId]);

  if (loading) return <p className="dim">loading tree…</p>;
  if (err) return <p style={{ color: 'crimson' }}>{err}</p>;
  if (entries.length === 0) return <p className="dim">No files.</p>;

  // group by top-level directory
  const groups: Record<string, typeof entries> = {};
  for (const e of entries) {
    const dir = e.relative_path.includes('/') ? e.relative_path.split('/')[0] : '(root)';
    (groups[dir] ||= []).push(e);
  }
  const totalBytes = entries.reduce((s, e) => s + (e.size_bytes ?? 0), 0);

  return (
    <div className="stack" style={{ gap: 8 }}>
      <span className="dim" style={{ fontSize: 12 }}>
        {entries.length} files · {fmtBytes(totalBytes)}
      </span>
      <table>
        <thead><tr><th>Path</th><th>Size</th><th>Type</th></tr></thead>
        <tbody>
          {Object.entries(groups).flatMap(([dir, items]) => [
            <tr key={`__h_${dir}`}><td colSpan={3} style={{ paddingTop: 8 }}><strong>{dir}/</strong></td></tr>,
            ...items.map((e) => (
              <tr key={e.relative_path}>
                <td style={{ paddingLeft: 16, fontFamily: 'monospace', fontSize: 12 }}>{e.relative_path}</td>
                <td className="dim" style={{ fontSize: 12 }}>{fmtBytes(e.size_bytes)}</td>
                <td className="dim" style={{ fontSize: 12 }}>{e.mime_type || ''}</td>
              </tr>
            )),
          ])}
        </tbody>
      </table>
    </div>
  );
}

function FolderViewer({ content }: { content: string }) {
  return <pre style={PRE_STYLE}>{content}</pre>;
}

function SkillViewer({ content }: { content: string }) {
  // SKILL.md = YAML frontmatter wrapped by --- delimiters followed by the body.
  // Render the frontmatter as a small property table and the body as a pre block.
  const m = content.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!m) return <pre style={PRE_STYLE}>{content}</pre>;
  const [, fmRaw, body] = m;
  const rows: Array<[string, string]> = [];
  for (const line of fmRaw.split('\n')) {
    const idx = line.indexOf(':');
    if (idx === -1) continue;
    const k = line.slice(0, idx).trim();
    const v = line.slice(idx + 1).trim();
    if (k) rows.push([k, v]);
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      {rows.length > 0 && (
        <table>
          <thead><tr><th>Frontmatter</th><th>Value</th></tr></thead>
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k}><td><code>{k}</code></td><td style={{ fontSize: 12 }}>{v}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 style={{ fontSize: 13, margin: '8px 0 0 0' }}>SKILL.md body</h3>
      <pre style={PRE_STYLE}>{body.trim()}</pre>
    </div>
  );
}

function ScriptViewer({ content, filename }: { content: string; filename?: string }) {
  const ext = (filename || '').toLowerCase().split('.').pop() || '';
  let language = 'text';
  if (ext === 'py') language = 'python';
  else if (ext === 'js' || ext === 'mjs' || ext === 'cjs' || ext === 'ts') language = 'js';
  else if (ext === 'sh' || ext === 'bash') language = 'shell';
  return (
    <div className="stack" style={{ gap: 4 }}>
      <span className="dim" style={{ fontSize: 12 }}>language: {language}</span>
      <pre
        style={{
          ...PRE_STYLE,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
          whiteSpace: 'pre',
        }}
      >
        {content}
      </pre>
    </div>
  );
}

interface KindViewerProps {
  kind: RepoType;
  content: string;
  filename?: string;
}

function KindViewer({ kind, content, filename }: KindViewerProps) {
  switch (kind) {
    case RepoTypeEnum.Schema:
      return <SchemaViewer content={content} />;
    case RepoTypeEnum.Document:
      return <DocumentViewer content={content} />;
    case RepoTypeEnum.Folder:
      return <FolderViewer content={content} />;
    case RepoTypeEnum.Skill:
      return <SkillViewer content={content} />;
    case RepoTypeEnum.Script:
      return <ScriptViewer content={content} filename={filename} />;
    default:
      return <pre style={PRE_STYLE}>{content}</pre>;
  }
}

export default function ResourceDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [resource, setResource] = useState<RepoResource | null>(null);
  const [activeVersion, setActiveVersion] = useState<RepoVersion | null>(null);
  const [versions, setVersions] = useState<RepoVersion[]>([]);
  const [rendered, setRendered] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload form
  const [file, setFile] = useState<File | null>(null);
  const [changelog, setChangelog] = useState('');
  const [busy, setBusy] = useState(false);

  // Script validation panel
  const [sampleText, setSampleText] = useState('{}');
  const [direction, setDirection] = useState<'input' | 'output'>('input');
  const [validateResult, setValidateResult] = useState<{ valid: boolean; errors: Array<{ path: unknown[]; message: string }> } | null>(null);
  const [validating, setValidating] = useState(false);

  // Script schema bindings (only used for type=script uploads)
  const [scriptInputSchemaId, setScriptInputSchemaId] = useState('');
  const [scriptOutputSchemaId, setScriptOutputSchemaId] = useState('');
  const [scriptLanguage, setScriptLanguage] = useState<'' | 'python' | 'shell'>('');
  const [schemaOptions, setSchemaOptions] = useState<RepoResource[]>([]);
  useEffect(() => {
    let cancelled = false;
    repoApi.list({ type: 'schema', limit: 200 })
      .then((r) => { if (!cancelled) setSchemaOptions(r.items); })
      .catch(() => { if (!cancelled) setSchemaOptions([]); });
    return () => { cancelled = true; };
  }, []);

  const refresh = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [detail, vs] = await Promise.all([
        repoApi.get(id),
        repoApi.versions(id),
      ]);
      setResource(detail.resource);
      setActiveVersion(detail.active_version);
      setVersions(vs.items);
      setError(null);
      if (detail.active_version) {
        try {
          const r = await repoApi.render(id, detail.active_version.id);
          setRendered(r.text || '');
        } catch {
          setRendered('');
        }
      } else {
        setRendered('');
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  const onUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || changelog.trim().length < 3) {
      alert('Pick a file and provide a changelog (min 3 chars).');
      return;
    }
    setBusy(true);
    try {
      let v: RepoVersion;
      const t = resource?.type;
      if (t === RepoTypeEnum.Schema) {
        v = await repoApi.uploadSchema(id, file, changelog.trim());
      } else if (t === RepoTypeEnum.Script) {
        v = await repoApi.uploadScript(id, file, changelog.trim(), {
          language: scriptLanguage || undefined,
          input_schema_resource_id: scriptInputSchemaId || undefined,
          output_schema_resource_id: scriptOutputSchemaId || undefined,
        });
      } else if ((t === RepoTypeEnum.Folder || t === RepoTypeEnum.Skill) && /\.zip$/i.test(file.name)) {
        v = await repoApi.uploadZip(id, file, changelog.trim());
      } else {
        v = await repoApi.uploadVersion(id, file, changelog.trim(), false);
      }
      await repoApi.publish(id, v.id, changelog.trim());
      setFile(null);
      setChangelog('');
      await refresh();
    } catch (err) {
      alert(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onDownloadJson = () => {
    window.open(`/api/repo-resources/${encodeURIComponent(id)}/blobs`, '_blank');
  };

  const onDownloadPydantic = async () => {
    try {
      const code = await repoApi.exportPydantic(id, resource?.display_name?.replace(/[^A-Za-z0-9]/g, '') || 'Model');
      const blob = new Blob([code], { type: 'text/x-python' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${resource?.slug.replace(/[^A-Za-z0-9_-]/g, '_') || 'model'}.py`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(String(err));
    }
  };

  const onCopyPydantic = async () => {
    try {
      const code = await repoApi.exportPydantic(id, resource?.display_name?.replace(/[^A-Za-z0-9]/g, '') || 'Model');
      await navigator.clipboard.writeText(code);
      alert('Pydantic model copied to clipboard.');
    } catch (err) {
      alert(String(err));
    }
  };

  const onDownloadZip = () => {
    window.open(repoApi.exportZipUrl(id, activeVersion?.id), '_blank');
  };

  const onValidate = async () => {
    let sample: unknown;
    try {
      sample = JSON.parse(sampleText);
    } catch (err) {
      alert(`Invalid JSON: ${err}`);
      return;
    }
    setValidating(true);
    try {
      const result = await repoApi.validateScript(id, sample, direction);
      setValidateResult({ valid: result.valid, errors: result.errors });
    } catch (err) {
      alert(String(err));
    } finally {
      setValidating(false);
    }
  };

  const onPublish = async (vid: string) => {
    const reason = prompt('Reason for publishing this version:');
    if (!reason || reason.trim().length < 3) return;
    try {
      await repoApi.publish(id, vid, reason.trim());
      await refresh();
    } catch (err) {
      alert(String(err));
    }
  };

  const onRollback = async (versionNumber: number) => {
    const reason = prompt(`Roll back to version ${versionNumber}? Reason:`);
    if (!reason || reason.trim().length < 3) return;
    try {
      await repoApi.rollback(id, versionNumber, reason.trim());
      await refresh();
    } catch (err) {
      alert(String(err));
    }
  };

  const onDelete = async () => {
    if (!confirm(`Delete resource "${resource?.slug}"? This cannot be undone.`)) return;
    try {
      await repoApi.remove(id);
      window.location.href = '/resources';
    } catch (err) {
      alert(String(err));
    }
  };

  if (loading) return <p className="dim">loading…</p>;
  if (error) return <p style={{ color: 'crimson' }}>{error}</p>;
  if (!resource) return <p className="dim">Resource not found.</p>;

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8 }}>
        <Link to="/resources">← all resources</Link>
      </div>

      <div className="row between">
        <h1 style={{ marginBottom: 4 }}>{resource.display_name}</h1>
        <button onClick={onDelete} style={{ color: 'crimson' }}>delete</button>
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="tag">{resource.type}</span>
        <code className="dim" style={{ fontSize: 12 }}>{resource.slug}</code>
        {activeVersion && (
          <span className="pill ok">v{activeVersion.version_number} (active)</span>
        )}
        {resource.tags && <span className="tag">{resource.tags}</span>}
        <span className="dim" style={{ fontSize: 12 }}>updated {fmtDate(resource.updated_at)}</span>
      </div>

      {resource.description && (
        <p className="dim" style={{ fontSize: 13 }}>{resource.description}</p>
      )}

      <div className="dim" style={{ fontSize: 12, wordBreak: 'break-all' }}>
        <code>{resource.id}</code>
        {activeVersion && <> · sha256:{activeVersion.content_hash.slice(0, 16)}… · {activeVersion.byte_size} bytes</>}
      </div>

      <section className="stack">
        <h2 style={{ fontSize: 14, margin: 0 }}>Upload new version</h2>
        <form onSubmit={onUpload} className="stack" style={{ border: '1px solid var(--border, #333)', padding: 12, borderRadius: 4 }}>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <input
            type="text"
            placeholder="changelog (required, min 3 chars)"
            value={changelog}
            onChange={(e) => setChangelog(e.target.value)}
            style={{ padding: '6px 10px' }}
            required
            minLength={3}
          />
          {resource.type === RepoTypeEnum.Script && (
            <div className="stack" style={{ gap: 6, border: '1px dashed var(--border, #333)', padding: 8, borderRadius: 4 }}>
              <span className="dim" style={{ fontSize: 11 }}>script options</span>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <label style={{ fontSize: 12 }}>
                  language:
                  <select
                    value={scriptLanguage}
                    onChange={(e) => setScriptLanguage(e.target.value as '' | 'python' | 'shell')}
                    style={{ marginLeft: 4 }}
                  >
                    <option value="">(auto)</option>
                    <option value="python">python</option>
                    <option value="shell">shell</option>
                  </select>
                </label>
                <label style={{ fontSize: 12 }}>
                  input schema:
                  <select
                    value={scriptInputSchemaId}
                    onChange={(e) => setScriptInputSchemaId(e.target.value)}
                    style={{ marginLeft: 4 }}
                  >
                    <option value="">(none)</option>
                    {schemaOptions.map((s) => (
                      <option key={s.id} value={s.id}>{s.slug}</option>
                    ))}
                  </select>
                </label>
                <label style={{ fontSize: 12 }}>
                  output schema:
                  <select
                    value={scriptOutputSchemaId}
                    onChange={(e) => setScriptOutputSchemaId(e.target.value)}
                    style={{ marginLeft: 4 }}
                  >
                    <option value="">(none)</option>
                    {schemaOptions.map((s) => (
                      <option key={s.id} value={s.id}>{s.slug}</option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
          )}
          <div className="row" style={{ gap: 8 }}>
            <button type="submit" disabled={busy || !file}>
              {busy ? 'uploading…' : 'upload & publish'}
            </button>
            <span className="dim" style={{ fontSize: 12 }}>
              For folder/skill resources, upload a .zip or .tar.gz.
            </span>
          </div>
        </form>
      </section>

      {resource.type === RepoTypeEnum.Schema && activeVersion && (
        <section className="stack">
          <h2 style={{ fontSize: 14, margin: 0 }}>Schema actions</h2>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <button onClick={onDownloadJson}>download .json</button>
            <button onClick={onDownloadPydantic}>download Pydantic .py</button>
            <button onClick={onCopyPydantic}>copy Pydantic to clipboard</button>
          </div>
        </section>
      )}

      {(resource.type === RepoTypeEnum.Folder || resource.type === RepoTypeEnum.Skill) && activeVersion && (
        <>
          <section className="stack">
            <h2 style={{ fontSize: 14, margin: 0 }}>Bundle</h2>
            <div className="row" style={{ gap: 8 }}>
              <button onClick={onDownloadZip}>download .zip</button>
              <span className="dim" style={{ fontSize: 12 }}>Includes every file in the active version.</span>
            </div>
          </section>
          <section className="stack">
            <h2 style={{ fontSize: 14, margin: 0 }}>File tree</h2>
            <FolderTree resourceId={id} versionId={activeVersion.id} />
          </section>
        </>
      )}

      {resource.type === RepoTypeEnum.Script && activeVersion && (
        <section className="stack">
          <h2 style={{ fontSize: 14, margin: 0 }}>Validate sample</h2>
          {(() => {
            const meta = (activeVersion.metadata || {}) as Record<string, unknown>;
            const inId = meta.input_schema_resource_id as string | undefined;
            const outId = meta.output_schema_resource_id as string | undefined;
            const findSlug = (sid: string | undefined) =>
              sid ? (schemaOptions.find((s) => s.id === sid)?.slug || sid) : '(none)';
            return (
              <div className="dim" style={{ fontSize: 12 }}>
                bound input: <code>{findSlug(inId)}</code> · bound output: <code>{findSlug(outId)}</code>
              </div>
            );
          })()}
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <select value={direction} onChange={(e) => setDirection(e.target.value as 'input' | 'output')} style={{ padding: '6px 10px' }}>
              <option value="input">input schema</option>
              <option value="output">output schema</option>
            </select>
            <button onClick={onValidate} disabled={validating}>
              {validating ? 'validating…' : 'validate'}
            </button>
          </div>
          <textarea
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            rows={6}
            style={{ fontFamily: 'monospace', fontSize: 12, padding: 8 }}
            placeholder='{"key": "value"}'
          />
          {validateResult && (
            <div className="stack" style={{ gap: 4 }}>
              <span className={validateResult.valid ? 'pill ok' : 'pill'} style={{ alignSelf: 'flex-start', background: validateResult.valid ? undefined : 'crimson', color: validateResult.valid ? undefined : '#fff' }}>
                {validateResult.valid ? 'valid' : `${validateResult.errors.length} error(s)`}
              </span>
              {!validateResult.valid && (
                <ul style={{ fontSize: 12, margin: 0, paddingLeft: 16 }}>
                  {validateResult.errors.map((e, i) => (
                    <li key={i}><code>{e.path.join('.') || '(root)'}</code>: {e.message}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>
      )}

      {rendered && (
        <section className="stack">
          <h2 style={{ fontSize: 14, margin: 0 }}>Active content</h2>
          <KindViewer
            kind={resource.type}
            content={rendered}
            filename={(activeVersion?.source_metadata?.filename as string | undefined) ?? undefined}
          />
        </section>
      )}

      <section className="stack">
        <h2 style={{ fontSize: 14, margin: 0 }}>Versions ({versions.length})</h2>
        {versions.length === 0 ? (
          <p className="dim">No versions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Version</th>
                <th>Status</th>
                <th>Source</th>
                <th>Changelog</th>
                <th>Size</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => {
                const isActive = activeVersion?.id === v.id;
                return (
                  <tr key={v.id}>
                    <td>v{v.version_number}</td>
                    <td>
                      {isActive ? (
                        <span className="pill ok">active</span>
                      ) : v.is_draft ? (
                        <span className="tag">draft</span>
                      ) : (
                        ''
                      )}
                    </td>
                    <td className="dim" style={{ fontSize: 12 }}>{v.import_source}</td>
                    <td>{v.changelog}</td>
                    <td className="dim" style={{ fontSize: 12 }}>{v.byte_size}</td>
                    <td className="dim" style={{ fontSize: 12 }}>{fmtDate(v.created_at)}</td>
                    <td>
                      {!isActive && (
                        <div className="row" style={{ gap: 4 }}>
                          {v.is_draft ? (
                            <button onClick={() => onPublish(v.id)}>publish</button>
                          ) : (
                            <button onClick={() => onRollback(v.version_number)}>rollback</button>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
