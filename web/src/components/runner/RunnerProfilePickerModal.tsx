import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, type RunnerBackend, type RunnerProfile, type RunnerProvider } from '../../api/client';
import RunnerProfileModal from './RunnerProfileModal';
import { harnessLabel, providerLabel } from './runnerLabels';
import './runner.css';

interface Props {
  boundId: string | null;
  /** Called with a profile id, or '' to clear back to system default. */
  onPick: (profileId: string) => void;
  /** Called after a brand-new profile is created (so the caller can bind it). */
  onCreated: (profile: RunnerProfile) => void;
  onClose: () => void;
  busy?: boolean;
}

/** Self-contained "pick an existing profile (filterable table) or create a new
 *  one" modal. Fetches the profile list + the lookups the create form needs. */
export default function RunnerProfilePickerModal({ boundId, onPick, onCreated, onClose, busy }: Props) {
  const [profiles, setProfiles] = useState<RunnerProfile[]>([]);
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [backends, setBackends] = useState<RunnerBackend[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const [list, provs, bes] = await Promise.all([
        api.listRunnerProfiles(),
        api.listRunnerProviders().catch(() => []),
        api.listRunnerBackends().catch(() => []),
      ]);
      if (cancelled) return;
      setProfiles(list);
      setProviders(provs);
      setBackends(bes);
      setLoading(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return profiles;
    return profiles.filter((p) =>
      [p.name, p.id, p.backend, p.provider, p.model, harnessLabel(p.backend), providerLabel(p)]
        .some((v) => (v ?? '').toString().toLowerCase().includes(q)),
    );
  }, [profiles, query]);

  return (
    <>
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal modal--wide" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3 style={{ margin: 0 }}>Runner profile</h3>
            <button className="modal-close" onClick={onClose} aria-label="Close">✕</button>
          </div>
          <div className="modal-body">
            {loading ? (
              <p className="dim">loading…</p>
            ) : (
              <>
                <input
                  className="profile-table-filter"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="filter profiles by name, harness, provider, model…"
                  autoFocus
                />
                <table className="profile-table">
                  <thead>
                    <tr>
                      <th>Profile</th>
                      <th>Harness</th>
                      <th>Provider</th>
                      <th>Model</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      className={`pick-row${boundId == null ? ' selected' : ''}`}
                      onClick={() => !busy && onPick('')}
                    >
                      <td className="pick-name">
                        System default
                        {boundId == null && <span className="pick-check">✓</span>}
                      </td>
                      <td className="dim" colSpan={3}>inherit the server default</td>
                    </tr>
                    {filtered.map((p) => (
                      <tr
                        key={p.id}
                        className={`pick-row${boundId === p.id ? ' selected' : ''}`}
                        onClick={() => !busy && onPick(p.id)}
                      >
                        <td className="pick-name">
                          {p.name || p.id}
                          {p.is_system_default && <span className="dim" style={{ marginLeft: 6, fontWeight: 400 }}>[default]</span>}
                          {boundId === p.id && <span className="pick-check">✓</span>}
                        </td>
                        <td><span className="runner-badge runner-badge--harness" data-harness={p.backend ?? undefined}>{harnessLabel(p.backend)}</span></td>
                        <td><span className="runner-badge runner-badge--provider" data-provider={providerLabel(p).toLowerCase()}>{providerLabel(p)}</span></td>
                        <td><span className="runner-badge runner-badge--model">{p.model || 'default'}</span></td>
                      </tr>
                    ))}
                    {filtered.length === 0 && (
                      <tr><td colSpan={4} className="dim" style={{ textAlign: 'center', padding: 16 }}>no profiles match</td></tr>
                    )}
                  </tbody>
                </table>
              </>
            )}
          </div>
          <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Link to="/runners" className="dim" style={{ fontSize: 12 }}>manage profiles →</Link>
            <button className="primary" onClick={() => setShowCreate(true)} disabled={loading}>+ create new profile</button>
          </div>
        </div>
      </div>

      {showCreate && (
        <RunnerProfileModal
          mode="create"
          backends={backends}
          providers={providers}
          onClose={() => setShowCreate(false)}
          onSaved={(p) => { setShowCreate(false); onCreated(p); }}
          onError={() => { /* surfaced inside the create modal */ }}
        />
      )}
    </>
  );
}
