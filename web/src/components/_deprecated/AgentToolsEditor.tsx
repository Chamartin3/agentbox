import { useEffect, useState } from 'react';
import { api } from '../api/client';

interface ToolGroup {
  name: string;
  tools: string[];
  claude_tools: string[];
  opencode_tools: string[];
  tool_count: number;
  kind: string;
  active: boolean;
  fully_active: boolean;
}

interface Props {
  workspace: string | null;
  onError: (msg: string) => void;
  onSaved: (msg: string) => void;
}

export default function AgentToolsEditor({ workspace, onError, onSaved }: Props) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [groups, setGroups] = useState<ToolGroup[]>([]);
  const [builtins, setBuiltins] = useState<string[]>([]);
  const [allowed, setAllowed] = useState<Set<string>>(new Set());
  const [permissions, setPermissions] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setGroups([]);
    setBuiltins([]);
    setAllowed(new Set());
    setDirty(false);
    if (!workspace || workspace === '<ephemeral>') return;
    setLoading(true);
    Promise.all([
      api.getWorkspaceMcpToolsByName(workspace),
      api.getWorkspacePermissionsByName(workspace),
    ])
      .then(([mcp, perms]) => {
        const g = ((mcp as Record<string, unknown>).groups as ToolGroup[]) || [];
        const b = ((mcp as Record<string, unknown>).builtin_tools as string[]) || [];
        const p = (perms as Record<string, unknown>).permissions as Record<string, unknown>;
        setGroups(g);
        setBuiltins(b);
        setPermissions(p || {});
        setAllowed(new Set((p?.allowed_tools as string[]) || []));
      })
      .catch((e) => onError(`tools load failed: ${String(e)}`))
      .finally(() => setLoading(false));
  }, [workspace]);

  const toggleGroup = (g: ToolGroup) => {
    const next = new Set(allowed);
    const fullyOn = g.claude_tools.every((t) => next.has(t));
    if (fullyOn) {
      g.claude_tools.forEach((t) => next.delete(t));
    } else {
      g.claude_tools.forEach((t) => next.add(t));
    }
    setAllowed(next);
    setDirty(true);
  };

  const toggleBuiltin = (t: string) => {
    const next = new Set(allowed);
    if (next.has(t)) next.delete(t);
    else next.add(t);
    setAllowed(next);
    setDirty(true);
  };

  const save = async () => {
    if (!workspace) return;
    setSaving(true);
    try {
      await api.setWorkspacePermissionsByName(workspace, {
        ...permissions,
        allowed_tools: Array.from(allowed),
      });
      setDirty(false);
      onSaved(`tools updated for workspace "${workspace}"`);
    } catch (e) {
      onError(`tools save failed: ${String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  if (!workspace) {
    return (
      <section className="section">
        <h2 style={{ border: 'none', margin: 0 }}>Allowed Tools</h2>
        <p className="dim" style={{ marginTop: 8 }}>
          Assign a workspace to manage tool permissions.
        </p>
      </section>
    );
  }

  if (workspace === '&lt;ephemeral&gt;' || workspace === '<ephemeral>') {
    return (
      <section className="section">
        <h2 style={{ border: 'none', margin: 0 }}>Allowed Tools</h2>
        <p className="dim" style={{ marginTop: 8 }}>
          Ephemeral workspaces have no persisted permissions.
        </p>
      </section>
    );
  }

  return (
    <section className="section">
      <div className="row between" style={{ marginBottom: 8 }}>
        <h2 style={{ border: 'none', margin: 0 }}>
          Allowed Tools
          {dirty && <span className="dirty" style={{ marginLeft: 8 }}>● unsaved</span>}
        </h2>
        <button className="primary" onClick={save} disabled={!dirty || saving}>
          {saving ? 'saving…' : 'save tools'}
        </button>
      </div>
      <p className="dim" style={{ marginTop: 0, fontSize: 12 }}>
        Tool permissions are stored on the workspace <code>{workspace}</code> and shared by
        every agent assigned to it.
      </p>

      {loading ? (
        <p className="dim">loading…</p>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          {builtins.length > 0 && (
            <div>
              <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                Built-in
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                {builtins.map((t) => (
                  <label key={t} className="row" style={{ gap: 6, cursor: 'pointer', fontSize: 13 }}>
                    <input
                      type="checkbox"
                      checked={allowed.has(t)}
                      onChange={() => toggleBuiltin(t)}
                    />
                    <span>{t}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {groups.length > 0 && (
            <div>
              <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                MCP tool groups
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
                {groups.map((g) => {
                  const fullyOn = g.claude_tools.every((t) => allowed.has(t));
                  const partiallyOn = !fullyOn && g.claude_tools.some((t) => allowed.has(t));
                  return (
                    <label key={g.name} className="row" style={{ gap: 6, cursor: 'pointer', fontSize: 13 }} title={g.tools.join(', ')}>
                      <input
                        type="checkbox"
                        checked={fullyOn}
                        ref={(el) => {
                          if (el) el.indeterminate = partiallyOn;
                        }}
                        onChange={() => toggleGroup(g)}
                      />
                      <span>
                        {g.name}
                        <span className="dim" style={{ marginLeft: 4, fontSize: 11 }}>
                          ({g.tool_count})
                        </span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {groups.length === 0 && builtins.length === 0 && (
            <p className="dim">No tool groups available.</p>
          )}
        </div>
      )}
    </section>
  );
}
