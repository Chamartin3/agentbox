import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, AgentDef } from '../api/client';

function PromptDrawer({ agent, onClose }: { agent: AgentDef; onClose: () => void }) {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getAgent(agent.id)
      .then((r) => setPrompt(r.prompt || ''))
      .catch(() => setPrompt(''))
      .finally(() => setLoading(false));
  }, [agent.id]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <strong>{agent.id}</strong>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, color: 'var(--fg-muted)' }}>✕</button>
        </div>
        {agent.description && (
          <p className="dim" style={{ marginTop: 0, marginBottom: 12, fontSize: 13 }}>{agent.description}</p>
        )}
        <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
          <span className="tag">{agent.runner.kind}</span>
          {agent.runner.model && <span className="tag">{agent.runner.model}</span>}
          {agent.workspace && <span className="tag">{agent.workspace}</span>}
        </div>
        <div className="code-block">
          <div className="code-block-bar">
            <span className="dim" style={{ fontSize: 11 }}>system prompt</span>
            {agent.prompt_path && (
              <span className="dim" style={{ fontSize: 11 }}>{agent.prompt_path}</span>
            )}
          </div>
          {loading
            ? <pre style={{ padding: '12px 14px', margin: 0, color: 'var(--fg-muted)', fontSize: 12 }}>loading…</pre>
            : prompt
              ? <pre style={{ padding: '12px 14px', margin: 0, whiteSpace: 'pre', wordBreak: 'normal', fontSize: 12, maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>{prompt}</pre>
              : <pre style={{ padding: '12px 14px', margin: 0, color: 'var(--fg-muted)', fontSize: 12 }}>no prompt</pre>
          }
        </div>
        <div style={{ marginTop: 14, textAlign: 'right' }}>
          <Link to={`/agents/${agent.id}`} style={{ fontSize: 13 }}>open full detail →</Link>
        </div>
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentDef[]>([]);
  const [selected, setSelected] = useState<AgentDef | null>(null);

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
            <tr
              key={a.id}
              style={{ cursor: 'pointer' }}
              onClick={() => setSelected(a)}
            >
              <td onClick={(e) => e.stopPropagation()}>
                <Link to={`/agents/${a.id}`}><strong>{a.id}</strong></Link>
              </td>
              <td><span className="tag">{a.runner.kind}</span></td>
              <td className="dim">{a.runner.model || '—'}</td>
              <td className="dim">{a.session_mode}</td>
              <td className="dim">
                {a.workspace === '<ephemeral>'
                  ? <span className="pill eph">ephemeral</span>
                  : (a.workspace || <span className="dim">auto</span>)}
              </td>
              <td>{a.description}</td>
              <td onClick={(e) => e.stopPropagation()}>
                <Link to={`/runs?agent=${encodeURIComponent(a.id)}`} title="view runs">
                  runs →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {selected && (
        <PromptDrawer agent={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
