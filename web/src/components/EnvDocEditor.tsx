import { useEffect, useState } from 'react';
import MarkdownEditor from './MarkdownEditor';

interface EnvDocContent {
  project_name: string;
  overview: string;
  working_directory_layout: string | null;
  conventions: string[];
  commands: { label: string; command: string; description: string }[];
  verification: string[] | null;
  sections: { id: string; title: string; body_markdown: string; visibility: string }[];
  references: {
    include_skills: boolean;
    include_folders: boolean;
    custom_links: { label: string; url: string }[];
  };
}

const EMPTY: EnvDocContent = {
  project_name: '',
  overview: '',
  working_directory_layout: null,
  conventions: [],
  commands: [],
  verification: null,
  sections: [],
  references: { include_skills: true, include_folders: true, custom_links: [] },
};

interface Props {
  workspaceId: string;
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${text}`);
  }
  return resp.json();
}

export default function EnvDocEditor({ workspaceId }: Props) {
  const [content, setContent] = useState<EnvDocContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [changelog, setChangelog] = useState('');
  const [activeVersion, setActiveVersion] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{
        active: { content_json: EnvDocContent; version?: number } | null;
      }>(`/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc`);
      setContent(
        data.active
          ? { ...EMPTY, ...data.active.content_json }
          : { ...EMPTY, project_name: workspaceId },
      );
      setActiveVersion(data.active?.version ?? null);
      setDirty(false);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const updateOverview = (overview: string) => {
    setContent((prev) => (prev ? { ...prev, overview } : prev));
    setDirty(true);
  };

  const save = async (publish: boolean) => {
    if (!content) return;
    const reason = (changelog.trim() || (publish ? 'publish env doc' : 'save env doc draft'));
    setBusy(true);
    try {
      await api(`/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc`, {
        method: 'PUT',
        body: JSON.stringify({ content, reason, publish }),
      });
      setChangelog('');
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (dirty && !busy) void save(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, busy, content, changelog]);

  if (loading) return <p className="dim">loading env-doc…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;
  if (!content) return null;

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>Environment documentation</h2>
        <div className="row" style={{ gap: 6 }}>
          {activeVersion != null && (
            <span className="dim" style={{ fontSize: 11 }}>
              active v{activeVersion}
              {dirty && <span className="dirty"> · unsaved</span>}
            </span>
          )}
          <button
            onClick={() => void save(false)}
            disabled={!dirty || busy}
            className="primary"
            style={{ fontSize: 11, padding: '4px 10px' }}
          >
            Save Draft
          </button>
        </div>
      </div>

      <div
        style={{
          resize: 'vertical',
          overflow: 'auto',
          height: 260,
          minHeight: 120,
          border: '1px solid var(--border)',
          borderRadius: 4,
        }}
      >
        <MarkdownEditor value={content.overview} onChange={updateOverview} height="100%" />
      </div>

      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        <input
          type="text"
          value={changelog}
          onChange={(e) => setChangelog(e.target.value)}
          placeholder="Changelog (optional)"
          style={{ flex: 1, maxWidth: 300 }}
        />
        <button onClick={() => void save(true)} disabled={busy}>
          Publish
        </button>
      </div>

      <p className="dim" style={{ marginTop: 12, fontSize: 11 }}>
        Rendered into CLAUDE.md / AGENTS.md inside the workdir on every run.
      </p>
    </section>
  );
}
