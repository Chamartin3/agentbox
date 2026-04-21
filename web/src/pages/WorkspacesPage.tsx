import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

interface WorkspaceItem {
  name: string;
  path: string;
  description?: string;
  kind: string;
  agents: string[];
  agent_count: number;
  file_count: number;
  skill_count: number;
  exists: boolean;
}

export default function WorkspacesPage() {
  const [workspaces, setWorkspaces] = useState<WorkspaceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.listWorkspaces()
      .then((data) => setWorkspaces(data as WorkspaceItem[]))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="stack">
      <h1>Workspaces</h1>

      {loading ? (
        <p className="dim">loading…</p>
      ) : workspaces.length === 0 ? (
        <p className="dim">No named workspaces declared in agentbox.toml.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Agents</th>
              <th>Files</th>
              <th>Skills</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {workspaces.map((w) => (
              <tr key={w.name}>
                <td>
                  <Link to={`/workspaces/${w.name}`}>
                    <strong>{w.name}</strong>
                  </Link>
                </td>
                <td>
                  {w.agents.length === 0 ? (
                    <span className="dim">none</span>
                  ) : (
                    <span className="dim">{w.agents.join(', ')}</span>
                  )}
                </td>
                <td>{w.file_count}</td>
                <td>{w.skill_count}</td>
                <td>
                  {w.exists ? (
                    <span className="pill" style={{ background: '#d1fae5', color: '#065f46' }}>ready</span>
                  ) : (
                    <span className="pill" style={{ background: '#fee2e2', color: '#991b1b' }}>missing</span>
                  )}
                </td>
                <td>
                  <Link to={`/workspaces/${w.name}`}>open →</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
