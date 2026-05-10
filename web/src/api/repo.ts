// Typed fetch helpers for the central resource repository
// (Plan 01 endpoints under /api/repo-resources).

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string>) };
  if (init && !(init.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    let detail: unknown;
    try { detail = await resp.clone().json(); } catch { detail = await resp.text(); }
    throw new Error(`HTTP ${resp.status}: ${JSON.stringify(detail)}`);
  }
  if (resp.status === 204) return undefined as T;
  const ct = resp.headers.get('Content-Type') || '';
  if (ct.includes('application/json')) return (await resp.json()) as T;
  return (await resp.text()) as unknown as T;
}

export type RepoType = 'document' | 'folder' | 'skill' | 'schema' | 'script';

export interface RepoResource {
  id: string;
  slug: string;
  type: RepoType;
  display_name: string;
  description?: string | null;
  active_version_id?: string | null;
  status?: string;
  tags?: string | null;
  created_at: string;
  updated_at: string;
  created_by?: string | null;
}

export interface RepoVersion {
  id: string;
  resource_id: string;
  version_number: number;
  is_draft: boolean;
  import_source: string;
  content_hash: string;
  byte_size: number;
  changelog: string;
  created_at: string;
  created_by?: string | null;
  source_metadata?: Record<string, unknown> | null;
  metadata?: Record<string, unknown> | null;
}

export interface RepoResourceDetail {
  resource: RepoResource;
  active_version: RepoVersion | null;
}

