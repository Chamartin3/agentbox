import { useEffect, useMemo, useState } from 'react';

type Visibility = 'both' | 'claude_only' | 'agents_only' | 'hidden';

interface Section {
  id: string;
  title: string;
  body_markdown: string;
  visibility: Visibility;
}

interface Command {
  label: string;
  command: string;
  description: string;
}

interface EnvDocContent {
  project_name: string;
  overview: string;
  working_directory_layout: string | null;
  conventions: string[];
  commands: Command[];
  verification: string[] | null;
  sections: Section[];
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
  const [tab, setTab] = useState<'edit' | 'claude' | 'agents'>('edit');
  const [previews, setPreviews] = useState<{ claude_md: string; agents_md: string } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api<{ active: { content_json: EnvDocContent } | null }>(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc`,
      );
      setContent(data.active ? { ...EMPTY, ...data.active.content_json } : null);
      setDirty(false);
      setPreviews(null);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [workspaceId]);

  const createBlank = () => {
    setContent({ ...EMPTY, project_name: workspaceId });
    setDirty(true);
    setTab('edit');
  };

  const update = (patch: Partial<EnvDocContent>) => {
    setContent((prev) => (prev ? { ...prev, ...patch } : prev));
    setDirty(true);
    setPreviews(null);
  };

  const save = async () => {
    if (!content) return;
    const reason = window.prompt('Reason for env-doc change:', 'updated env doc');
    if (!reason || reason.trim().length < 3) return;
    setBusy(true);
    try {
      await api(`/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc`, {
        method: 'PUT',
        body: JSON.stringify({ content, reason: reason.trim(), publish: true }),
      });
      await load();
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const preview = async () => {
    if (!content) return;
    setBusy(true);
    try {
      const data = await api<{ claude_md: string; agents_md: string }>(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/env-doc/preview`,
        { method: 'POST', body: JSON.stringify({ content }) },
      );
      setPreviews(data);
      setTab('claude');
    } catch (e) {
      alert(String(e));
    } finally {
      setBusy(false);
    }
  };

  const addSection = () => {
    if (!content) return;
    const id = `section-${content.sections.length + 1}`;
    update({
      sections: [
        ...content.sections,
        { id, title: 'New section', body_markdown: '', visibility: 'both' },
      ],
    });
  };

  const updateSection = (i: number, patch: Partial<Section>) => {
    if (!content) return;
    const next = content.sections.slice();
    next[i] = { ...next[i], ...patch };
    update({ sections: next });
  };

  const removeSection = (i: number) => {
    if (!content) return;
    update({ sections: content.sections.filter((_, idx) => idx !== i) });
  };

  const moveSection = (i: number, dir: -1 | 1) => {
    if (!content) return;
    const j = i + dir;
    if (j < 0 || j >= content.sections.length) return;
    const next = content.sections.slice();
    [next[i], next[j]] = [next[j], next[i]];
    update({ sections: next });
  };

  const conventionsText = useMemo(
    () => (content?.conventions ?? []).join('\n'),
    [content?.conventions],
  );

  if (loading) return <p className="dim">loading env-doc…</p>;
  if (error) return <p style={{ color: 'crimson', fontSize: 12 }}>{error}</p>;

  if (!content) {
    return (
      <div className="stack" style={{ gap: 12 }}>
        <p className="dim">No env-doc found for this workspace.</p>
        <div>
          <button onClick={createBlank} className="primary">
            create env doc
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row between">
        <div className="row" style={{ gap: 6 }}>
          <button onClick={() => setTab('edit')} className={tab === 'edit' ? 'primary' : ''}>
            edit
          </button>
          <button
            onClick={() => (previews ? setTab('claude') : preview())}
            className={tab === 'claude' ? 'primary' : ''}
            disabled={busy}
          >
            CLAUDE.md
          </button>
          <button
            onClick={() => (previews ? setTab('agents') : preview())}
            className={tab === 'agents' ? 'primary' : ''}
            disabled={busy}
          >
            AGENTS.md
          </button>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <button onClick={preview} disabled={busy}>preview</button>
          <button onClick={save} disabled={busy || !dirty} className="primary">
            {busy ? 'saving…' : dirty ? 'save & publish' : 'saved'}
          </button>
        </div>
      </div>

      {tab === 'edit' && (
        <div className="stack" style={{ gap: 12 }}>
          <div className="row" style={{ gap: 8 }}>
            <label style={{ flex: 1 }}>
              <div className="dim" style={{ fontSize: 11, marginBottom: 4 }}>Project name</div>
              <input
                type="text"
                value={content.project_name}
                onChange={(e) => update({ project_name: e.target.value })}
                style={{ width: '100%', padding: '6px 8px', fontSize: 12 }}
              />
            </label>
          </div>

          <label>
            <div className="dim" style={{ fontSize: 11, marginBottom: 4 }}>Overview</div>
            <textarea
              rows={3}
              value={content.overview}
              onChange={(e) => update({ overview: e.target.value })}
              style={{ width: '100%', padding: '6px 8px', fontSize: 12, fontFamily: 'inherit' }}
            />
          </label>

          <label>
            <div className="dim" style={{ fontSize: 11, marginBottom: 4 }}>
              Conventions <span>(one per line)</span>
            </div>
            <textarea
              rows={4}
              value={conventionsText}
              onChange={(e) =>
                update({
                  conventions: e.target.value.split('\n').map((s) => s.trimEnd()).filter(Boolean),
                })
              }
              style={{ width: '100%', padding: '6px 8px', fontSize: 12, fontFamily: 'monospace' }}
            />
          </label>

          <div>
            <div className="row between" style={{ marginBottom: 6 }}>
              <strong style={{ fontSize: 12 }}>Sections ({content.sections.length})</strong>
              <button onClick={addSection}>+ add section</button>
            </div>
            {content.sections.length === 0 ? (
              <p className="dim" style={{ fontSize: 11 }}>No sections yet.</p>
            ) : (
              <div className="stack" style={{ gap: 8 }}>
                {content.sections.map((s, i) => (
                  <div key={s.id} className="section" style={{ padding: 8 }}>
                    <div className="row between" style={{ marginBottom: 6 }}>
                      <input
                        type="text"
                        value={s.title}
                        onChange={(e) => updateSection(i, { title: e.target.value })}
                        placeholder="title"
                        style={{ flex: 1, padding: '4px 6px', fontSize: 12, fontWeight: 600 }}
                      />
                      <select
                        value={s.visibility}
                        onChange={(e) => updateSection(i, { visibility: e.target.value as Visibility })}
                        style={{ fontSize: 11, marginLeft: 6 }}
                      >
                        <option value="both">both</option>
                        <option value="claude_only">claude only</option>
                        <option value="agents_only">agents only</option>
                        <option value="hidden">hidden</option>
                      </select>
                      <button onClick={() => moveSection(i, -1)} disabled={i === 0} title="up">↑</button>
                      <button onClick={() => moveSection(i, 1)} disabled={i === content.sections.length - 1} title="down">↓</button>
                      <button onClick={() => removeSection(i)} style={{ color: 'crimson', fontSize: 11 }}>remove</button>
                    </div>
                    <textarea
                      rows={4}
                      value={s.body_markdown}
                      onChange={(e) => updateSection(i, { body_markdown: e.target.value })}
                      placeholder="markdown body"
                      style={{ width: '100%', padding: '6px 8px', fontSize: 12, fontFamily: 'monospace' }}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="row" style={{ gap: 16 }}>
            <label className="row" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={content.references.include_skills}
                onChange={(e) =>
                  update({
                    references: { ...content.references, include_skills: e.target.checked },
                  })
                }
              />
              <span style={{ fontSize: 12 }}>include skills in references</span>
            </label>
            <label className="row" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={content.references.include_folders}
                onChange={(e) =>
                  update({
                    references: { ...content.references, include_folders: e.target.checked },
                  })
                }
              />
              <span style={{ fontSize: 12 }}>include folders in references</span>
            </label>
          </div>
        </div>
      )}

      {tab !== 'edit' && (
        <div className="code-block">
          <div className="code-block-bar">
            <span className="dim" style={{ fontSize: 11 }}>
              {tab === 'claude' ? 'CLAUDE.md preview' : 'AGENTS.md preview'}
            </span>
          </div>
          <pre style={{ maxHeight: 500, overflow: 'auto', fontSize: 12, padding: '12px 14px', margin: 0 }}>
            {previews
              ? (tab === 'claude' ? previews.claude_md : previews.agents_md)
              : 'click preview to render…'}
          </pre>
        </div>
      )}
    </div>
  );
}
