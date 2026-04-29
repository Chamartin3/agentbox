// Typed API client. Throws on non-2xx.

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.clone().json();
    } catch {
      detail = await resp.text();
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`HTTP ${status}`);
  }
}

// ---- types --------------------------------------------------------------

export interface CompositionConfig {
  system: string;
  references: Array<string | { path: string; heading?: string }>;
  user_template: string | null;
  input_schema: string | null;
  output_schema: string | null;
  transport: string;
  output_validation: string;
}

export interface RunRecord {
  id: string;
  agent_id: string;
  session_id: string | null;
  status:
    | 'running'
    | 'ok'
    | 'error'
    | 'failed'
    | 'timeout'
    | 'stopped'
    | 'incomplete';
  input: string;
  output: string | null;
  error: string | null;
  workdir: string | null;
  transcript_path: string | null;
  created_at: string;
  finished_at: string | null;
  config_digest: string | null;
  agent_version_id: number | null;
  composition_snapshot: Record<string, unknown> | null;
  rendered_prompt: { system: string; user: string; schema: unknown } | null;
  variables: Record<string, string> | null;
  validation_status: string | null;
  validation_errors: string | null;
}

export interface UsageRecord {
  run_id: string;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  cost_usd: number | null;
}

export interface GuardrailRow {
  id: number;
  run_id: string;
  name: string;
  ok: number;
  message: string | null;
  attempt: number;
  created_at: string;
}

export interface RunnerSpec {
  kind: string;
  model: string | null;
  mcp_config_path: string | null;
  agents_config_path: string | null;
  settings_path: string | null;
  config_path: string | null;
  command: string[] | null;
  allowed_tools: string[];
  extra_args: string[];
  timeout_seconds: number;
  output_schema_path: string | null;
  output_validation_engine: 'jsonschema' | 'pydantic' | 'both';
  max_validation_retries: number;
  max_error_retries: number;
}

export interface GuardrailRef {
  name: string;
  options: Record<string, unknown>;
}

export interface AgentDef {
  id: string;
  description: string;
  prompt_path: string | null;
  composition: CompositionConfig | null;
  workspace: string | null;
  runner: RunnerSpec;
  session_mode: 'headless' | 'persistent';
  guardrails: GuardrailRef[];
  tags: string[];
  tools: string[];
  webhook_url: string | null;
  claude_agent: boolean;
  headless: boolean;
  unsupported_backends: string[];
  source_format: string | null;
  updated_at?: string | null;
  resolved_workspace?: string;
}

export interface PromptFragment {
  name: string;
  source: string;
  injected_by: string;
  content: string;
  inspectable: boolean;
  size_bytes: number;
}

export interface RunPromptDoc {
  run_id: string;
  fragments: PromptFragment[];
  total_bytes: number;
}

export interface PromptDoc {
  path: string;
  content: string;
  size: number;
  mtime: string;
}

export interface ManifestDoc {
  path: string;
  text: string;
  parsed: { project: string; agents: AgentDef[] };
}

// ---- prompt versioning --------------------------------------------------

export interface PromptVersionSummary {
  version: number;
  is_draft: boolean;
  created_at: string;
  author: string;
  changelog: string;
  size: number;
}

export interface PromptVersionList {
  agent_id: string;
  active_version: number | null;
  draft_version: number | null;
  versions: PromptVersionSummary[];
}

export interface PromptVersionDetail extends PromptVersionSummary {
  content: string;
}

// ---- endpoints ---------------------------------------------------------

