import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, AgentDef } from '../api/client';

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentDef[]>([]);

  useEffect(() => {
    api.listAgents().then(setAgents).catch(console.error);
  }, []);

  return (
    <div className="stack">
      <h1>Agents</h1>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Runner</th>
            <th>Model</th>
            <th>Session</th>
            <th>Workspace</th>
            <th>Description</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {agents.map((a) => (
            <tr key={a.id}>
              <td><Link to={`/agents/${a.id}`}><strong>{a.id}</strong></Link></td>
              <td><span className="tag">{a.runner.kind}</span></td>
              <td className="dim">{a.runner.model || '—'}</td>
              <td className="dim">{a.session_mode}</td>
              <td className="dim">
                {a.workspace === '<ephemeral>'
                  ? <span className="pill eph">ephemeral</span>
                  : (a.workspace || <span className="dim">auto</span>)}
              </td>
              <td>{a.description}</td>
              <td>
                <Link to={`/runs?agent=${encodeURIComponent(a.id)}`} title="view runs">
                  runs →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
