import { useState } from 'react';
import { Link } from 'react-router-dom';
import { repoApi, RepoResource, RepoType } from '../api/repo';
import DataTable, { ColumnDef } from '../components/common/DataTable';

// Canonical resource types. Mirrors backend `ResourceType` StrEnum
// (core/constants.py). Single source of truth across UI + API.
const TYPE_OPTIONS: Array<{ value: RepoType | ''; label: string }> = [
  { value: '', label: 'all' },
  { value: 'document', label: 'document' },
  { value: 'folder', label: 'folder' },
  { value: 'skill', label: 'skill' },
  { value: 'schema', label: 'schema' },
  { value: 'script', label: 'script' },
];

const TYPE_COLORS: Record<RepoType, { bg: string; fg: string }> = {
  document: { bg: '#dbeafe', fg: '#1e3a8a' },
  folder:   { bg: '#fef3c7', fg: '#92400e' },
  skill:    { bg: '#dcfce7', fg: '#14532d' },
  schema:   { bg: '#ede9fe', fg: '#4c1d95' },
  script:   { bg: '#fee2e2', fg: '#7f1d1d' },
};

function fmtDate(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString();
}

function parseTags(t: string | null | undefined): string[] {
  if (!t) return [];
  try {
    const arr = JSON.parse(t);
    if (Array.isArray(arr)) return arr.filter((x) => typeof x === 'string');
  } catch {
    // fall through
  }
  return t.split(',').map((s) => s.trim()).filter(Boolean);
}

export default function ResourcesPage() {
  const [typeFilter, setTypeFilter] = useState<RepoType | ''>('');
  const [tagFilter, setTagFilter] = useState<string>('');

  const columns: ColumnDef<RepoResource>[] = [
    {
      key: 'name',
      header: 'Name',
      sortable: true,
      accessor: (r) => r.display_name || r.slug,
      render: (r) => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Link to={`/workspaces/resources/${r.id}`} style={{ fontWeight: 600 }}>
            {r.display_name || r.slug}
          </Link>
          <span className="dim" style={{ fontSize: 11, fontFamily: 'monospace' }}>
            {r.slug}
          </span>
          {r.description ? (
            <span className="dim" style={{ fontSize: 12 }}>
              {r.description.length > 80
                ? `${r.description.slice(0, 80)}…`
                : r.description}
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      sortable: true,
      accessor: (r) => r.type,
      render: (r) => {
        const c = TYPE_COLORS[r.type] || { bg: '#f3f4f6', fg: '#374151' };
        return (
          <button
            type="button"
            onClick={() => setTypeFilter(r.type)}
            className="pill"
            style={{
              background: c.bg,
              color: c.fg,
              border: 'none',
              cursor: 'pointer',
              padding: '2px 8px',
              fontSize: 12,
            }}
            title={`filter by type: ${r.type}`}
          >
            {r.type}
          </button>
        );
      },
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (r) => {
        const tags = parseTags(r.tags);
        if (tags.length === 0) return <span className="dim">—</span>;
        return (
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {tags.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTagFilter(t)}
                className="tag"
                style={{
                  background: 'transparent',
                  border: '1px solid #d1d5db',
                  cursor: 'pointer',
                  padding: '1px 6px',
                  fontSize: 11,
                  borderRadius: 4,
                }}
                title={`filter by tag: ${t}`}
              >
                {t}
              </button>
            ))}
          </div>
        );
      },
    },
    {
      key: 'updated_at',
      header: 'Updated',
      sortable: true,
      accessor: (r) => r.updated_at,
      render: (r) => (
        <span className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {fmtDate(r.updated_at)}
        </span>
      ),
    },
  ];

  const activeChips = [
    typeFilter && { key: `t:${typeFilter}`, label: `type: ${typeFilter}`, clear: () => setTypeFilter('') },
    tagFilter && { key: `g:${tagFilter}`, label: `tag: ${tagFilter}`, clear: () => setTagFilter('') },
  ].filter(Boolean) as Array<{ key: string; label: string; clear: () => void }>;

  return (
    <div className="stack">
      <div className="row between">
        <h1>Resources</h1>
      </div>

      {/* Type chip bar — replaces dropdown */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="dim" style={{ fontSize: 12, marginRight: 4 }}>type:</span>
        {TYPE_OPTIONS.map((o) => {
          const active = typeFilter === o.value;
          const c = o.value ? TYPE_COLORS[o.value as RepoType] : null;
          return (
            <button
              key={o.value || 'all'}
              type="button"
              onClick={() => setTypeFilter(o.value)}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                borderRadius: 12,
                border: active ? '2px solid #1f2937' : '1px solid #d1d5db',
                background: active && c ? c.bg : '#fff',
                color: active && c ? c.fg : '#374151',
                cursor: 'pointer',
                fontWeight: active ? 600 : 400,
              }}
            >
              {o.label}
            </button>
          );
        })}
      </div>

      {activeChips.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="dim" style={{ fontSize: 12 }}>active filters:</span>
          {activeChips.map((c) => (
            <span
              key={c.key}
              style={{
                padding: '2px 8px',
                fontSize: 11,
                background: '#f3f4f6',
                borderRadius: 12,
                display: 'inline-flex',
                gap: 4,
                alignItems: 'center',
              }}
            >
              {c.label}
              <button
                type="button"
                onClick={c.clear}
                style={{
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 12,
                  lineHeight: 1,
                  padding: 0,
                }}
                aria-label={`clear ${c.label}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <DataTable<RepoResource>
        mode="server"
        columns={columns}
        rowKey={(r) => r.id}
        pageSize={25}
        searchPlaceholder="search name, slug…"
        emptyMessage="No resources found."
        refreshKey={`${typeFilter}|${tagFilter}`}
        fetcher={({ q, limit, offset }) => {
          const search = [q, tagFilter ? `tag:${tagFilter}` : ''].filter(Boolean).join(' ');
          return repoApi
            .list({
              type: typeFilter || undefined,
              q: search || undefined,
              limit,
              offset,
            })
            .then((res) => {
              // tag filter is client-side until the backend supports it
              const items = tagFilter
                ? res.items.filter((r) => parseTags(r.tags).includes(tagFilter))
                : res.items;
              return { items, total: res.total ?? items.length };
            });
        }}
      />
    </div>
  );
}
