import { useEffect, useState, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import CodeMirror from '@uiw/react-codemirror';
import { markdown } from '@codemirror/lang-markdown';
import { javascript } from '@codemirror/lang-javascript';
import { githubDark } from '@uiw/codemirror-theme-github';
import { repoApi, RepoResource, RepoVersion, RepoType } from '../api/repo';
import { RepoType as RepoTypeEnum } from '../api/enums';

function roleFromTags(tags: string | null | undefined): string | undefined {
  if (!tags) return undefined;
  const KNOWN = ['system_fragment', 'system_prompt', 'output_schema', 'input_schema'];
  let parts: string[] = [];
  try {
    const j = JSON.parse(tags);
    if (Array.isArray(j)) parts = j.map(String);
  } catch {
    parts = tags.split(',').map((t) => t.trim());
  }
  for (const p of parts) if (KNOWN.includes(p)) return p === 'system_prompt' ? 'system_fragment' : p;
  return undefined;
}

function fmtDate(s?: string): string {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString();
}

// Per-resource-type file picker hints. Keep these aligned with the
// upload dispatch in `onUpload` (schema → JSON, script → py/sh, folder/skill → archive).
function acceptFor(type: RepoType): string {
  switch (type) {
    case 'schema': return '.json,application/json';
    case 'script': return '.py,.sh,text/x-python,application/x-sh';
    case 'folder':
    case 'skill': return '.zip,.tar,.tgz,.gz,application/zip,application/gzip,application/x-tar';
    case 'document': return '.md,.txt,text/markdown,text/plain';
    default: return '';
  }
}

function acceptHintFor(type: RepoType): string {
  switch (type) {
    case 'schema': return '.json';
    case 'script': return '.py or .sh';
    case 'folder':
    case 'skill': return '.zip / .tar.gz';
    case 'document': return '.md / .txt';
    default: return 'any';
  }
}

function uploadHint(type: RepoType): string {
  return `Accepted: ${acceptHintFor(type)}`;
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
  constraints?: string[];
  enumValues?: unknown[];
  defaultValue?: unknown;
  examples?: unknown[];
  format?: string;
  nullable?: boolean;
  deprecated?: boolean;
}

// Pull every JSON-schema validation keyword we know how to render into
// human-friendly chips. Keywords not handled fall through silently; we
// don't try to be exhaustive, just useful.
function extractConstraints(def: Record<string, unknown>): string[] {
  const c: string[] = [];
  const push = (label: string, value: unknown) => {
    if (value !== undefined && value !== null) c.push(`${label} ${value}`);
  };
  // Numeric
  push('min', def.minimum);
  push('max', def.maximum);
  push('>', def.exclusiveMinimum);
  push('<', def.exclusiveMaximum);
  push('multipleOf', def.multipleOf);
  // String
  push('minLen', def.minLength);
  push('maxLen', def.maxLength);
  if (typeof def.pattern === 'string') c.push(`pattern /${def.pattern}/`);
  // Array
  push('minItems', def.minItems);
  push('maxItems', def.maxItems);
  if (def.uniqueItems === true) c.push('unique');
  // Object
  push('minProps', def.minProperties);
  push('maxProps', def.maxProperties);
  if (def.additionalProperties === false) c.push('no extra props');
  // Const
  if ('const' in def) c.push(`const ${JSON.stringify(def.const)}`);
  // readOnly / writeOnly
  if (def.readOnly === true) c.push('readOnly');
  if (def.writeOnly === true) c.push('writeOnly');
  return c;
}

// Pydantic-generated JSON schemas use $defs + $ref; we resolve refs against
// the root schema's $defs/definitions so nested objects/arrays expand
// instead of bottoming out as opaque leaves.
type Defs = Record<string, Record<string, unknown>>;

function getDefs(root: Record<string, unknown> | null | undefined): Defs {
  if (!root) return {};
  const a = (root.$defs as Defs) || (root.definitions as Defs) || {};
  return a || {};
}

function resolveRef(def: Record<string, unknown>, defs: Defs): Record<string, unknown> {
  // Resolve a single $ref hop (e.g. "#/$defs/Foo"). Allof/oneOf get
  // simplified to the first viable branch — enough for display.
  let cur = def;
  for (let i = 0; i < 4; i++) {
    const ref = cur.$ref as string | undefined;
    if (ref) {
      const key = ref.split('/').pop() || '';
      const target = defs[key];
      if (!target) return cur;
      cur = { ...target, ...stripRef(cur) };
      continue;
    }
    const allOf = cur.allOf as Array<Record<string, unknown>> | undefined;
    if (Array.isArray(allOf) && allOf.length) {
      cur = { ...cur, ...allOf[0] };
      continue;
    }
    break;
  }
  return cur;
}

function stripRef(o: Record<string, unknown>): Record<string, unknown> {
  const { $ref: _ref, ...rest } = o;
  void _ref;
  return rest;
}

function extractProps(
  schema: Record<string, unknown> | null | undefined,
  defs: Defs = {},
): SchemaProp[] {
  if (!schema || typeof schema !== 'object') return [];
  const resolvedRoot = resolveRef(schema, defs);
  const props = (resolvedRoot.properties as Record<string, unknown>) || {};
  const required = new Set<string>(
    Array.isArray(resolvedRoot.required) ? (resolvedRoot.required as string[]) : [],
  );
  const result: SchemaProp[] = [];
  for (const [name, raw] of Object.entries(props)) {
    const rawDef = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
    const def = resolveRef(rawDef, defs);
    let type = (def.type as string) || (def.$ref ? '$ref' : 'any');
    if (Array.isArray(def.type)) type = (def.type as string[]).join('|');
    if (def.enum) type = `${type} (enum)`;
    const description = (def.description as string) || (rawDef.description as string) || '';
    const node: SchemaProp = { name, type, required: required.has(name), description };
    node.constraints = extractConstraints(def);
    if (Array.isArray(def.enum)) node.enumValues = def.enum as unknown[];
    if ('default' in def) node.defaultValue = def.default;
    if (Array.isArray(def.examples)) node.examples = def.examples as unknown[];
    if (typeof def.format === 'string') node.format = def.format;
    if (def.nullable === true) node.nullable = true;
    if (def.deprecated === true) node.deprecated = true;
    // Detect Optional[T] expressed as anyOf:[T, null] in pydantic schemas.
    const anyOf = def.anyOf as Array<Record<string, unknown>> | undefined;
    if (!node.nullable && Array.isArray(anyOf)) {
      const hasNull = anyOf.some((b) => b && (b as Record<string, unknown>).type === 'null');
      if (hasNull) node.nullable = true;
    }
    if (type === 'object' && def.properties) {
      node.children = extractProps(def, defs);
    } else if (type === 'object' && def.additionalProperties && typeof def.additionalProperties === 'object') {
      // Dict-shaped object: surface the value type so the user can see
      // what the map contains.
      const ap = resolveRef(def.additionalProperties as Record<string, unknown>, defs);
      const valueType = (ap.type as string) || (ap.$ref ? '$ref' : 'any');
      node.type = `object<string, ${valueType}>`;
      if (ap.properties) node.children = extractProps(ap, defs);
    } else if (type === 'array' && def.items && typeof def.items === 'object') {
      const items = resolveRef(def.items as Record<string, unknown>, defs);
      if (items.properties) {
        node.type = 'array<object>';
        node.children = extractProps(items, defs);
      } else if (items.type) {
        node.type = `array<${items.type as string}>`;
      } else if (items.enum) {
        node.type = 'array (enum)';
      }
    }
    result.push(node);
  }
  return result;
}

// Foreground tints for JSON-schema types — dark-theme palette tuned to
// the app's --bg-elevated chip background. The base keyword maps to the
// color; composite labels like 'array<string>' fall back to neutral fg.
const SCHEMA_TYPE_FG: Record<string, string> = {
  object:  '#d2a8ff', // purple
  array:   '#ffa657', // amber
  string:  '#7ee787', // green
  number:  '#79c0ff', // blue
  integer: '#79c0ff',
  boolean: '#ff7b72', // red
  null:    'var(--fg-muted)',
};

function typeFg(t: string): string {
  const base = t.replace(/<.*$/, '').split('|')[0];
  return SCHEMA_TYPE_FG[base] || 'var(--fg-muted)';
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span
      className="tag"
      style={{
        color: typeFg(type),
        fontFamily: 'monospace',
        fontSize: 11,
      }}
    >
      {type}
    </span>
  );
}

