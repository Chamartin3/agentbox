import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import EnvDocEditor from '../components/EnvDocEditor';
import WorkspaceResourcesEditor from '../components/WorkspaceResourcesEditor';
import SubagentsEditor from '../components/SubagentsEditor';
import WorkspaceMcpEditor from '../components/WorkspaceMcpEditor';
import WorkspaceHostEnvEditor from '../components/WorkspaceHostEnvEditor';

interface WorkspaceFile {
  path: string;
  size: number;
}

interface GeneratedConfig {
  path: string;
  exists: boolean;
}

interface SkillItem {
  name: string;
  path: string;
  size: number;
}

export default function WorkspaceDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingSkills, setGeneratingSkills] = useState(false);
  const [skills, setSkills] = useState<SkillItem[]>([]);

  // Permissions state — single source of truth is now the DB overlay
  // (workspace_runtime_permissions). MCP tool grants live in the DB MCP
  // override tables and are managed by <WorkspaceMcpEditor/> — they do
  // NOT belong on this page anymore.
  const [permissions, setPermissions] = useState<Record<string, any>>({});
  const [permissionsSaving, setPermissionsSaving] = useState(false);
  const [builtinTools, setBuiltinTools] = useState<string[]>([]);

  // File viewer state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [fileDirty, setFileDirty] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [ws, perms, mcp, sk] = await Promise.all([
        api.getWorkspaceByName(id),
        api.getWorkspacePermissionsByName(id),
        api.getWorkspaceMcpToolsByName(id),
        api.listWorkspaceSkillsByName(id),
      ]);
      setData(ws);
      setPermissions((perms as any).permissions || {});
      // The MCP tools endpoint still ships the built-in-tools allow-list
      // (it's the same registry); MCP groups are no longer rendered here.
      setBuiltinTools((mcp as any).builtin_tools || []);
      setSkills((sk as any).skills || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const generate = async () => {
    setGenerating(true);
    try {
      await api.generateWorkspaceConfigsByName(id);
      await load();
    } catch (e) {
      console.error(e);
    } finally {
      setGenerating(false);
    }
  };

  const generateSkills = async () => {
    setGeneratingSkills(true);
    try {
      await api.generateWorkspaceSkillsByName(id);
      await load();
    } catch (e) {
      console.error(e);
    } finally {
      setGeneratingSkills(false);
    }
  };

  const [lastAction, setLastAction] = useState<string | null>(null);

  const savePermissions = async () => {
    setPermissionsSaving(true);
    try {
      const result = await api.setWorkspacePermissionsByName(id, permissions);
      setLastAction(
        `Saved permissions + regenerated ${Object.keys((result as any).regenerated || {}).length} config files`
      );
      await load();
    } catch (e) {
      console.error(e);
    } finally {
      setPermissionsSaving(false);
    }
  };

  const toggleBuiltinTool = (tool: string) => {
    const current = new Set<string>(permissions.allowed_builtin_tools || []);
    if (current.has(tool)) current.delete(tool);
    else current.add(tool);
    setPermissions({ ...permissions, allowed_builtin_tools: Array.from(current) });
  };

  const toggleFlag = (key: string) => {
    setPermissions({ ...permissions, [key]: !permissions[key] });
  };

  const openFile = async (path: string) => {
    setSelectedFile(path);
    setFileDirty(false);
    setFileLoading(true);
    try {
      const doc = await api.getWorkspaceFileByName(id, path);
      setFileContent((doc as any).content || '');
    } catch (e) {
      console.error(e);
      setFileContent('');
    } finally {
      setFileLoading(false);
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    setFileSaving(true);
    try {
      await api.putWorkspaceFileByName(id, selectedFile, fileContent);
      setFileDirty(false);
    } catch (e) {
      console.error(e);
    } finally {
      setFileSaving(false);
    }
  };

  useEffect(() => {
    load();
    setSelectedFile(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) return <p className="dim">loading…</p>;
  if (!data) return <p className="dim">workspace not found</p>;

  const files: WorkspaceFile[] = data.files || [];
  const configs: Record<string, GeneratedConfig> = data.generated_configs || {};
  const builtinEnabled = new Set<string>(permissions.allowed_builtin_tools || []);

  return (
    <div className="stack">
      {/* Header */}
      <div className="row between" style={{ marginBottom: 8 }}>
        <h1>
          <Link to="/workspaces" className="dim">workspaces</Link> / {id}
        </h1>
        <div className="row" style={{ gap: 8 }}>
          <button onClick={generateSkills} disabled={generatingSkills}>
            {generatingSkills ? 'generating skills…' : 'generate skills'}
          </button>
          <button onClick={generate} disabled={generating} className="primary">
            {generating ? 'generating…' : 'generate configs'}
          </button>
        </div>
      </div>

      <div className="row between">
        <p className="dim">{data.path}</p>
        {lastAction && (
          <span className="pill ok" style={{ fontSize: 11 }}>
            {lastAction}
          </span>
        )}
      </div>

      {/* KPIs */}
      <div className="kpi-grid" style={{ marginBottom: 8 }}>
        <div className="kpi">
          <div className="kpi-label">Agents</div>
          <div className="kpi-value">{data.agents?.length || 0}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Files</div>
          <div className="kpi-value">{files.length}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Skills</div>
          <div className="kpi-value">{skills.length}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Built-in tools</div>
          <div className="kpi-value">{builtinEnabled.size}</div>
          <div className="kpi-sub">/ {builtinTools.length} possible</div>
        </div>
      </div>

      {/* 1. Environment — env-doc (renders CLAUDE.md/AGENTS.md on each run) */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Environment</h3>
        <EnvDocEditor workspaceId={id!} />
      </section>

      {/* 2. Resources — skills/folders/scripts/schemas/docs bound to this
          workspace. Skill packs discovered on disk surface here as
          available-to-bind; the dedicated Skills viewer section was
          removed to stop double-presenting the same concept. */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Resources</h3>
        <WorkspaceResourcesEditor workspaceId={id!} />
      </section>

      {/* 3. Agents — subagent assignments with reorder */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Agents</h3>
        <SubagentsEditor workspaceId={id!} />
      </section>

      {/* 4. Capabilities — single section bundling everything that controls
          what the agent CAN do at runtime. The previous "MCP Tool Groups"
          card was removed: it wrote to capabilities.json while
          WorkspaceMcpEditor wrote to the DB, leaving the same MCP grants
          under two stores that never agreed. */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Capabilities</h3>
          <button onClick={savePermissions} disabled={permissionsSaving} className="primary">
            {permissionsSaving ? 'saving…' : 'save permissions'}
          </button>
        </div>

        {/* 4a. Workspace flags + limits */}
        <div className="stack" style={{ gap: 12, marginBottom: 16 }}>
          <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
            <label className="row" style={{ gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={!!permissions.allow_file_write}
                onChange={() => toggleFlag('allow_file_write')}
              />
              <span>Allow file write</span>
            </label>
            <label className="row" style={{ gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={!!permissions.allow_network}
                onChange={() => toggleFlag('allow_network')}
              />
              <span>Allow network access</span>
            </label>
            <div className="row" style={{ gap: 6, alignItems: 'center' }}>
              <label style={{ fontSize: 12 }}>Max tokens</label>
              <input
                type="number"
                value={permissions.max_tokens ?? ''}
                placeholder="inherit"
                onChange={(e) => {
                  const v = e.target.value.trim();
                  setPermissions({
                    ...permissions,
                    max_tokens: v === '' ? null : parseInt(v, 10),
                  });
                }}
                style={{ maxWidth: 110 }}
              />
            </div>
          </div>
        </div>

        {/* 4b. Built-in tools — managed via allowed_builtin_tools, distinct
            from MCP tools which are managed below. */}
        <div style={{ marginBottom: 16 }}>
          <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Built-in tools
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {builtinTools.map((tool) => {
              const isActive = builtinEnabled.has(tool);
              return (
                <button
                  key={tool}
                  className={isActive ? 'primary' : ''}
                  style={{ fontSize: 11, padding: '3px 10px', borderRadius: 12 }}
                  onClick={() => toggleBuiltinTool(tool)}
                >
                  {tool}
                </button>
              );
            })}
          </div>
        </div>

        {/* 4c. MCP servers & tools — DB-backed, the single source of truth
            for per-server enable + per-tool grants. */}
        <div style={{ marginBottom: 16 }}>
          <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            MCP servers &amp; tools
          </h4>
          <WorkspaceMcpEditor workspaceId={id!} />
        </div>

        {/* 4d. Host-env capability grants */}
        <div>
          <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Host-env capabilities
          </h4>
          <WorkspaceHostEnvEditor workspaceId={id!} />
        </div>
      </section>

      {/* 5. Files — user files only. CLAUDE.md / AGENTS.md / .agentbox/
          / permissions/ are render artifacts and live in their own
          sections, so they're filtered server-side. */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Files ({files.length})</h3>
          {Object.keys(configs).length > 0 && (
            <span className="dim" style={{ fontSize: 11 }}>
              {Object.values(configs).filter((c) => c.exists).length}/
              {Object.keys(configs).length} generated configs ready
            </span>
          )}
        </div>
        {files.length === 0 ? (
          <p className="dim">No user files yet.</p>
        ) : (
          <div className="stack" style={{ gap: 8 }}>
            <table style={{ fontSize: 12 }}>
              <tbody>
                {files.map((f) => (
                  <tr
                    key={f.path}
                    style={{
                      cursor: 'pointer',
                      background: selectedFile === f.path ? 'rgba(88,166,255,0.1)' : undefined,
                    }}
                    onClick={() => openFile(f.path)}
                  >
                    <td>
                      <button className="link-btn">{f.path}</button>
                    </td>
                    <td style={{ textAlign: 'right' }} className="dim">{f.size}b</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {selectedFile && (
              <div className="stack" style={{ gap: 8 }}>
                <div className="row between">
                  <span style={{ fontWeight: 500, fontSize: 12 }}>
                    {selectedFile}
                    {fileDirty && <span className="dirty" style={{ marginLeft: 6 }}>●</span>}
                  </span>
                  <button onClick={saveFile} disabled={fileSaving || !fileDirty} className="primary" style={{ fontSize: 12, padding: '3px 10px' }}>
                    {fileSaving ? 'saving…' : 'save'}
                  </button>
                </div>
                {fileLoading ? (
                  <p className="dim">loading…</p>
                ) : (
                  <textarea
                    value={fileContent}
                    onChange={(e) => {
                      setFileContent(e.target.value);
                      setFileDirty(true);
                    }}
                    style={{
                      minHeight: 150,
                      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
                      fontSize: 11,
                      lineHeight: 1.5,
                      resize: 'vertical',
                    }}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* Generated configs as a compact status strip — the actual
            artifacts live under .agentbox/generated/ and are rewritten on
            every "generate configs" / save-permissions call. */}
        {Object.keys(configs).length > 0 && (
          <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap', fontSize: 11 }}>
              {Object.entries(configs).map(([name, cfg]) => (
                <span
                  key={name}
                  className="pill"
                  style={{
                    background: cfg.exists ? '#1f6f3a' : '#5a2424',
                    color: '#fff',
                  }}
                  title={cfg.path}
                >
                  {name} {cfg.exists ? '✓' : '✗'}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
