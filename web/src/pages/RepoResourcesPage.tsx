import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { repoApi, RepoResource, RepoType } from '../api/repo';
import DataTable, { ColumnDef } from '../components/DataTable';
import ResourcePicker from '../components/ResourcePicker';

const TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'all types' },
  { value: 'document', label: 'document' },
  { value: 'folder', label: 'folder' },
  { value: 'skill', label: 'skill' },
  { value: 'schema', label: 'schema' },
  { value: 'script', label: 'script' },
];

function fmtDate(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

function parseTags(tags: string | null | undefined): string[] {
  if (!tags) return [];
  try {
    const parsed = JSON.parse(tags);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return tags.split(',').map((t) => t.trim()).filter(Boolean);
  }
}

export default function RepoResourcesPage() {
  const navigate = useNavigate();
  const [typeFilter, setTypeFilter] = useState('');
  const [creating, setCreating] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  const columns: ColumnDef<RepoResource>[] = [
    {
      key: 'slug',
      header: 'Slug',
      render: (r) => (
        <Link to={`/workspaces/resources/${encodeURIComponent(r.id)}`}>
          <strong>{r.slug}</strong>
        </Link>
      ),
    },
    { key: 'type', header: 'Type', render: (r) => <span className="tag">{r.type}</span> },
    { key: 'display_name', header: 'Name', render: (r) => r.display_name },
    {
      key: 'tags',
      header: 'Tags',
      render: (r) => (
        <>
          {parseTags(r.tags).map((t) => (
            <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>
          ))}
        </>
      ),
    },
    {
      key: 'updated_at',
      header: 'Updated',
      render: (r) => (
        <span className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {fmtDate(r.updated_at)}
        </span>
      ),
    },
    {
      key: 'open',
      header: '',
      render: (r) => (
        <Link to={`/workspaces/resources/${encodeURIComponent(r.id)}`}>detail →</Link>
      ),
    },
  ];

  return (
    <div className="stack">
      <div className="row between">
        <h1>Shared Resources</h1>
        <button className="primary" onClick={() => setCreating(true)}>
          + new resource
        </button>
      </div>
      <DataTable<RepoResource>
        mode="server"
        columns={columns}
        rowKey={(r) => r.id}
        pageSize={25}
        searchPlaceholder="search slug, name…"
        emptyMessage="No resources found."
        refreshKey={`${typeFilter}:${refreshTick}`}
        toolbarExtra={
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{ padding: '6px 10px', fontSize: 13 }}
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        }
        fetcher={({ q, limit, offset }) =>
          repoApi
            .list({
              q: q || undefined,
              type: (typeFilter as RepoType) || undefined,
              limit,
              offset,
            })
            .then((res) => ({ items: res.items, total: res.total ?? res.items.length }))
        }
      />
      {creating && (
        <ResourcePicker
          allowUpload
          defaultShowUpload
          title="Create a new resource"
          onPick={(rs) => {
            setCreating(false);
            setRefreshTick((n) => n + 1);
            const created = rs[0];
            if (created) navigate(`/workspaces/resources/${encodeURIComponent(created.id)}`);
          }}
          onClose={() => setCreating(false)}
        />
      )}
    </div>
  );
}
