import SettingsBaseTab from './SettingsBaseTab';
import SettingsApiTokensTab from './SettingsApiTokensTab';
import SettingsSecretsTab from './SettingsSecretsTab';
import SettingsDeploymentTab from './SettingsDeploymentTab';

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

export default function SettingsPage() {
  return (
    <div className="stack">
      <h1>Settings</h1>
      <Section title="Base">
        <SettingsBaseTab />
      </Section>
      <Section title="Secrets">
        <SettingsSecretsTab />
      </Section>
      <Section title="API tokens">
        <SettingsApiTokensTab />
      </Section>
      <Section title="Deployment">
        <SettingsDeploymentTab />
      </Section>
    </div>
  );
}
