import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, SharedResource, ResourceKind } from '../api/client';
import { ResourceKind as ResourceKindEnum } from '../api/enums';
import DataTable, { ColumnDef } from '../components/DataTable';

const KIND_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'all kinds' },
  ...Object.values(ResourceKindEnum).map((k) => ({ value: k, label: k })),
];

function fmtDate(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

export default function ResourcesPage() {
  const [kindFilter, setKindFilter] = useState('');

  const columns: ColumnDef<SharedResource>[] = [
    {
      key: 'id',
      header: 'ID / Slug',
      render: (r) => (
        <Link to={`/workspaces/resources/${r.id}`}>
          <strong>{r.id}</strong>
        </Link>
      ),
    },
    { key: 'kind', header: 'Kind', render: (r) => <span className="tag">{r.kind}</span> },
    { key: 'name', header: 'Name', render: (r) => r.name },
    {
      key: 'version',
      header: 'Active Version',
      render: (r) =>
        r.is_active ? (
          <span className="pill ok">v{r.version}</span>
        ) : (
          <span className="dim">v{r.version}</span>
        ),
    },
    {
      key: 'tags',
      header: 'Tags',
      render: (r) => (
        <>
          {(r.tags || []).map((t) => (
            <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>
          ))}
        </>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: (r) => (
        <span className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
          {fmtDate(r.created_at)}
        </span>
      ),
    },
    {
      key: 'open',
      header: '',
      render: (r) => <Link to={`/workspaces/resources/${r.id}`}>detail →</Link>,
    },
  ];

  return (
    <div className="stack">
      <div className="row between">
        <h1>Shared Resources</h1>
      </div>
      <DataTable<SharedResource>
        mode="server"
        columns={columns}
        rowKey={(r) => `${r.id}-${r.version}`}
        pageSize={25}
        searchPlaceholder="search id, name…"
        emptyMessage="No resources found."
        refreshKey={kindFilter}
        toolbarExtra={
          <select
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            style={{ padding: '6px 10px', fontSize: 13 }}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        }
        fetcher={({ q, limit, offset }) =>
          api
            .listResources({
              q: q || undefined,
              kind: (kindFilter as ResourceKind) || undefined,
              limit,
              offset,
            })
            .then((res) => ({ items: res.items, total: res.total ?? res.items.length }))
        }
      />
    </div>
  );
}