function SchemaNode({ prop, depth }: { prop: SchemaProp; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = (prop.children?.length ?? 0) > 0;
  return (
    <div
      style={{
        borderLeft: depth > 0 ? '1px solid var(--border)' : 'none',
        marginLeft: depth > 0 ? 12 : 0,
        paddingLeft: depth > 0 ? 10 : 0,
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'baseline',
          padding: '4px 0',
          cursor: hasChildren ? 'pointer' : 'default',
        }}
        onClick={() => hasChildren && setOpen((v) => !v)}
      >
        <span
          style={{
            display: 'inline-block',
            width: 12,
            color: 'var(--fg-muted)',
            fontSize: 10,
            transform: hasChildren && open ? 'rotate(90deg)' : 'none',
            transition: 'transform 80ms ease',
          }}
        >
          {hasChildren ? '▶' : ''}
        </span>
        <code style={{ fontWeight: 600, fontSize: 13, color: 'var(--fg)' }}>
          {prop.name}
        </code>
        <TypeBadge type={prop.type} />
        {prop.format && (
          <span className="tag" style={{ color: '#79c0ff', fontSize: 10 }}>
            {prop.format}
          </span>
        )}
        {prop.nullable && (
          <span className="tag" style={{ color: 'var(--fg-muted)', fontSize: 10 }}>
            nullable
          </span>
        )}
        {prop.required && (
          <span
            className="tag"
            style={{
              color: '#ff7b72',
              fontSize: 10,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}
          >
            required
          </span>
        )}
        {prop.deprecated && (
          <span
            className="tag"
            style={{
              color: '#ffa657',
              fontSize: 10,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: 0.5,
            }}
          >
            deprecated
          </span>
        )}
        {prop.description && (
          <span className="dim" style={{ fontSize: 12, marginLeft: 4 }}>
            — {prop.description}
          </span>
        )}
      </div>
      {(prop.constraints?.length ||
        prop.enumValues ||
        prop.defaultValue !== undefined ||
        prop.examples) && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 4,
            paddingLeft: 20,
            paddingBottom: 4,
          }}
        >
          {prop.constraints?.map((c) => (
            <span
              key={c}
              className="tag"
              style={{ color: 'var(--fg-muted)', fontSize: 10, fontFamily: 'monospace' }}
            >
              {c}
            </span>
          ))}
          {prop.enumValues && (
            <span
              className="tag"
              style={{ color: '#d2a8ff', fontSize: 10, fontFamily: 'monospace' }}
              title={JSON.stringify(prop.enumValues)}
            >
              enum: {formatEnum(prop.enumValues)}
            </span>
          )}
          {prop.defaultValue !== undefined && (
            <span
              className="tag"
              style={{ color: '#7ee787', fontSize: 10, fontFamily: 'monospace' }}
            >
              default {JSON.stringify(prop.defaultValue)}
            </span>
          )}
          {prop.examples && prop.examples.length > 0 && (
            <span
              className="tag"
              style={{ color: 'var(--fg-muted)', fontSize: 10, fontFamily: 'monospace' }}
              title={JSON.stringify(prop.examples)}
            >
              e.g. {JSON.stringify(prop.examples[0])}
              {prop.examples.length > 1 ? ` (+${prop.examples.length - 1})` : ''}
            </span>
          )}
        </div>
      )}
      {hasChildren && open && (
        <div>
          {prop.children!.map((c) => (
            <SchemaNode key={`${prop.name}.${c.name}`} prop={c} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function formatEnum(values: unknown[]): string {
  const max = 4;
  const head = values.slice(0, max).map((v) => JSON.stringify(v)).join(' | ');
  return values.length > max ? `${head} | …(+${values.length - max})` : head;
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
  const props = extractProps(parsed, getDefs(parsed));
  const rootType = parsed?.type as string | undefined;
  const rootTitle = parsed?.title as string | undefined;
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, alignItems: 'center' }}>
        {rootTitle && <strong style={{ fontSize: 14 }}>{rootTitle}</strong>}
        {rootType && <TypeBadge type={rootType} />}
        <span style={{ flex: 1 }} />
        <button onClick={() => setShowRaw((v) => !v)}>
          {showRaw ? 'show tree' : 'show raw JSON'}
        </button>
      </div>
      {showRaw || parseError || props.length === 0 ? (
        <pre style={PRE_STYLE}>{parseError ? `Parse error: ${parseError}\n\n${content}` : content}</pre>
      ) : (
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '6px 12px',
            background: 'var(--bg-elevated)',
          }}
        >
          {props.map((p) => (
            <SchemaNode key={p.name} prop={p} depth={0} />
          ))}
        </div>
      )}
    </div>
  );
}

function looksLikeJsonSchema(content: string): boolean {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('{')) return false;
  try {
    const o = JSON.parse(content);
    return !!o && typeof o === 'object' && (
      '$schema' in o || 'properties' in o || (o.type === 'object' && 'required' in o)
    );
  } catch {
    return false;
  }
}

