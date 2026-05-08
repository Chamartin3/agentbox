import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import EnvDocEditor from '../components/EnvDocEditor';
import WorkspaceResourcesEditor from '../components/WorkspaceResourcesEditor';
import SubagentsEditor from '../components/SubagentsEditor';

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

interface ToolGroup {
  name: string;
  tools: string[];
  claude_tools: string[];
  tool_count: number;
  kind: string;
  active: boolean;
  fully_active: boolean;
}

export default function WorkspaceDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatingSkills, setGeneratingSkills] = useState(false);
  const [skills, setSkills] = useState<SkillItem[]>([]);

  // Permissions state
  const [permissions, setPermissions] = useState<Record<string, any>>({});
  const [permissionsSaving, setPermissionsSaving] = useState(false);
  const [mcpGroups, setMcpGroups] = useState<ToolGroup[]>([]);
  const [builtinTools, setBuiltinTools] = useState<string[]>([]);
  const [mcpServerName, setMcpServerName] = useState<string>('');
  const [mcpPrefixes, setMcpPrefixes] = useState<{ claude: string; opencode: string }>({ claude: '', opencode: '' });
  const [mcpLoading, setMcpLoading] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null);

  // File viewer state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [fileDirty, setFileDirty] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);

  // Skill viewer state
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [skillContent, setSkillContent] = useState('');
  const [skillLoading, setSkillLoading] = useState(false);

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
      setMcpGroups((mcp as any).groups || []);
      setBuiltinTools((mcp as any).builtin_tools || []);
      setMcpServerName((mcp as any).mcp_server_name || '');
      setMcpPrefixes({
        claude: (mcp as any).claude_prefix || '',
        opencode: (mcp as any).opencode_prefix || '',
      });
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

  const savePermissions = async (newPermissions: Record<string, any>) => {
    setPermissionsSaving(true);
    try {
      const result = await api.setWorkspacePermissionsByName(id, newPermissions);
      setLastAction(
        `Saved permissions + regenerated ${Object.keys((result as any).regenerated || {}).length} config files`
      );
      await load(); // refresh config statuses
    } catch (e) {
      console.error(e);
    } finally {
      setPermissionsSaving(false);
    }
  };

  const toggleToolGroup = (group: ToolGroup) => {
    const currentAllowed = new Set(permissions.allowed_tools || []);
    const groupTools = new Set(group.claude_tools);

    // If group is fully active, remove all its tools. Otherwise add all.
    const shouldEnable = !group.fully_active;

    if (shouldEnable) {
      groupTools.forEach((t) => currentAllowed.add(t));
    } else {
      groupTools.forEach((t) => currentAllowed.delete(t));
    }

    const newPermissions = {
      ...permissions,
      allowed_tools: Array.from(currentAllowed),
    };
    setPermissions(newPermissions);

    // Update group states locally for instant feedback
    setMcpGroups((groups) =>
      groups.map((g) => {
        if (g.name === group.name) {
          return { ...g, active: shouldEnable, fully_active: shouldEnable };
        }
        return g;
      })
    );
  };

  const toggleBuiltinTool = (tool: string) => {
    const currentAllowed = new Set(permissions.allowed_tools || []);
    if (currentAllowed.has(tool)) {
      currentAllowed.delete(tool);
    } else {
      currentAllowed.add(tool);
    }
    const newPermissions = {
      ...permissions,
      allowed_tools: Array.from(currentAllowed),
    };
    setPermissions(newPermissions);
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

  const stripFrontmatter = (s: string): string => {
    // SKILL.md files start with `---\n...\n---\n` YAML frontmatter; the
    // viewer should show the skill body only, not the metadata header.
    if (!s.startsWith('---')) return s;
    const end = s.indexOf('\n---', 3);
    if (end === -1) return s;
    return s.slice(end + 4).replace(/^\n+/, '');
  };

  const openSkill = async (name: string) => {
    setSelectedSkill(name);
    setSkillLoading(true);
    try {
      const doc = await api.getWorkspaceSkillByName(id, name);
      setSkillContent(stripFrontmatter((doc as any).content || ''));
    } catch (e) {
      console.error(e);
      setSkillContent('');
    } finally {
      setSkillLoading(false);
    }
  };

  useEffect(() => {
    load();
    setSelectedFile(null);
    setSelectedSkill(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) return <p className="dim">loading…</p>;
  if (!data) return <p className="dim">workspace not found</p>;

  const files: WorkspaceFile[] = data.files || [];
  const configs: Record<string, GeneratedConfig> = data.generated_configs || {};

  // Group tool groups by category prefix
  const groupedTools: Record<string, ToolGroup[]> = {};
  mcpGroups.forEach((g) => {
    const prefix = g.name.includes('.') ? g.name.split('.')[0] : 'general';
    if (!groupedTools[prefix]) groupedTools[prefix] = [];
    groupedTools[prefix].push(g);
  });

  // Permission stats
  const allowedCount = (permissions.allowed_tools || []).length;
  const totalToolCount = mcpGroups.reduce((sum, g) => sum + g.tool_count, 0);

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

      {/* Top stats row */}
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
          <div className="kpi-label">Tools Enabled</div>
          <div className="kpi-value">{allowedCount}</div>
          <div className="kpi-sub">/ {totalToolCount + builtinTools.length} possible</div>
        </div>
      </div>

      {/* D1 — workspace env-doc editor (top of the page, "front and center") */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Environment Documentation</h3>
        <EnvDocEditor workspaceId={id!} />
      </section>

      {/* D2 — central resource bindings (skills/folders/scripts/schemas/docs) */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Resources</h3>
        <WorkspaceResourcesEditor workspaceId={id!} />
      </section>

      {/* D3 / E4 — subagent assignments with reorder */}
      <section className="section">
        <h3 style={{ marginTop: 0 }}>Subagents</h3>
        <SubagentsEditor workspaceId={id!} />
      </section>

      {/* Skills viewer — narrow list on left, wide content on right */}
      <section className="section">
        <div className="row between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Skills ({skills.length})</h3>
          {selectedSkill && (
            <span className="dim" style={{ fontSize: 11 }}>{selectedSkill}</span>
          )}
        </div>
        {skills.length === 0 ? (
          <p className="dim">No skill packs discovered.</p>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '240px 1fr',
              gap: 16,
              alignItems: 'start',
            }}
          >
            <div className="stack" style={{ gap: 6, maxHeight: 600, overflowY: 'auto' }}>
              {skills.map((s) => (
                <button
                  key={s.name}
                  onClick={() => openSkill(s.name)}
                  className={selectedSkill === s.name ? 'primary' : ''}
                  style={{
                    textAlign: 'left',
                    padding: '6px 10px',
                    fontSize: 12,
                    borderRadius: 6,
                  }}
                  title={s.path}
                >
                  <div style={{ fontWeight: 500 }}>{s.name}</div>
                  <div className="dim" style={{ fontSize: 10 }}>{s.size}b</div>
                </button>
              ))}
            </div>
            <div className="code-block" style={{ minHeight: 400 }}>
              <div className="code-block-bar">
                <span className="dim" style={{ fontSize: 11 }}>
                  {selectedSkill ? selectedSkill : 'select a skill →'}
                </span>
              </div>
              <pre style={{ maxHeight: 600, minHeight: 360 }}>
                {selectedSkill
                  ? (skillLoading ? 'loading…' : skillContent)
                  : ''}
              </pre>
            </div>
          </div>
        )}
      </section>

      {/* Configuration Dashboard */}
      <div className="grid-2" style={{ alignItems: 'start', gap: 16 }}>
        {/* LEFT: Permissions & Tool Groups */}
        <div className="stack" style={{ gap: 16 }}>
          {/* Workspace Flags */}
          <section className="section">
            <h3 style={{ marginTop: 0 }}>Workspace Settings</h3>
            <p className="dim" style={{ marginTop: 0, fontSize: 11 }}>
              Stored in <code>permissions/capabilities.json</code>. Click "save permissions" to
              persist and regenerate <code>.agentbox/generated/*</code>.
            </p>
            <div className="stack" style={{ gap: 12 }}>
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
              </div>
              <div className="field" style={{ gridTemplateColumns: '120px 1fr', marginBottom: 0 }}>
                <label>Max tokens</label>
                <input
                  type="number"
                  value={permissions.max_tokens || 64000}
                  onChange={(e) =>
                    setPermissions({ ...permissions, max_tokens: parseInt(e.target.value, 10) || 64000 })
                  }
                  style={{ maxWidth: 120 }}
                />
              </div>
              <div className="field" style={{ gridTemplateColumns: '120px 1fr', marginBottom: 0 }}>
                <label>MCP config path</label>
                <input
                  type="text"
                  value={permissions.mcp_config_path || ''}
                  onChange={(e) =>
                    setPermissions({ ...permissions, mcp_config_path: e.target.value.trim() || null })
                  }
                  placeholder="bin/claude/mcp.json — relative to project root"
                />
              </div>
            </div>
          </section>

          {/* Built-in Tools */}
          <section className="section">
            <h3 style={{ marginTop: 0 }}>Built-in Tools</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {builtinTools.map((tool) => {
                const isActive = (permissions.allowed_tools || []).includes(tool);
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
          </section>

          {/* MCP Tool Groups */}
          <section className="section">
            <div className="row between" style={{ marginBottom: 12 }}>
              <div>
                <h3 style={{ margin: 0 }}>MCP Tool Groups</h3>
                {mcpServerName && (
                  <div className="row" style={{ gap: 6, marginTop: 4 }}>
                    <span className="pill" style={{ background: 'var(--bg)', color: 'var(--fg-muted)', fontSize: 10 }}>
                      server: {mcpServerName}
                    </span>
                    <span className="dim" style={{ fontSize: 10 }}>
                      Claude: {mcpPrefixes.claude}* · OpenCode: {mcpPrefixes.opencode}*
                    </span>
                  </div>
                )}
              </div>
              <span className="dim" style={{ fontSize: 11 }}>
                {mcpGroups.length} groups · {totalToolCount} tools
              </span>
            </div>

            {mcpLoading ? (
              <p className="dim">loading…</p>
            ) : (
              <div className="stack" style={{ gap: 16 }}>
                {Object.entries(groupedTools).map(([category, groups]) => (
                  <div key={category}>
                    <h4
                      className="dim"
                      style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}
                    >
                      {category}
                    </h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {groups.map((group) => (
                        <div key={group.name} style={{ position: 'relative' }}>
                          <button
                            className={group.fully_active ? 'primary' : group.active ? '' : ''}
                            style={{
                              fontSize: 11,
                              padding: '4px 12px',
                              borderRadius: 12,
                              borderColor: group.fully_active ? 'var(--accent)' : undefined,
                              opacity: group.fully_active ? 1 : group.active ? 0.7 : 0.5,
                            }}
                            onClick={() => toggleToolGroup(group)}
                            title={`${group.tools.join(', ')}`}
                          >
                            {group.name}
                            <span className="dim" style={{ marginLeft: 4, fontSize: 10 }}>
                              ({group.tool_count})
                            </span>
                          </button>
                          <button
                            className="link-btn"
                            style={{ fontSize: 10, marginLeft: 2, padding: '2px 4px' }}
                            onClick={() => setExpandedGroup(expandedGroup === group.name ? null : group.name)}
                            title="Show actual tool names"
                          >
                            {expandedGroup === group.name ? '▲' : '▼'}
                          </button>
                          {expandedGroup === group.name && (
                            <div
                              className="section"
                              style={{
                                position: 'absolute',
                                zIndex: 10,
                                top: '100%',
                                left: 0,
                                marginTop: 4,
                                padding: 8,
                                minWidth: 280,
                                fontSize: 11,
                              }}
                            >
                              <div className="dim" style={{ fontSize: 10, marginBottom: 4 }}>Claude Code:</div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                                {group.claude_tools.map((t: string) => (
                                  <code key={t} style={{ fontSize: 10, padding: '1px 5px' }}>{t}</code>
                                ))}
                              </div>
                              <div className="dim" style={{ fontSize: 10, marginTop: 6, marginBottom: 4 }}>OpenCode:</div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                                {group.opencode_tools.map((t: string) => (
                                  <code key={t} style={{ fontSize: 10, padding: '1px 5px' }}>{t}</code>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Save */}
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
              <button onClick={() => savePermissions(permissions)} disabled={permissionsSaving} className="primary">
                {permissionsSaving ? 'saving…' : 'save permissions'}
              </button>
            </div>
          </section>
        </div>

        {/* RIGHT: Files, Configs */}
        <div className="stack" style={{ gap: 16 }}>
          {/* Files */}
          <section className="section">
            <h3 style={{ marginTop: 0 }}>Files ({files.length})</h3>
            {files.length === 0 ? (
              <p className="dim">No files yet.</p>
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
          </section>

          {/* Configs */}
          <section className="section">
            <h3 style={{ marginTop: 0 }}>Generated Configs</h3>
            <table style={{ fontSize: 12 }}>
              <tbody>
                {Object.entries(configs).map(([name, cfg]) => {
                  // Path is absolute (/project/workspaces/<ws>/.agentbox/generated/<file>)
                  // Convert to relative-to-workspace for the file viewer endpoint.
                  const rel = data?.path ? cfg.path.replace(data.path + '/', '') : cfg.path;
                  const clickable = cfg.exists;
                  return (
                    <tr
                      key={name}
                      style={{
                        cursor: clickable ? 'pointer' : 'default',
                        background: selectedFile === rel ? 'rgba(88,166,255,0.1)' : undefined,
                      }}
                      onClick={() => clickable && openFile(rel)}
                    >
                      <td>{name}</td>
                      <td className="dim">{rel}</td>
                      <td>
                        {cfg.exists ? (
                          <span className="pill" style={{ background: '#1f6f3a', color: '#fff' }}>ready</span>
                        ) : (
                          <span className="pill" style={{ background: '#8b1a1a', color: '#fff' }}>missing</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="dim" style={{ fontSize: 11, marginTop: 8, marginBottom: 0 }}>
              Click a "ready" row to view its content in the Files panel above.
            </p>
          </section>
        </div>
      </div>
    </div>
  );
}
