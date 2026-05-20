import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import ActivityPage from './pages/ActivityPage';
import RunsPage from './pages/RunsPage';
import RunDetailPage from './pages/RunDetailPage';
import AgentsPage from './pages/AgentsPage';
import AgentDetailPage from './pages/AgentDetailPage';
import AgentVersionDiff from './pages/AgentVersionDiff';
import AgentVersionDetailPage from './pages/AgentVersionDetailPage';
import AgentNew from './pages/AgentNew';
import WorkspacesSection from './pages/WorkspacesSection';
import WorkspaceDetailPage from './pages/WorkspaceDetailPage';
import ResourceDetailPage from './pages/ResourceDetailPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <>
      <header className="app-header">
        <strong>agentbox</strong>
        <nav className="row" style={{ gap: 16 }}>
          <NavLink to="/" end>activity</NavLink>
          <NavLink to="/agents">agents</NavLink>
          <NavLink to="/runs">runs</NavLink>
          <NavLink to="/workspaces">workspaces</NavLink>
          <NavLink to="/settings">settings</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<ActivityPage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/profiles" element={<RunsPage />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/agents/new" element={<AgentNew />} />
          <Route path="/agents/:id" element={<AgentDetailPage />} />
          <Route path="/agents/:id/versions/diff" element={<AgentVersionDiff />} />
          <Route path="/agents/:id/versions/:vid" element={<AgentVersionDetailPage />} />
          <Route path="/agents/:id/:tab" element={<AgentDetailPage />} />

          {/* Workspaces section: workspaces table + resources sub-section. */}
          <Route path="/workspaces" element={<WorkspacesSection />} />
          <Route path="/workspaces/resources" element={<WorkspacesSection />} />
          <Route path="/workspaces/:id" element={<WorkspaceDetailPage />} />
          <Route path="/workspaces/resources/:id" element={<ResourceDetailPage />} />

          {/* Settings (providers/runners are a sub-section). */}
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/base" element={<SettingsPage />} />
          <Route path="/settings/api-tokens" element={<SettingsPage />} />

          {/* Legacy redirects (one-release grace period). */}
          <Route path="/runners" element={<Navigate to="/runs/profiles" replace />} />
          <Route path="/runner-profiles" element={<Navigate to="/runs/profiles" replace />} />
          <Route path="/settings/providers" element={<Navigate to="/runs/profiles" replace />} />
          <Route path="/resources" element={<Navigate to="/workspaces/resources" replace />} />
          <Route path="/resources/:id" element={<LegacyResourceRedirect />} />
        </Routes>
      </main>
    </>
  );
}

function LegacyResourceRedirect() {
  const id = window.location.pathname.split('/').pop() ?? '';
  return <Navigate to={`/workspaces/resources/${id}`} replace />;
}
