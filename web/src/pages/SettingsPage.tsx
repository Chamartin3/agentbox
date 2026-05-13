import { useEffect, useState } from 'react';
import RunnerProfilesPage from './RunnerProfilesPage';
import SettingsBaseTab, { RuntimeDefaultsForm, type ToastState } from './SettingsBaseTab';
import SettingsApiTokensTab from './SettingsApiTokensTab';
import Toast from '../components/Toast';

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

function SubSection({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
      <h3 style={{ margin: 0 }}>{title}</h3>
      {hint && <p className="dim" style={{ fontSize: 12, margin: 0 }}>{hint}</p>}
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const [toast, setToast] = useState<ToastState>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="stack">
      <h1>Settings</h1>
      <Section title="Base">
        <SettingsBaseTab />
      </Section>
      <Section title="API tokens">
        <SettingsApiTokensTab />
      </Section>
      <Section title="Runner profiles">
        <SubSection
          title="Runtime defaults"
          hint="Default model per backend + runner timeout. Backends consult these on every run."
        >
          <RuntimeDefaultsForm onToast={setToast} />
        </SubSection>
        <SubSection title="Profiles">
          <RunnerProfilesPage embedded />
        </SubSection>
      </Section>
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
