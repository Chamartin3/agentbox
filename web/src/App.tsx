import { lazy, Suspense, useEffect } from 'react';
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import logoUrl from '../../src/agentbox/ui/assets/logo.svg';

const ActivityPage = lazy(() => import('./pages/ActivityPage'));
const RunsPage = lazy(() => import('./pages/RunsPage'));
const RunDetailPage = lazy(() => import('./pages/RunDetailPage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const AgentDetailPage = lazy(() => import('./pages/AgentDetailPage'));
const AgentVersionDiff = lazy(() => import('./pages/AgentVersionDiff'));
const AgentVersionDetailPage = lazy(() => import('./pages/AgentVersionDetailPage'));
const AgentNew = lazy(() => import('./pages/AgentNew'));
const WorkspacesSection = lazy(() => import('./pages/WorkspacesSection'));
const WorkspaceDetailPage = lazy(() => import('./pages/WorkspaceDetailPage'));
const ResourceDetailPage = lazy(() => import('./pages/ResourceDetailPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

export default function App() {
  // The backend only serves /assets/*, so point the favicon at the bundled logo URL.
  useEffect(() => {
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) {
      link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
    }
    link.type = 'image/svg+xml';
    link.href = logoUrl;
  }, []);

  return (
    <>
      <header className="app-header">
        <span className="brand">
          <img src={logoUrl} alt="" className="brand-logo" />
          <strong>AgentBox</strong>
        </span>
        <nav className="row" style={{ gap: 16 }}>
          <NavLink to="/" end>activity</NavLink>
          <NavLink to="/agents">agents</NavLink>
          <NavLink to="/runs">runs</NavLink>
          <NavLink to="/workspaces">workspaces</NavLink>
          <NavLink to="/settings">settings</NavLink>
        </nav>
      </header>
      <main>
        <Suspense fallback={<p className="dim" style={{ padding: 16 }}>loading…</p>}>
        <Routes>
          <Route path="/" element={<ActivityPage />} />
          <Route path="/runs" element={<RunsPage />} />
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

          {/* Settings — credentials, runner profiles, general, deployment are subtabs. */}
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/settings/:tab" element={<SettingsPage />} />

          {/* Legacy redirects (credentials + runner profiles moved into Settings). */}
          <Route path="/credentials" element={<Navigate to="/settings/runner-profiles" replace />} />
          <Route path="/runs/profiles" element={<Navigate to="/settings/runner-profiles" replace />} />
          <Route path="/runners" element={<Navigate to="/settings/runner-profiles" replace />} />
          <Route path="/runner-profiles" element={<Navigate to="/settings/runner-profiles" replace />} />
          <Route path="/resources" element={<Navigate to="/workspaces/resources" replace />} />
          <Route path="/resources/:id" element={<LegacyResourceRedirect />} />
        </Routes>
        </Suspense>
      </main>
    </>
  );
}

function LegacyResourceRedirect() {
  const id = window.location.pathname.split('/').pop() ?? '';
  return <Navigate to={`/workspaces/resources/${id}`} replace />;
}