export interface RunsQuery {
  agent?: string;
  status?: string;
  executor?: string;
  q?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export interface RunsPage {
  items: RunRecord[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface RunsFacets {
  agents: string[];
  executors: string[];
  statuses: string[];
}

function buildRunsQs(q: RunsQuery): string {
  const p = new URLSearchParams();
  if (q.agent) p.set('agent', q.agent);
  if (q.status) p.set('status', q.status);
  if (q.executor) p.set('executor', q.executor);
  if (q.q) p.set('q', q.q);
  if (q.since) p.set('since', q.since);
  if (q.until) p.set('until', q.until);
  if (q.limit != null) p.set('limit', String(q.limit));
  if (q.offset != null) p.set('offset', String(q.offset));
  return p.toString();
}

export const api = {
  listRuns: (agent?: string) =>
    req<RunRecord[]>(`/api/runs${agent ? `?agent=${agent}` : ''}`),
  listRunsPaged: async (q: RunsQuery): Promise<RunsPage> => {
    const limit = q.limit ?? 25;
    const qs = buildRunsQs({ ...q, limit });
    const raw = await req<RunsPage | RunRecord[]>(
      `/api/runs?paginated=true${qs ? `&${qs}` : ''}`,
    );
    if (Array.isArray(raw)) {
      return {
        items: raw,
        total: raw.length,
        offset: q.offset ?? 0,
        limit,
        has_more: false,
      };
    }
    return raw;
  },
  runFacets: async (): Promise<RunsFacets> => {
    try {
      return await req<RunsFacets>('/api/runs/_facets');
    } catch {
      const runs = await req<RunRecord[]>('/api/runs?limit=500');
      const agents = Array.from(new Set(runs.map((r) => r.agent_id))).sort();
      return {
        agents,
        executors: [],
        statuses: ['ok', 'error', 'failed', 'stopped', 'timeout', 'running'],
      };
    }
  },
  getRun: (id: string) =>
    req<{ run: RunRecord; usage: UsageRecord | null; guardrails: GuardrailRow[] }>(
      `/api/runs/${id}`,
    ),
  getTranscript: (id: string) =>
    req<Array<Record<string, unknown>>>(`/api/runs/${id}/transcript`),
  getRunPrompt: (id: string) => req<RunPromptDoc>(`/api/runs/${id}/prompt`),
  rerunRun: (id: string) =>
    req<{ run_id: string; agent: string; rerun_of: string }>(
      `/api/runs/${id}/rerun`,
      { method: 'POST' },
    ),
  listRunComments: (id: string) =>
    req<{ run_id: string; comments: Array<{ id: number; author: string; body: string; created_at: string }> }>(
      `/api/runs/${id}/comments`,
    ),
  addRunComment: (id: string, body: string, author = 'web') =>
    req<{ id: number; author: string; body: string; created_at: string }>(
      `/api/runs/${id}/comments`,
      { method: 'POST', body: JSON.stringify({ body, author }) },
    ),
  aggregateUsage: () =>
    req<{ input_tokens: number; output_tokens: number; cost_usd: number; runs: number }>(
      '/api/usage',
    ),

  listAgents: () => req<AgentDef[]>('/api/agents'),
  getAgent: (id: string) =>
    req<{
      agent: AgentDef;
      prompt: string;
      composed_system: string | null;
      composed_user: string | null;
      bundle_files: Array<{
        kind: string;
        relative_path: string;
        sha256: string;
        source_uri: string | null;
      }>;
      workspace: { path: string; ephemeral: boolean; generated_configs: Record<string, string> };
      current_version: number | null;
      versions: Array<Record<string, unknown>>;
    }>(`/api/agents/${id}`),

  getManifest: () => req<ManifestDoc>('/api/manifest'),
  listRunnerModels: (kind: string) =>
    req<{ kind: string; models: string[] }>(
      `/api/manifest/runner-models?kind=${encodeURIComponent(kind)}`,
    ),
  patchAgent: (id: string, body: Partial<AgentDef> & { runner?: Partial<RunnerSpec> }) =>
    req<{ agent: AgentDef }>(`/api/manifest/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  getPrompt: (id: string) => req<PromptDoc>(`/api/agents/${id}/prompt`),
  putPrompt: (id: string, content: string) =>
    req<PromptDoc>(`/api/agents/${id}/prompt`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    }),

  // versioned prompt endpoints
  listPromptVersions: (id: string) => req<PromptVersionList>(`/api/agents/${id}/prompt/versions`),
  getPromptVersion: (id: string, version: number) =>
    req<PromptVersionDetail>(`/api/agents/${id}/prompt/versions/${version}`),
  savePromptDraft: (id: string, content: string, author?: string) =>
    req<PromptDoc>(`/api/agents/${id}/prompt/draft`, {
      method: 'POST',
      body: JSON.stringify({ content, author: author || 'system' }),
    }),
  publishPrompt: (id: string, changelog?: string, author?: string) =>
    req<PromptDoc>(`/api/agents/${id}/prompt/publish`, {
      method: 'POST',
      body: JSON.stringify({ changelog: changelog || '', author: author || 'system' }),
    }),
  rollbackPrompt: (id: string, targetVersion: number, author?: string) =>
    req<PromptDoc>(`/api/agents/${id}/prompt/rollback`, {
      method: 'POST',
      body: JSON.stringify({ target_version: targetVersion, author: author || 'system' }),
    }),

  // workspace endpoints (by name)
  listWorkspaces: () => req<Array<Record<string, unknown>>>('/api/workspaces'),
  getWorkspaceByName: (name: string) => req<Record<string, unknown>>(`/api/workspaces/by-name/${name}`),
  generateWorkspaceConfigsByName: (name: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/generate-configs`, { method: 'POST' }),
  generateWorkspaceSkillsByName: (name: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/generate-skills`, { method: 'POST' }),
  getWorkspacePermissionsByName: (name: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/permissions`),
  setWorkspacePermissionsByName: (name: string, permissions: Record<string, unknown>) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/permissions`, {
      method: 'PUT',
      body: JSON.stringify({ permissions }),
    }),
  getWorkspaceMcpToolsByName: (name: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/mcp-tools`),
  listWorkspaceSkillsByName: (name: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/skills`),
  getWorkspaceSkillByName: (name: string, skillName: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/skills/${skillName}`),
  getWorkspaceFileByName: (name: string, path: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/file?path=${encodeURIComponent(path)}`),
  putWorkspaceFileByName: (name: string, path: string, content: string) =>
    req<Record<string, unknown>>(`/api/workspaces/by-name/${name}/file`, {
      method: 'PUT',
      body: JSON.stringify({ path, content }),
    }),

  // mcp manifest
  getMcpManifest: () => req<Record<string, unknown>>('/api/mcp/manifest'),
  getMcpToolGroups: () => req<Record<string, unknown>>('/api/mcp/tool-groups'),

  // legacy agent-centric workspace endpoints
  getWorkspace: (agentId: string) => req<Record<string, unknown>>(`/api/workspaces/${agentId}`),
  createWorkspace: (agentId: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}`, { method: 'POST' }),
  resetWorkspace: (agentId: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}`, { method: 'DELETE' }),
  generateWorkspaceConfigs: (agentId: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}/generate-configs`, { method: 'POST' }),
  listWorkspaceSkills: (agentId: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}/skills`),
  getWorkspaceFile: (agentId: string, path: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}/file?path=${encodeURIComponent(path)}`),
  putWorkspaceFile: (agentId: string, path: string, content: string) =>
    req<Record<string, unknown>>(`/api/workspaces/${agentId}/file`, {
      method: 'PUT',
      body: JSON.stringify({ path, content }),
    }),
};
