import { NavLink, Route, Routes } from 'react-router-dom';
import ActivityPage from './pages/ActivityPage';
import RunsPage from './pages/RunsPage';
import RunDetailPage from './pages/RunDetailPage';
import AgentsPage from './pages/AgentsPage';
import AgentDetailPage from './pages/AgentDetailPage';
import AgentVersions from './pages/AgentVersions';
import AgentVersionDiff from './pages/AgentVersionDiff';
import AgentNew from './pages/AgentNew';
import WorkspacesPage from './pages/WorkspacesPage';
import WorkspaceDetailPage from './pages/WorkspaceDetailPage';

export default function App() {
  return (
    <>
      <header className="app-header">
        <strong>agentbox</strong>
        <nav className="row" style={{ gap: 16 }}>
          <NavLink to="/" end>activity</NavLink>
          <NavLink to="/runs">runs</NavLink>
          <NavLink to="/agents">agents</NavLink>
          <NavLink to="/workspaces">workspaces</NavLink>
          <a href="/health" target="_blank" rel="noreferrer">health</a>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ActivityPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/new" element={<AgentNew />} />
          <Route path="/agents/:id" element={<AgentDetailPage />} />
          <Route path="/agents/:id/versions" element={<AgentVersions />} />
          <Route path="/agents/:id/versions/diff" element={<AgentVersionDiff />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:id" element={<WorkspaceDetailPage />} />
        </Routes>
      </main>
    </>
  );
}