function DocumentViewer({ content, role }: { content: string; role?: string }) {
  const isSystemFragment = role === 'system_fragment';
  const isSchemaShape = !isSystemFragment && looksLikeJsonSchema(content);

  if (isSchemaShape) {
    return (
      <div className="stack" style={{ gap: 6 }}>
        <div
          className="dim"
          style={{
            fontSize: 12,
            padding: '6px 10px',
            background: 'rgba(80, 160, 200, 0.12)',
            borderLeft: '3px solid #4ea1c4',
            borderRadius: 2,
          }}
        >
          Detected JSON schema — rendering as schema table.
        </div>
        <SchemaViewer content={content} />
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      {isSystemFragment && (
        <div
          className="dim"
          style={{
            fontSize: 12,
            padding: '6px 10px',
            background: 'rgba(120, 80, 200, 0.12)',
            borderLeft: '3px solid #845ec2',
            borderRadius: 2,
          }}
        >
          System prompt fragment — composed into the agent's system prompt at run time.
        </div>
      )}
      <CodeMirror
        value={content}
        extensions={[markdown()]}
        theme={githubDark}
        editable={false}
        basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
        style={{ maxHeight: 480, overflow: 'auto', fontSize: 12 }}
      />
    </div>
  );
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
      <CodeMirror
        value={body.trim()}
        extensions={[markdown()]}
        theme={githubDark}
        editable={false}
        basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
        style={{ maxHeight: 480, overflow: 'auto', fontSize: 12 }}
      />
    </div>
  );
}

