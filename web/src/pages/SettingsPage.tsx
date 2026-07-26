import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import SettingsDeploymentTab from './SettingsDeploymentTab';
import SettingsRunnerProfilesTab from './SettingsRunnerProfilesTab';
import ProjectMcpEditor from '../components/settings/ProjectMcpEditor';
import Toast from '../components/common/Toast';

const TABS = [
  { key: 'general', label: 'General' },
  { key: 'runner-profiles', label: 'Runners & credentials' },
  { key: 'deployment', label: 'Deployment info' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

function GeneralTab() {
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);
  return (
    <section className="stack" style={{ gap: 8, border: '1px solid #30363d', padding: 12, borderRadius: 6 }}>
      <h3 style={{ margin: 0 }}>Global MCPs</h3>
      <ProjectMcpEditor
        onToast={(t) => {
          setToast(t);
          setTimeout(() => setToast(null), 4000);
        }}
      />
      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </section>
  );
}

export default function SettingsPage() {
  const { tab } = useParams<{ tab?: string }>();
  const navigate = useNavigate();
  const active: TabKey = TABS.some((t) => t.key === tab) ? (tab as TabKey) : TABS[0].key;

  return (
    <div className="stack">
      <h1>Settings</h1>
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab-button ${active === t.key ? 'active' : ''}`}
            onClick={() => navigate(`/settings/${t.key}`)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="tab-content">
        <div className="tab-pane stack" style={{ gap: 16 }}>
          {active === 'runner-profiles' && <SettingsRunnerProfilesTab />}
          {active === 'general' && <GeneralTab />}
          {active === 'deployment' && <SettingsDeploymentTab />}
        </div>
      </div>
    </div>
  );
}
