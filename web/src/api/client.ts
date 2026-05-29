// Typed API client. Throws ApiError on non-2xx.

import { RunStatus } from '../theme/statusColors';
import { apiRequest as req, ApiError } from './http';

export { ApiError };

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
  status: RunStatus;
  input: string;
  output: string | null;
  error: string | null;
  workdir: string | null;
  transcript_path: string | null;
  created_at: string;
  finished_at: string | null;
  config_digest: string | null;
  agent_version_id: number | null;
  agent_version?: number | null;
  composition_snapshot: Record<string, unknown> | null;
  rendered_prompt: { system: string; user: string; schema: unknown } | null;
  variables: Record<string, string> | null;
  validation_status: string | null;
  validation_errors: string | null;
  backend?: string | null;
  configured_model?: string | null;
  reported_model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_read_tokens?: number | null;
  cache_write_tokens?: number | null;
  cost_usd?: number | null;
  model?: string | null;
  duration_ms?: number | null;
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

export interface RunsStats {
  totals: {
    runs: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    avg_duration_ms: number;
  };
  by_agent: Array<{
    agent_id: string;
    runs: number;
    tokens: number;
    cost_usd: number;
  }>;
  by_model: Array<{
    model: string;
    runs: number;
    tokens: number;
    cost_usd: number;
  }>;
  by_version?: Array<{
    version: number;
    runs: number;
    tokens: number;
  }>;
  by_status: Array<{
    status: string;
    runs: number;
  }>;
  timeseries: Array<{
    bucket: string;
    runs: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
  }>;
}

export interface RunnerSpec {
  kind: string;
  /**
   * @deprecated The legacy `runner.model` field is no longer surfaced by
   * the API. Read the top-level `AgentDef.model` instead (resolved via
   * the bound runner profile). Kept optional for backwards-compat with
   * old write paths.
   */
  model?: string | null;
  mcp_config_path: string | null;
  agents_config_path: string | null;
  settings_path: string | null;
  config_path: string | null;
  command: string[] | null;
  allowed_tools: string[];
  extra_args: string[];
  timeout_seconds: number | null;
  output_schema_path: string | null;
  output_validation_engine: 'jsonschema' | 'pydantic' | 'both';
  max_validation_retries: number;
  max_error_retries: number;
}

