import WorkspacesPage from './WorkspacesPage';
import ResourcesPage from './ResourcesPage';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="stack" style={{ gap: 12, marginTop: 24 }}>
      <h2 style={{ margin: 0, borderBottom: '1px solid #30363d', paddingBottom: 6 }}>
        {title}
      </h2>
      {children}
    </section>
  );
}

/**
 * Workspaces section — renders the workspaces table and the resources
 * table stacked vertically on a single page.
 */
export default function WorkspacesSection() {
  return (
    <div className="stack">
      <WorkspacesPage />
      <Section title="Resources">
        <ResourcesPage />
      </Section>
    </div>
  );
}
