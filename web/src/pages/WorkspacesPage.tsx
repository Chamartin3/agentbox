import { Link } from 'react-router-dom';
import { api } from '../api/client';
import DataTable, { ColumnDef } from '../components/DataTable';

interface WorkspaceItem {
  name: string;
  path: string;
  description?: string;
  kind: string;
  agents: string[];
  agent_count: number;
  file_count: number;
  skill_count: number;
  resource_count: number;
  exists: boolean;
}

export default function WorkspacesPage() {
  const columns: ColumnDef<WorkspaceItem>[] = [
    {
      key: 'name',
      header: 'Name',
      sortable: true,
      accessor: (w) => w.name,
      render: (w) => (
        <Link to={`/workspaces/${w.name}`}>
          <strong>{w.name}</strong>
        </Link>
      ),
    },
    {
      key: 'agents',
      header: 'Agents',
      sortable: true,
      accessor: (w) => w.agent_count,
      render: (w) =>
        w.agents.length === 0 ? (
          <span className="dim">none</span>
        ) : (
          <span className="dim">{w.agents.join(', ')}</span>
        ),
    },
    { key: 'file_count', header: 'Files', sortable: true, accessor: (w) => w.file_count, align: 'right' },
    { key: 'skill_count', header: 'Skills', sortable: true, accessor: (w) => w.skill_count, align: 'right' },
    {
      key: 'resource_count',
      header: 'Resources',
      sortable: true,
      accessor: (w) => w.resource_count ?? 0,
      align: 'right',
    },
    {
      key: 'exists',
      header: 'Status',
      sortable: true,
      accessor: (w) => (w.exists ? 'ready' : 'missing'),
      render: (w) =>
        w.exists ? (
          <span className="pill" style={{ background: '#d1fae5', color: '#065f46' }}>ready</span>
        ) : (
          <span className="pill" style={{ background: '#fee2e2', color: '#991b1b' }}>missing</span>
        ),
    },
    {
      key: 'open',
      header: '',
      render: (w) => <Link to={`/workspaces/${w.name}`}>open →</Link>,
    },
  ];

  return (
    <div className="stack">
      <h1>Workspaces</h1>
      <DataTable<WorkspaceItem>
        mode="server"
        columns={columns}
        rowKey={(w) => w.name}
        pageSize={20}
        searchPlaceholder="search workspaces…"
        emptyMessage="No workspaces found."
        fetcher={({ q, sort, order, limit, offset }) =>
          api
            .listWorkspacesPaginated({ q, sort, order, limit, offset })
            .then((res) => ({ items: res.items as unknown as WorkspaceItem[], total: res.total }))
        }
      />
    </div>
  );
}
