import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, SharedResource, ResourceKind } from '../api/client';

const KIND_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'all kinds' },
  { value: 'output_schema', label: 'output_schema' },
  { value: 'input_schema', label: 'input_schema' },
  { value: 'user_template', label: 'user_template' },
  { value: 'system_fragment', label: 'system_fragment' },
  { value: 'reference', label: 'reference' },
  { value: 'mcp_server', label: 'mcp_server' },
  { value: 'skill', label: 'skill' },
];

function fmtDate(s: string): string {
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString();
}

export default function ResourcesPage() {
  const [items, setItems] = useState<SharedResource[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [kindFilter, setKindFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const load = (off: number, q: string, kind: string) => {
    setLoading(true);
    api
      .listResources({
        q: q || undefined,
        kind: (kind as ResourceKind) || undefined,
        limit,
        offset: off,
      })
      .then((page) => {
        setItems(page.items);
        setTotal(page.total ?? page.items.length);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    setOffset(0);
    load(0, query, kindFilter);
  }, [query, kindFilter]);

  const goPage = (newOffset: number) => {
    setOffset(newOffset);
    load(newOffset, query, kindFilter);
  };

  const totalPages = Math.max(1, Math.ceil(total / limit));
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="stack">
      <div className="row between">
        <h1>Shared Resources</h1>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input
          type="text"
          placeholder="search id, name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{ flex: '1 1 220px', padding: '6px 10px', fontSize: 13 }}
        />
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value)}
          style={{ padding: '6px 10px', fontSize: 13 }}
        >
          {KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <span className="dim" style={{ fontSize: 12, alignSelf: 'center' }}>
          {total} total
        </span>
      </div>

      {loading ? (
        <p className="dim">loading…</p>
      ) : items.length === 0 ? (
        <p className="dim">No resources found.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>ID / Slug</th>
              <th>Kind</th>
              <th>Name</th>
              <th>Active Version</th>
              <th>Tags</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={`${r.id}-${r.version}`}>
                <td>
                  <Link to={`/resources/${r.id}`}>
                    <strong>{r.id}</strong>
                  </Link>
                </td>
                <td><span className="tag">{r.kind}</span></td>
                <td>{r.name}</td>
                <td>
                  {r.is_active ? (
                    <span className="pill ok">v{r.version}</span>
                  ) : (
                    <span className="dim">v{r.version}</span>
                  )}
                </td>
                <td>
                  {(r.tags || []).map((t) => (
                    <span key={t} className="tag" style={{ marginRight: 4 }}>{t}</span>
                  ))}
                </td>
                <td className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                  {fmtDate(r.created_at)}
                </td>
                <td>
                  <Link to={`/resources/${r.id}`}>detail →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {totalPages > 1 && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'flex-end' }}>
          <button
            onClick={() => goPage(Math.max(0, offset - limit))}
            disabled={currentPage === 1}
          >
            ← prev
          </button>
          <span className="dim" style={{ fontSize: 12 }}>
            page {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => goPage(offset + limit)}
            disabled={currentPage === totalPages}
          >
            next →
          </button>
        </div>
      )}
    </div>
  );
}
