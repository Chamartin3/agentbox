// Typed client for the /api/credentials endpoints and the per-workspace
// /api/workspaces/{id}/credentials enablement endpoints. Mirrors the
// convention in api/api_tokens.ts — a single object of thin apiRequest
// wrappers.

import { apiRequest } from './http';

export type CredentialKind = 'api_key' | 'login';
export type CredentialSource = 'file' | 'env' | 'db';
export type CredentialState = 'present' | 'missing' | 'invalid';

export interface CredentialInventoryEntry {
  id: string;
  label: string;
  kind: CredentialKind;
  source: CredentialSource;
  env_var: string | null;
  state: CredentialState;
}

export interface CredentialListResponse {
  items: CredentialInventoryEntry[];
  total: number;
}

export interface CreateCredentialBody {
  id: string;
  label: string;
  kind: CredentialKind;
  env_var?: string | null;
  secret: string;
}

export interface WorkspaceCredentials {
  available: CredentialInventoryEntry[];
  enabled: string[];
}

export const credentialsApi = {
  list: (): Promise<CredentialListResponse> =>
    apiRequest<CredentialListResponse>('/api/credentials'),

  // Returns the public row (never a secret). Throws ApiError(400) on
  // validation errors (e.g. api_key without env_var).
  create: (body: CreateCredentialBody): Promise<CredentialInventoryEntry> =>
    apiRequest<CredentialInventoryEntry>('/api/credentials', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  remove: (id: string): Promise<void> =>
    apiRequest<void>(`/api/credentials/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),

  forWorkspace: (workspaceId: string): Promise<WorkspaceCredentials> =>
    apiRequest<WorkspaceCredentials>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/credentials`,
    ),

  setForWorkspace: (
    workspaceId: string,
    enabled: string[],
  ): Promise<WorkspaceCredentials> =>
    apiRequest<WorkspaceCredentials>(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/credentials`,
      { method: 'PUT', body: JSON.stringify({ enabled }) },
    ),
};