export const repoApi = {
  list: (params: { type?: RepoType; q?: string; limit?: number; offset?: number } = {}) => {
    const p = new URLSearchParams();
    if (params.type) p.set('type', params.type);
    if (params.q) p.set('q', params.q);
    if (params.limit != null) p.set('limit', String(params.limit));
    if (params.offset != null) p.set('offset', String(params.offset));
    const qs = p.toString();
    return req<{ items: RepoResource[]; total?: number; limit?: number; offset?: number }>(`/api/repo-resources${qs ? `?${qs}` : ''}`);
  },

  get: (id: string) => req<RepoResourceDetail>(`/api/repo-resources/${encodeURIComponent(id)}`),

  versions: (id: string) =>
    req<{ items: RepoVersion[] }>(`/api/repo-resources/${encodeURIComponent(id)}/versions`),

  create: (body: { slug: string; type: RepoType; display_name: string; description?: string }) =>
    req<RepoResource>('/api/repo-resources', { method: 'POST', body: JSON.stringify(body) }),

  update: (id: string, body: { display_name?: string; description?: string; tags?: string[] }) =>
    req<RepoResource>(`/api/repo-resources/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  uploadVersion: (id: string, file: File, changelog: string, draft = false, actor?: string) => {
    const fd = new FormData();
    fd.set('file', file);
    const qs = new URLSearchParams({ changelog, draft: String(draft) });
    if (actor) qs.set('actor', actor);
    return req<RepoVersion>(
      `/api/repo-resources/${encodeURIComponent(id)}/versions/upload?${qs.toString()}`,
      { method: 'POST', body: fd },
    );
  },

  publish: (id: string, versionId: string, reason: string, actor?: string) =>
    req<RepoVersion>(
      `/api/repo-resources/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/publish`,
      { method: 'POST', body: JSON.stringify({ reason, actor }) },
    ),

  rollback: (id: string, targetVersion: number, reason: string, actor?: string) =>
    req<RepoVersion>(`/api/repo-resources/${encodeURIComponent(id)}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ target_version: targetVersion, reason, actor }),
    }),

  render: (id: string, versionId?: string) => {
    const qs = versionId ? `?version_id=${encodeURIComponent(versionId)}` : '';
    return req<{ resource_id: string; version_id: string; text?: string; metadata?: Record<string, unknown> }>(
      `/api/repo-resources/${encodeURIComponent(id)}/render${qs}`,
    );
  },

  blob: (id: string, path = '', versionId?: string) => {
    const qs = new URLSearchParams();
    if (path) qs.set('path', path);
    if (versionId) qs.set('version_id', versionId);
    return req<string>(`/api/repo-resources/${encodeURIComponent(id)}/blobs?${qs.toString()}`);
  },

  remove: (id: string) =>
    req<void>(`/api/repo-resources/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  tree: (id: string, versionId?: string) => {
    const qs = versionId ? `?version_id=${encodeURIComponent(versionId)}` : '';
    return req<{
      version_id: string;
      entries: Array<{ relative_path: string; size_bytes: number | null; mime_type: string | null }>;
    }>(`/api/repo-resources/${encodeURIComponent(id)}/tree${qs}`);
  },

  // --- Phase 1 (RESOURCES_PLAN) ---

  uploadZip: (id: string, file: File, changelog: string, actor?: string) => {
    const fd = new FormData();
    fd.set('file', file);
    const qs = new URLSearchParams({ changelog });
    if (actor) qs.set('actor', actor);
    return req<RepoVersion>(
      `/api/repo-resources/${encodeURIComponent(id)}/versions/upload-zip?${qs.toString()}`,
      { method: 'POST', body: fd },
    );
  },

  uploadSchema: (id: string, file: File, changelog: string, actor?: string) => {
    const fd = new FormData();
    fd.set('file', file);
    const qs = new URLSearchParams({ changelog });
    if (actor) qs.set('actor', actor);
    return req<RepoVersion>(
      `/api/repo-resources/${encodeURIComponent(id)}/versions/upload-schema?${qs.toString()}`,
      { method: 'POST', body: fd },
    );
  },

  uploadScript: (
    id: string,
    file: File,
    changelog: string,
    opts: {
      language?: 'python' | 'shell';
      input_schema_resource_id?: string;
      output_schema_resource_id?: string;
      actor?: string;
    } = {},
  ) => {
    const fd = new FormData();
    fd.set('file', file);
    const qs = new URLSearchParams({ changelog });
    if (opts.language) qs.set('language', opts.language);
    if (opts.input_schema_resource_id) qs.set('input_schema_resource_id', opts.input_schema_resource_id);
    if (opts.output_schema_resource_id) qs.set('output_schema_resource_id', opts.output_schema_resource_id);
    if (opts.actor) qs.set('actor', opts.actor);
    return req<RepoVersion>(
      `/api/repo-resources/${encodeURIComponent(id)}/versions/upload-script?${qs.toString()}`,
      { method: 'POST', body: fd },
    );
  },

  exportZipUrl: (id: string, versionId?: string) =>
    `/api/repo-resources/${encodeURIComponent(id)}/export/zip${versionId ? `?version_id=${encodeURIComponent(versionId)}` : ''}`,

  exportPydantic: (id: string, className = 'Model') =>
    req<string>(
      `/api/repo-resources/${encodeURIComponent(id)}/export/pydantic?class_name=${encodeURIComponent(className)}`,
    ),

  validateScript: (id: string, sample: unknown, direction: 'input' | 'output' = 'input') =>
    req<{ valid: boolean; errors: Array<{ path: unknown[]; message: string }>; schema_resource_id: string }>(
      `/api/repo-resources/${encodeURIComponent(id)}/validate`,
      { method: 'POST', body: JSON.stringify({ sample, direction }) },
    ),
};

// --- Phase 2 (RESOURCES_PLAN): workspace subagents ---

export interface WorkspaceSubagent {
  id: string;
  workspace_id: string;
  agent_id: string;
  alias: string;
  display_order: number;
  created_at: string;
  agent_name?: string | null;
  agent_description?: string | null;
}

export const subagentsApi = {
  list: (workspaceId: string) =>
    req<{ items: WorkspaceSubagent[] }>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/subagents`,
    ),

  replace: (
    workspaceId: string,
    subagents: Array<{ agent_id: string; alias: string; display_order?: number }>,
    actor?: string,
  ) =>
    req<{ items: WorkspaceSubagent[] }>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/subagents`,
      { method: 'PUT', body: JSON.stringify({ subagents, actor }) },
    ),
};

// --- Workspace MCP overrides (Plan 05) ---

export type McpPolicy = 'allow_all_unless_disabled' | 'deny_all_unless_enabled';

export interface McpServerView {
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  disabled_tools: string[];
  source: 'default' | 'override';
}

export interface EffectiveMcp {
  servers: McpServerView[];
  policy: McpPolicy;
}

export const workspaceMcpApi = {
  get: (workspaceId: string) =>
    req<EffectiveMcp>(`/api/workspaces/${encodeURIComponent(workspaceId)}/mcp`),
  setPolicy: (workspaceId: string, policy: McpPolicy) =>
    req<{ policy: McpPolicy }>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/mcp/policy`,
      { method: 'PUT', body: JSON.stringify({ default_policy: policy }) },
    ),
  setServer: (
    workspaceId: string,
    serverName: string,
    enabled: boolean,
    reason: string,
    config_overrides?: Record<string, unknown> | null,
  ) =>
    req(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/mcp/servers/${encodeURIComponent(serverName)}`,
      { method: 'PUT', body: JSON.stringify({ enabled, reason, config_overrides }) },
    ),
  setTool: (
    workspaceId: string,
    serverName: string,
    toolName: string,
    enabled: boolean,
  ) =>
    req(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/mcp/servers/${encodeURIComponent(serverName)}/tools/${encodeURIComponent(toolName)}`,
      { method: 'PUT', body: JSON.stringify({ enabled }) },
    ),
  refresh: (workspaceId: string) =>
    req<{ invalidated: number }>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/mcp/refresh`,
      { method: 'POST' },
    ),
};

// --- Host-env grants (Plan 06) ---

export interface HostEnvCapability {
  name: string;
  description: string;
  grant_schema: Record<string, unknown>;
  default_granted: boolean;
}

export interface HostEnvGrants {
  grants: Record<string, Record<string, unknown>>;
  profile_id: string | null;
}

export const hostEnvApi = {
  capabilities: () =>
    req<{ capabilities: HostEnvCapability[] }>(`/api/host-env/capabilities`),
  getWorkspace: (workspaceId: string) =>
    req<HostEnvGrants>(`/api/workspaces/${encodeURIComponent(workspaceId)}/host-env`),
  setWorkspace: (
    workspaceId: string,
    overrides: Record<string, Record<string, unknown>>,
    reason: string,
    profile_id?: string | null,
  ) =>
    req<HostEnvGrants>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/host-env`,
      {
        method: 'PUT',
        body: JSON.stringify({ overrides, profile_id, reason }),
      },
    ),
};