export interface AgentDef {
  id: string;
  description: string;
  prompt_path: string | null;
  composition: CompositionConfig | null;
  workspace: string | null;
  runner: RunnerSpec;
  session_mode: 'headless' | 'persistent';
  tags: string[];
  tools: string[];
  webhook_url: string | null;
  claude_agent: boolean;
  headless: boolean;
  unsupported_backends: string[];
  source_format: string | null;
  updated_at?: string | null;
  last_run_at?: string | null;
  last_activity_at?: string | null;
  resolved_workspace?: string;
  version?: number | null;
  total_versions?: number | null;
  active_version?: number | null;
  run_count?: number | null;
  runner_profile_id?: string | null;
  /** Effective model resolved via the bound runner profile. */
  model?: string | null;
  /** Effective provider resolved via the bound runner profile. */
  model_provider?: string | null;
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

// ---- agent lifecycle types -----------------------------------------------

export type RunnerKind = 'claude_code' | 'opencode' | 'pydantic_ai';

export type BundleFileKind = 'output_schema' | 'input_schema' | 'user_template' | 'system' | 'reference';

export interface AgentCreatePayload {
  id: string;
  description: string;
  runner: Partial<RunnerSpec> & { kind: RunnerKind };
  prompt?: string;
  composition?: Partial<CompositionConfig>;
  tools?: string[];
  tags?: string[];
  workspace?: string;
  session_mode?: 'fresh' | 'resume';
  webhook_url?: string;
  author: string;
  changelog: string;
}

export interface AgentCreateResult {
  agent_id: string;
  version: number;
  version_id: number;
  is_draft: boolean;
}

export interface VersionFileUpload {
  kind: BundleFileKind;
  name: string;
  content: string;
}

export interface VersionFileUploadResult {
  file_id: number;
  sha256: string;
  size: number;
}

export interface ExportRequest {
  source_format: string;
  target_path?: string;
}

export interface ImportRequest {
  path: string;
  source_format?: string;
  strategy?: string;
  author: string;
  changelog: string;
}

// ---- shared resources types -----------------------------------------------

export type ResourceKind =
  | 'output_schema'
  | 'input_schema'
  | 'user_template'
  | 'system_fragment'
  | 'reference'
  | 'mcp_server'
  | 'skill';

export interface SharedResource {
  id: string;
  version: number;
  kind: string;
  name: string;
  description?: string;
  content?: string;
  config_json?: string;
  sha256: string;
  is_active: boolean;
  author?: string;
  changelog?: string;
  tags: string[];
  created_at: string;
}

export interface SharedRef {
  shared: string;
  version?: number;
}

export interface ResourceQuery {
  kind?: ResourceKind | ResourceKind[];
  q?: string;
  limit?: number;
  offset?: number;
}

export interface ResourcesPage {
  items: SharedResource[];
  total?: number;
}

export interface CreateResourcePayload {
  id: string;
  kind: string;
  name: string;
  description?: string;
  content?: string;
  config_json?: string;
  author: string;
  changelog: string;
  tags?: string[];
  activate?: boolean;
}

export interface CreateResourceVersionPayload {
  content?: string;
  config_json?: string;
  author: string;
  changelog: string;
  activate?: boolean;
  name?: string;
  description?: string;
  tags?: string[];
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

// ---- runner profiles -----------------------------------------------------

export interface RunnerProfile {
  id: string;
  name: string;
  description: string | null;
  backend: string;
  provider: string | null;
  model: string | null;
  base_url: string | null;
  api_key_env: string | null;
  api_token_id: string | null;
  params: Record<string, unknown>;
  headers: Record<string, string>;
  extra_args: string[];
  is_enabled: boolean;
  is_system_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface RunnerProfileCreate {
  id?: string;
  name: string;
  description?: string | null;
  backend: string;
  provider?: string | null;
  model?: string | null;
  base_url?: string | null;
  api_key_env?: string | null;
  api_token_id?: string | null;
  params?: Record<string, unknown>;
  headers?: Record<string, string>;
  extra_args?: string[];
  is_enabled?: boolean;
  is_system_default?: boolean;
}

export type RunnerProfilePatch = Partial<RunnerProfileCreate>;

export interface RunnerProfileStats {
  profile_id: string;
  runs: number;
  succeeded: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  avg_duration_ms: number | null;
  last_run_at: string | null;
}

export interface RunnerProvider {
  id: string;
  label: string;
  backend: string;
  compatible_backends: string[];
  requires_api_key: boolean;
  supports_base_url: boolean;
  supports_model_listing: boolean;
  default_base_url: string | null;
  default_api_key_env: string | null;
}

export interface RunnerBackend {
  id: string;
  label: string;
  default_model: string | null;
  compatible_providers: string[];
  accepts_no_provider: boolean;
}


// ---- inline per-agent validators ----------------------------------------

export interface HttpValidator {
  kind: 'http';
  endpoint: string;
  timeout_seconds?: number;
  description?: string;
}

export interface ScriptValidator {
  kind: 'script';
  resource_id: string;
  pinned_version_id?: string | null;
  description?: string;
}

export type Validator = HttpValidator | ScriptValidator | { kind: string; [k: string]: unknown };

export interface AgentValidationView {
  agent_id: string;
  agent_version_id: number | null;
  input: { validators: Validator[] } | null;
  output: { validators: Validator[] } | null;
}

export interface AgentValidationPut {
  input?: { validators: Validator[] } | null;
  output?: { validators: Validator[] } | null;
  reason: string;
  actor?: string;
}

// ---- endpoints ---------------------------------------------------------

export interface RunsQuery {
  agent?: string;
  status?: string;
  executor?: string;
  agent_version?: number;
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
  if (q.agent_version != null) p.set('agent_version', String(q.agent_version));
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
        statuses: Object.values(RunStatus),
      };
    }
  },
  getRun: (id: string) =>
    req<{ run: RunRecord; usage: UsageRecord | null }>(
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
  cancelRun: (id: string) =>
    req<{ run_id: string; cancelled: boolean; status: string }>(
      `/api/runs/${id}/cancel`,
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
  runStats: (q?: RunsQuery) => {
    const qs = q ? buildRunsQs(q) : '';
    return req<RunsStats>(`/api/runs/_stats${qs ? `?${qs}` : ''}`);
  },
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

  getManifest: () => req<ManifestDoc>('/api/agents/export-all'),
  listRunnerModels: (kind: string) =>
    req<{ kind: string; models: string[] }>(
      `/api/manifest/runner-models?kind=${encodeURIComponent(kind)}`,
    ),
  patchAgent: (id: string, body: Partial<AgentDef> & { runner?: Partial<RunnerSpec> }) =>
    req<{ agent: AgentDef }>(`/api/agents/${id}`, {
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
  listWorkspacesPaginated: (params: {
    q?: string; sort?: string | null; order?: 'asc' | 'desc' | null;
    limit?: number; offset?: number;
  }) => {
    const p = new URLSearchParams({ paginated: 'true' });
    if (params.q) p.set('q', params.q);
    if (params.sort) p.set('sort', params.sort);
    if (params.order) p.set('order', params.order);
    if (params.limit != null) p.set('limit', String(params.limit));
    if (params.offset != null) p.set('offset', String(params.offset));
    return req<{ items: Array<Record<string, unknown>>; total: number }>(
      `/api/workspaces?${p.toString()}`,
    );
  },
  createWorkspaceRegistry: (body: { name: string; description?: string; path?: string }) =>
    req<Record<string, unknown>>('/api/workspaces', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteWorkspaceRegistry: (name: string, purgeDisk = false) =>
    req<Record<string, unknown>>(
      `/api/workspaces/by-name/${encodeURIComponent(name)}${purgeDisk ? '?purge_disk=true' : ''}`,
      { method: 'DELETE' },
    ),
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

  // ---- agent lifecycle (DB-only creation, publish, draft, rollback) --------

  createAgent: (payload: AgentCreatePayload) =>
    req<AgentCreateResult>('/api/agents', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  uploadVersionFile: (agentId: string, version: number, body: VersionFileUpload) =>
    req<VersionFileUploadResult>(`/api/agents/${agentId}/versions/${version}/files`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  deleteVersionFile: (agentId: string, version: number, fileId: number) =>
    req<void>(`/api/agents/${agentId}/versions/${version}/files/${fileId}`, {
      method: 'DELETE',
    }),

  publishVersion: (agentId: string, version: number, reason: string) =>
    req<{ active_version: number; version_id: number; is_draft: boolean }>(
      `/api/agents/${agentId}/versions/${version}/publish`,
      { method: 'POST', body: JSON.stringify({ reason }) },
    ),

  branchDraft: (agentId: string, author: string) =>
    req<{ version: number; version_id: number; is_draft: boolean }>(
      `/api/agents/${agentId}/draft`,
      { method: 'POST', body: JSON.stringify({ author }) },
    ),

  rollbackVersion: (agentId: string, version: number, reason: string, author: string) =>
    req<{ version: number; version_id: number; is_draft: boolean; active_version: number }>(
      `/api/agents/${agentId}/versions/${version}/rollback`,
      { method: 'POST', body: JSON.stringify({ reason, author }) },
    ),

  exportAgent: (agentId: string, body: ExportRequest) =>
    req<{ ok: boolean; path?: string }>(`/api/agents/${agentId}/export`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  importAgent: (body: ImportRequest) =>
    req<AgentCreateResult>('/api/agents/import-file', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // ---- shared resources ----------------------------------------------------

  listResources: (params?: ResourceQuery) => {
    const p = new URLSearchParams();
    if (params?.kind) {
      if (Array.isArray(params.kind)) params.kind.forEach((k) => p.append('kind', k));
      else p.set('kind', params.kind);
    }
    if (params?.q) p.set('q', params.q);
    if (params?.limit != null) p.set('limit', String(params.limit));
    if (params?.offset != null) p.set('offset', String(params.offset));
    const qs = p.toString();
    return req<ResourcesPage>(`/api/resources${qs ? `?${qs}` : ''}`);
  },

  getResource: (id: string) => req<SharedResource>(`/api/resources/${id}`),

  getResourceVersions: (id: string) => req<ResourcesPage>(`/api/resources/${id}/versions`),

  createResource: (body: CreateResourcePayload) =>
    req<SharedResource>('/api/resources', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  createResourceVersion: (id: string, body: CreateResourceVersionPayload) =>
    req<SharedResource>(`/api/resources/${id}/versions`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  activateResourceVersion: (id: string, version: number) =>
    req<SharedResource>(`/api/resources/${id}/activate`, {
      method: 'POST',
      body: JSON.stringify({ version }),
    }),

  // mcp manifest
  getMcpManifest: () => req<Record<string, unknown>>('/api/mcp/manifest'),
  getMcpToolGroups: () => req<Record<string, unknown>>('/api/mcp/tool-groups'),

  // ---- runner profiles -----------------------------------------------------

  // Provider* helpers are the canonical UI names from IMPROVEMENTS.md Phase 4.
  // They alias the legacy runner-profile endpoints; backend exposes both
  // via providers_alias router (307 redirect).
  listProviders: () => req<RunnerProfile[]>('/api/runner-profiles'),
  listRunnerProfiles: () => req<RunnerProfile[]>('/api/runner-profiles'),
  getRunnerProfile: (id: string) => req<RunnerProfile>(`/api/runner-profiles/${id}`),
  createRunnerProfile: (body: RunnerProfileCreate) =>
    req<RunnerProfile>('/api/runner-profiles', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateRunnerProfile: (id: string, body: RunnerProfilePatch) =>
    req<RunnerProfile>(`/api/runner-profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteRunnerProfile: (id: string) =>
    req<void>(`/api/runner-profiles/${id}`, { method: 'DELETE' }),
  getRunnerProfileStats: (id: string) =>
    req<RunnerProfileStats>(`/api/runner-profiles/${id}/stats`),

  getAgentRunnerProfile: (agentId: string) =>
    req<RunnerProfile | null>(`/api/agents/${agentId}/runner-profile`),
  setAgentRunnerProfile: (agentId: string, profileId: string) =>
    req<{ agent_id: string; runner_profile_id: string }>(
      `/api/agents/${agentId}/runner-profile`,
      { method: 'PATCH', body: JSON.stringify({ runner_profile_id: profileId }) },
    ),
  clearAgentRunnerProfile: (agentId: string) =>
    req<void>(`/api/agents/${agentId}/runner-profile`, { method: 'DELETE' }),

  listRunnerBackends: () => req<RunnerBackend[]>('/api/runner-backends'),
  listRunnerProviders: (backend?: string) => {
    const qs = backend ? `?backend=${encodeURIComponent(backend)}` : '';
    return req<RunnerProvider[]>(`/api/runner-providers${qs}`);
  },
  refreshRunnerProviders: (backend?: string) => {
    const qs = backend ? `?backend=${encodeURIComponent(backend)}` : '';
    return req<{ opencode: string[]; model_cache_cleared: boolean }>(
      `/api/runner-providers/refresh${qs}`,
      { method: 'POST' },
    );
  },
  listProviderModels: (
    providerId: string,
    opts?: {
      profile_id?: string;
      base_url?: string;
      api_key_env?: string;
      backend?: string;
      refresh?: boolean;
    },
  ) => {
    const params = new URLSearchParams();
    if (opts?.profile_id) params.set('profile_id', opts.profile_id);
    if (opts?.base_url) params.set('base_url', opts.base_url);
    if (opts?.api_key_env) params.set('api_key_env', opts.api_key_env);
    if (opts?.backend) params.set('backend', opts.backend);
    if (opts?.refresh) params.set('refresh', 'true');
    const qs = params.toString();
    return req<
      Array<{
        id: string;
        name?: string | null;
        context_length?: number | null;
        input_modalities?: string[];
        output_modalities?: string[];
        raw?: Record<string, unknown>;
      }>
    >(`/api/runner-providers/${providerId}/models${qs ? `?${qs}` : ''}`);
  },

  // ---- per-agent inline validators ---------------------------------------

  getAgentValidation: (agentId: string) =>
    req<AgentValidationView>(`/api/agents/${encodeURIComponent(agentId)}/validation`),
  setAgentValidation: (agentId: string, body: AgentValidationPut) =>
    req<AgentValidationView>(`/api/agents/${encodeURIComponent(agentId)}/validation`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

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
