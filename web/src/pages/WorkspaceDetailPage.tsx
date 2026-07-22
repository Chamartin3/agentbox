import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../api/client';
import { apiRequestOrNull } from '../api/http';
import { subagentsApi } from '../api/repo';
import EnvDocEditor from '../components/workspace/EnvDocEditor';
import WorkspaceResourcesEditor from '../components/workspace/WorkspaceResourcesEditor';
import WorkspaceSkillsEditor from '../components/workspace/WorkspaceSkillsEditor';
import SubagentsEditor from '../components/workspace/SubagentsEditor';
import WorkspaceMcpEditor from '../components/workspace/WorkspaceMcpEditor';
import WorkspaceCredentialsEditor from '../components/workspace/WorkspaceCredentialsEditor';
import FileTree from '../components/workspace/FileTree';
import Modal from '../components/common/Modal';

interface WorkspaceFile {
  path: string;
  size: number;
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
  const [subagentCount, setSubagentCount] = useState(0);
  const [bindingCount, setBindingCount] = useState(0);

  // File viewer state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileLoading, setFileLoading] = useState(false);
  const [fileDirty, setFileDirty] = useState(false);
  const [fileSaving, setFileSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [ws, perms, sk, subagents, bindings] = await Promise.all([
        api.getWorkspaceByName(id),
        api.getWorkspacePermissionsByName(id),
        api.listWorkspaceSkillsByName(id),
        subagentsApi.list(id),
        apiRequestOrNull<{ items: unknown[] }>(
          `/api/workspaces/${encodeURIComponent(id)}/resources`,
        ).then((d) => d ?? { items: [] }),
      ]);
      setData(ws);
      setPermissions((perms as any).permissions || {});
      setSkills((sk as any).skills || []);
      setSubagentCount(subagents.items?.length || 0);
      setBindingCount((bindings as any).items?.length || 0);
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
          <div className="kpi-label">Subagents</div>
          <div className="kpi-value">{subagentCount}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Resources</div>
          <div className="kpi-value">{bindingCount}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Skill packs</div>
          <div className="kpi-value">{skills.length}</div>
          <div className="kpi-sub">on-disk SKILL.md</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Files</div>
          <div className="kpi-value">{files.length}</div>
        </div>
      </div>

      {/* Each editor renders its own card chrome (heading + panel). The
          page used to wrap them in an outer <section className="section">
          which produced visible card-in-card nesting. */}
      <EnvDocEditor workspaceId={id!} />
      <WorkspaceResourcesEditor workspaceId={id!} />
      <WorkspaceSkillsEditor workspaceId={id!} />
      <SubagentsEditor workspaceId={id!} />
      <WorkspaceCredentialsEditor workspaceId={id!} />

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

        {/* Built-in tools are governed by each agent's configuration, not the
            workspace — so they're intentionally not editable here. */}

        {/* 4c. MCP servers & tools — DB-backed, the single source of truth
            for per-server enable + per-tool grants. */}
        <div style={{ marginBottom: 16 }}>
          <h4 className="dim" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            MCP servers &amp; tools
          </h4>
          <WorkspaceMcpEditor workspaceId={id!} />
        </div>

        {/* Host-env capability grants are authorized per-agent (the agent's
            tool_grants is the sole authorization surface — see
            /api/agents/{id}/host-env), so they are not configured here. */}
      </section>

      {/* 5. Files — user files only, as a tree. CLAUDE.md / AGENTS.md /
          .agentbox/ / .claude/ / .opencode/ / .codex/ / permissions/ are
          render artifacts, filtered server-side. Clicking a file opens it
          in a modal. */}
      <section className="section">
        <h3 style={{ margin: 0, marginBottom: 8 }}>Files ({files.length})</h3>
        {files.length === 0 ? (
          <p className="dim">No user files yet.</p>
        ) : (
          <FileTree files={files} onOpen={openFile} />
        )}
      </section>

      {selectedFile && (
        <Modal
          title={
            <span>
              {selectedFile}
              {fileDirty && <span className="dirty" style={{ marginLeft: 6 }}>●</span>}
            </span>
          }
          onClose={() => setSelectedFile(null)}
          wide
          footer={
            <button
              onClick={saveFile}
              disabled={fileSaving || !fileDirty}
              className="primary"
              style={{ fontSize: 12, padding: '4px 12px' }}
            >
              {fileSaving ? 'saving…' : 'save'}
            </button>
          }
        >
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
                width: '100%',
                minHeight: 320,
                fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
                fontSize: 12,
                lineHeight: 1.5,
                resize: 'vertical',
              }}
            />
          )}
        </Modal>
      )}
    </div>
  );
}
