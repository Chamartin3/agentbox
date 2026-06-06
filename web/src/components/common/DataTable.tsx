import { ReactNode, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Generic, reusable table with header-click sort (tri-state), debounced
 * search box, and prev/next pagination.
 *
 * Two modes via the `mode` prop:
 *  - `'client'` (default): pass `data`; the table filters/sorts/paginates in
 *    memory using each column's `accessor` and `searchable` flag.
 *  - `'server'`: pass a `fetcher` that takes `{q, sort, order, limit, offset}`
 *    and returns `{items, total}`. The table re-fetches on state changes.
 */

export type SortOrder = 'asc' | 'desc' | null;

export interface ColumnDef<T> {
  key: string;
  header: ReactNode;
  /** Renderer for the cell. Defaults to `String(accessor(row))`. */
  render?: (row: T) => ReactNode;
  /** Sort/search accessor. Required if sortable or searchable. */
  accessor?: (row: T) => string | number | null | undefined;
  sortable?: boolean;
  searchable?: boolean;
  align?: 'left' | 'right' | 'center';
  width?: string | number;
}

interface BaseProps<T> {
  columns: ColumnDef<T>[];
  rowKey: (row: T) => string;
  pageSize?: number;
  searchPlaceholder?: string;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  /** Extra UI rendered to the right of the search box. */
  toolbarExtra?: ReactNode;
  /** Initial sort. */
  defaultSort?: { key: string; order: 'asc' | 'desc' };
}

interface ClientProps<T> extends BaseProps<T> {
  mode?: 'client';
  data: T[];
  loading?: boolean;
}

interface ServerProps<T> extends BaseProps<T> {
  mode: 'server';
  fetcher: (params: {
    q: string;
    sort: string | null;
    order: SortOrder;
    limit: number;
    offset: number;
  }) => Promise<{ items: T[]; total: number }>;
  /** Bumping this causes a re-fetch. */
  refreshKey?: unknown;
}

export type DataTableProps<T> = ClientProps<T> | ServerProps<T>;

function sortIndicator(order: SortOrder): string {
  if (order === 'asc') return ' ▲';
  if (order === 'desc') return ' ▼';
  return '';
}

function compareVals(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

export default function DataTable<T>(props: DataTableProps<T>) {
  const {
    columns,
    rowKey,
    pageSize = 20,
    searchPlaceholder = 'search…',
    emptyMessage = 'no results',
    onRowClick,
    toolbarExtra,
    defaultSort,
  } = props;

  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState<string | null>(defaultSort?.key ?? null);
  const [order, setOrder] = useState<SortOrder>(defaultSort?.order ?? null);
  const [page, setPage] = useState(1);

  // Debounce search input
  useEffect(() => {
    const t = window.setTimeout(() => setQ(qInput), 250);
    return () => window.clearTimeout(t);
  }, [qInput]);

  useEffect(() => setPage(1), [q, sort, order]);

  // Server mode state
  const [serverData, setServerData] = useState<{ items: T[]; total: number }>({
    items: [],
    total: 0,
  });
  const [serverLoading, setServerLoading] = useState(false);
  const lastReq = useRef(0);

  useEffect(() => {
    if (props.mode !== 'server') return;
    const reqId = ++lastReq.current;
    setServerLoading(true);
    props
      .fetcher({
        q,
        sort,
        order,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      .then((res) => {
        if (lastReq.current === reqId) setServerData(res);
      })
      .catch((err) => console.error(err))
      .finally(() => {
        if (lastReq.current === reqId) setServerLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    q,
    sort,
    order,
    page,
    pageSize,
    props.mode,
    (props as ServerProps<T>).refreshKey,
  ]);

  // Client-side processing
  const { rows, total, loading } = useMemo(() => {
    if (props.mode === 'server') {
      return {
        rows: serverData.items,
        total: serverData.total,
        loading: serverLoading,
      };
    }
    const data = props.data;
    const filtered = q
      ? data.filter((row) =>
          columns.some((c) => {
            if (!c.searchable || !c.accessor) return false;
            const v = c.accessor(row);
            return v != null && String(v).toLowerCase().includes(q.toLowerCase());
          }),
        )
      : data;
    let sorted = filtered;
    if (sort && order) {
      const col = columns.find((c) => c.key === sort);
      if (col?.accessor) {
        const dir = order === 'asc' ? 1 : -1;
        sorted = [...filtered].sort(
          (a, b) => dir * compareVals(col.accessor!(a), col.accessor!(b)),
        );
      }
    }
    const start = (page - 1) * pageSize;
    return {
      rows: sorted.slice(start, start + pageSize),
      total: sorted.length,
      loading: props.loading ?? false,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    props.mode === 'client' ? props.data : null,
    serverData,
    serverLoading,
    q,
    sort,
    order,
    page,
    pageSize,
    columns,
  ]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(page, totalPages);

  function toggleSort(key: string) {
    const col = columns.find((c) => c.key === key);
    if (!col?.sortable) return;
    if (sort !== key) {
      setSort(key);
      setOrder('asc');
      return;
    }
    setOrder((o) => (o === 'asc' ? 'desc' : o === 'desc' ? null : 'asc'));
    if (order === 'desc') setSort(null);
  }

  return (
    <div className="stack">
      <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="search"
          placeholder={searchPlaceholder}
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
          style={{ flex: '1 1 240px', padding: '6px 10px', fontSize: 13 }}
        />
        {toolbarExtra}
        <span className="dim" style={{ fontSize: 12 }}>
          {total.toLocaleString()} {total === 1 ? 'row' : 'rows'}
          {loading ? ' · loading…' : ''}
        </span>
      </div>
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                onClick={c.sortable ? () => toggleSort(c.key) : undefined}
                style={{
                  cursor: c.sortable ? 'pointer' : undefined,
                  textAlign: c.align,
                  width: c.width,
                  userSelect: 'none',
                }}
              >
                {c.header}
                {sort === c.key && sortIndicator(order)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && !loading && (
            <tr>
              <td colSpan={columns.length} className="dim" style={{ textAlign: 'center', padding: 20 }}>
                {emptyMessage}
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              style={onRowClick ? { cursor: 'pointer' } : undefined}
            >
              {columns.map((c) => {
                const content = c.render
                  ? c.render(row)
                  : c.accessor
                    ? String(c.accessor(row) ?? '')
                    : null;
                return (
                  <td key={c.key} style={{ textAlign: c.align }}>
                    {content}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {totalPages > 1 && (
        <div className="row between" style={{ marginTop: 4 }}>
          <span className="dim" style={{ fontSize: 12 }}>
            page {safePage} of {totalPages} · showing {rows.length} of {total}
          </span>
          <div className="row" style={{ gap: 4 }}>
            <button onClick={() => setPage(1)} disabled={safePage === 1 || loading}>«</button>
            <button onClick={() => setPage(Math.max(1, safePage - 1))} disabled={safePage === 1 || loading}>← prev</button>
            <button onClick={() => setPage(Math.min(totalPages, safePage + 1))} disabled={safePage >= totalPages || loading}>next →</button>
            <button onClick={() => setPage(totalPages)} disabled={safePage >= totalPages || loading}>»</button>
          </div>
        </div>
      )}
    </div>
  );
}
