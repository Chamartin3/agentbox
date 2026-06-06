import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import DataTable, { ColumnDef } from '../components/common/DataTable';

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
  on_disk?: boolean;
}

export default function WorkspacesPage() {
  const [refreshKey, setRefreshKey] = useState(0);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');

  const handleDelete = async (name: string) => {
    const purge = window.confirm(
      `Delete workspace "${name}"?\n\nOK = remove registry + DB state only.\n` +
      `Cancel = abort.\n\n(Files on disk are kept unless you tick "purge disk" below.)`,
    );
    if (!purge) return;
    const purgeDisk = window.confirm(`Also delete on-disk workspace directory for "${name}"?`);
    try {
      await api.deleteWorkspaceRegistry(name, purgeDisk);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      alert(`Delete failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await api.createWorkspaceRegistry({ name: newName.trim() });
      setNewName('');
      setCreating(false);
      setRefreshKey((k) => k + 1);
    } catch (e) {
      alert(`Create failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

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
      render: (w) => (
        <span style={{ whiteSpace: 'nowrap' }}>
          <Link to={`/workspaces/${w.name}`}>open →</Link>
          <button
            type="button"
            onClick={() => handleDelete(w.name)}
            style={{
              marginLeft: 12,
              padding: '2px 8px',
              fontSize: 12,
              background: 'transparent',
              border: '1px solid #fca5a5',
              color: '#b91c1c',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            delete
          </button>
        </span>
      ),
    },
  ];

  return (
    <div className="stack">
      <div className="row between">
        <h1>Workspaces</h1>
        {creating ? (
          <span style={{ display: 'inline-flex', gap: 6 }}>
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="workspace name"
              style={{ padding: '6px 10px', fontSize: 13 }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreate();
                if (e.key === 'Escape') {
                  setCreating(false);
                  setNewName('');
                }
              }}
            />
            <button type="button" onClick={handleCreate}>create</button>
            <button type="button" onClick={() => { setCreating(false); setNewName(''); }}>
              cancel
            </button>
          </span>
        ) : (
          <button type="button" onClick={() => setCreating(true)}>+ new workspace</button>
        )}
      </div>
      <DataTable<WorkspaceItem>
        mode="server"
        columns={columns}
        rowKey={(w) => w.name}
        pageSize={20}
        searchPlaceholder="search workspaces…"
        emptyMessage="No workspaces found."
        refreshKey={refreshKey}
        fetcher={({ q, sort, order, limit, offset }) =>
          api
            .listWorkspacesPaginated({ q, sort, order, limit, offset })
            .then((res) => ({ items: res.items as unknown as WorkspaceItem[], total: res.total }))
        }
      />
    </div>
  );
}