function ScriptViewer({ content, filename }: { content: string; filename?: string }) {
  const ext = (filename || '').toLowerCase().split('.').pop() || '';
  let language = 'text';
  const extensions = [];
  if (ext === 'py') language = 'python';
  else if (ext === 'js' || ext === 'mjs' || ext === 'cjs') {
    language = 'javascript';
    extensions.push(javascript());
  } else if (ext === 'ts' || ext === 'tsx') {
    language = 'typescript';
    extensions.push(javascript({ typescript: true }));
  } else if (ext === 'sh' || ext === 'bash') language = 'shell';
  return (
    <div className="stack" style={{ gap: 4 }}>
      <span className="dim" style={{ fontSize: 12 }}>language: {language}</span>
      <CodeMirror
        value={content}
        extensions={extensions}
        theme={githubDark}
        editable={false}
        basicSetup={{ lineNumbers: true, foldGutter: true, highlightActiveLine: false }}
        style={{ maxHeight: 520, overflow: 'auto', fontSize: 12 }}
      />
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
  const [uploadOpen, setUploadOpen] = useState(false);
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
      setUploadOpen(false);
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
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <button type="button" onClick={() => setUploadOpen(true)}>
            Upload new version
          </button>
          <span className="dim" style={{ fontSize: 12 }}>
            {uploadHint(resource.type)}
          </span>
        </div>
      </section>

      {uploadOpen && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
          }}
          onClick={() => { if (!busy) setUploadOpen(false); }}
          onKeyDown={(e) => { if (e.key === 'Escape' && !busy) setUploadOpen(false); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--bg, #1a1a1a)', borderRadius: 6,
              width: 'min(560px, 92vw)', maxHeight: '85vh', overflow: 'auto',
              padding: 16, border: '1px solid var(--border, #333)',
            }}
          >
            <div className="row between" style={{ alignItems: 'center', marginBottom: 12 }}>
              <h2 style={{ fontSize: 16, margin: 0 }}>Upload new version</h2>
              <button type="button" onClick={() => setUploadOpen(false)} disabled={busy}>×</button>
            </div>
            <form onSubmit={onUpload} className="stack">
              <label className="stack" style={{ gap: 4 }}>
                <span className="dim" style={{ fontSize: 12 }}>
                  file ({acceptHintFor(resource.type)})
                </span>
                <input
                  type="file"
                  accept={acceptFor(resource.type)}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
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
              <div className="row" style={{ gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" onClick={() => setUploadOpen(false)} disabled={busy}>
                  cancel
                </button>
                <button type="submit" disabled={busy || !file}>
                  {busy ? 'uploading…' : 'upload & publish'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

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
            role={
              ((activeVersion?.metadata as Record<string, unknown> | undefined)?.role as string | undefined)
              ?? roleFromTags(resource.tags)
            }
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
