import { useEffect, useState } from 'react';
import {
  api,
  ApiError,
  type RunnerBackend,
  type RunnerProfile,
  type RunnerProvider,
} from '../api/client';
import Toast from '../components/Toast';
import RunnerProfileModal from '../components/RunnerProfileModal';
import { apiTokens as apiTokensClient } from '../api/api_tokens';
import './RunnerProfilesPage.css';

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) {
    const d = e.detail as { detail?: string } | string | undefined;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.detail === 'string') return d.detail;
    return `${fallback} (HTTP ${e.status})`;
  }
  return e instanceof Error ? e.message : fallback;
}

type FormMode = 'create' | 'edit' | null;

export default function RunnerProfilesPage({ embedded = false }: { embedded?: boolean } = {}) {
  const [profiles, setProfiles] = useState<RunnerProfile[]>([]);
  const [providers, setProviders] = useState<RunnerProvider[]>([]);
  const [backends, setBackends] = useState<RunnerBackend[]>([]);
  const [loading, setLoading] = useState(true);
  const [formMode, setFormMode] = useState<FormMode>(null);
  const [editingProfile, setEditingProfile] = useState<RunnerProfile | undefined>(undefined);
  const [toast, setToast] = useState<{ kind: 'ok' | 'error'; msg: string } | null>(null);
  const [apiTokens, setApiTokens] = useState<Array<{ id: string; name: string; environment: string }>>([]);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadProfiles();
    loadProviders();
    loadBackends();
    apiTokensClient.listSafe().then(setApiTokens);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const loadProfiles = async () => {
    try {
      setProfiles(await api.listRunnerProfiles());
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to load profiles') });
    } finally {
      setLoading(false);
    }
  };

  const loadProviders = async () => {
    try {
      setProviders(await api.listRunnerProviders());
    } catch (e) {
      console.error('failed to load providers', e);
    }
  };

  const refreshProviders = async () => {
    setRefreshing(true);
    try {
      const res = await api.refreshRunnerProviders();
      await loadProviders();
      const count = res.opencode?.length ?? 0;
      setToast({
        kind: 'ok',
        msg: count
          ? `refreshed: ${count} opencode provider(s), model cache cleared`
          : 'refreshed: no opencode providers discovered, model cache cleared',
      });
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to refresh providers') });
    } finally {
      setRefreshing(false);
    }
  };

  const loadBackends = async () => {
    try {
      setBackends(await api.listRunnerBackends());
    } catch (e) {
      console.error('failed to load backends', e);
    }
  };

  const openCreate = () => {
    setEditingProfile(undefined);
    setFormMode('create');
  };

  const openEdit = (p: RunnerProfile) => {
    setEditingProfile(p);
    setFormMode('edit');
  };

  const closeForm = () => {
    setFormMode(null);
    setEditingProfile(undefined);
  };

  const handleSaved = (_profile: RunnerProfile) => {
    setToast({ kind: 'ok', msg: formMode === 'create' ? 'profile created' : 'profile updated' });
    closeForm();
    loadProfiles();
  };

  const handleDelete = async (id: string) => {
    if (!confirm(`delete profile "${id}"?`)) return;
    try {
      await api.deleteRunnerProfile(id);
      setToast({ kind: 'ok', msg: 'profile deleted' });
      closeForm();
      loadProfiles();
    } catch (e) {
      setToast({ kind: 'error', msg: errMsg(e, 'failed to delete profile') });
    }
  };

  if (loading) {
    return (
      <div className="stack">
        {!embedded && <h1>Runner Profiles</h1>}
        <p className="dim">loading…</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {embedded ? <span /> : <h1>Runner Profiles</h1>}
        <div className="row" style={{ gap: 8 }}>
          <button
            onClick={refreshProviders}
            disabled={refreshing}
            title="Re-run opencode model discovery and clear provider model caches"
          >
            {refreshing ? 'Refreshing…' : '↻ Refresh providers'}
          </button>
          <button onClick={openCreate}>+ Create Profile</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Backend</th>
            <th>Provider</th>
            <th>Model</th>
            <th>Enabled</th>
            <th style={{ width: 1 }}></th>
          </tr>
        </thead>
        <tbody>
          {profiles.length === 0 ? (
            <tr>
              <td colSpan={6} className="dim" style={{ textAlign: 'center', padding: 24 }}>
                no runner profiles
              </td>
            </tr>
          ) : (
            profiles.map((p) => (
              <tr key={p.id}>
                <td>
                  <button
                    onClick={() => openEdit(p)}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      color: 'var(--link)',
                      cursor: 'pointer',
                      font: 'inherit',
                    }}
                  >
                    <strong>{p.name}</strong>
                  </button>
                </td>
                <td><span className="tag">{p.backend}</span></td>
                <td>{p.provider ? <span className="tag">{p.provider}</span> : <span className="dim">—</span>}</td>
                <td>{p.model || <span className="dim">—</span>}</td>
                <td>
                  {p.is_enabled ? (
                    <span className="pill default">yes</span>
                  ) : (
                    <span className="pill disabled">no</span>
                  )}
                </td>
                <td>
                  <div className="row" style={{ gap: 6 }}>
                    <button onClick={() => openEdit(p)} style={{ fontSize: 12, padding: '2px 8px' }}>
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(p.id)}
                      style={{ fontSize: 12, padding: '2px 8px', border: '1px solid var(--error)', color: 'var(--error)', background: 'none' }}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      {formMode && (
        <RunnerProfileModal
          mode={formMode}
          profile={editingProfile}
          backends={backends}
          providers={providers}
          apiTokens={apiTokens}
          onClose={closeForm}
          onSaved={handleSaved}
          onDelete={formMode === 'edit' ? handleDelete : undefined}
          onError={(msg) => setToast({ kind: 'error', msg })}
        />
      )}

      {toast && <Toast kind={toast.kind} msg={toast.msg} />}
    </div>
  );
}
