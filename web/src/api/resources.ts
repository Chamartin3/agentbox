// Typed fetch helpers for resources, prompt bindings, workspace resources,
// env-doc, MCP policy/servers, and host-env endpoints.

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = await resp.clone().json();
    } catch {
      detail = await resp.text();
    }
    throw new Error(`HTTP ${resp.status}: ${JSON.stringify(detail)}`);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ---- types -----------------------------------------------------------------

export interface PromptBinding {
  marker: string;
  resource_id: string;
  resource_version?: number | null;
  kind?: string;
  name?: string;
}

export interface PromptBindingsResponse {
  agent_id: string;
  bindings: PromptBinding[];
}

export interface WorkspaceFileBinding {
  path: string;
  resource_id: string;
  resource_version?: number | null;
  kind?: string;
  sha256?: string;
}

export interface WorkspaceResourcesResponse {
  workspace_id: string;
  bindings: WorkspaceFileBinding[];
}

export interface EnvDocResponse {
  workspace_id: string;
  content: string;
  path?: string;
  size?: number;
}

export interface McpPolicy {
  allow_all?: boolean;
  allowed_servers?: string[];
  denied_servers?: string[];
}

export interface McpPolicyResponse {
  workspace_id: string;
  policy: McpPolicy;
}

export interface McpServerOverride {
  name: string;
  url?: string;
  command?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

export interface McpServersResponse {
  workspace_id: string;
  servers: McpServerOverride[];
}

export interface HostEnvGrant {
  name: string;
  value?: string;
  source?: string;
  masked?: boolean;
}

export interface HostEnvResponse {
  workspace_id: string;
  grants: HostEnvGrant[];
}

// ---- API calls -------------------------------------------------------------

export const resourcesApi = {
  // Prompt bindings
  listPromptBindings: (agentId: string) =>
    req<PromptBindingsResponse>(`/api/agents/${encodeURIComponent(agentId)}/prompt-bindings`),

  // Workspace resources
  listWorkspaceResources: (wsId: string) =>
    req<WorkspaceResourcesResponse>(`/api/workspaces/${encodeURIComponent(wsId)}/resources`),

  // Env doc
  getEnvDoc: (wsId: string) =>
    req<EnvDocResponse>(`/api/workspaces/${encodeURIComponent(wsId)}/env-doc`),

  // MCP
  getMcpPolicy: (wsId: string) =>
    req<McpPolicyResponse>(`/api/workspaces/${encodeURIComponent(wsId)}/mcp/policy`),

  listMcpServers: (wsId: string) =>
    req<McpServersResponse>(`/api/workspaces/${encodeURIComponent(wsId)}/mcp/servers`),

  // Host-env
  getHostEnv: (wsId: string) =>
    req<HostEnvResponse>(`/api/workspaces/${encodeURIComponent(wsId)}/host-env`),
};
