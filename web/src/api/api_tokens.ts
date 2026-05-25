// Typed client for the /api/api-tokens endpoints. Consolidates the three
// scattered fetch() callers (SettingsApiTokensTab, RunnerProfilesPage,
// RunnerProfileSection) that previously each rolled their own request.

import { apiRequest, apiRequestOrNull } from './http';

export interface ApiToken {
  id: string;
  environment: string;
  name: string;
  last_four: string;
  created_at: string;
  updated_at: string;
}

export interface CreatedToken extends ApiToken {
  secret: string;
}

interface ListResponse {
  items: ApiToken[];
}

export const apiTokens = {
  // Returns [] when the endpoint is missing or returns an error — callers
  // that only need to populate a picker shouldn't crash on 404/500.
  listSafe: async (): Promise<ApiToken[]> => {
    const data = await apiRequestOrNull<ListResponse | ApiToken[]>(
      '/api/api-tokens',
    ).catch(() => null);
    if (!data) return [];
    return Array.isArray(data) ? data : (data.items ?? []);
  },

  list: (): Promise<ListResponse> => apiRequest<ListResponse>('/api/api-tokens'),

  create: (body: { environment: string; name: string; secret: string }) =>
    apiRequest<CreatedToken>('/api/api-tokens', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  rotate: (id: string, secret: string) =>
    apiRequest<ApiToken>(`/api/api-tokens/${id}/rotate`, {
      method: 'POST',
      body: JSON.stringify({ secret }),
    }),

  rename: (id: string, name: string) =>
    apiRequest<ApiToken>(`/api/api-tokens/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  remove: (id: string) =>
    apiRequest<void>(`/api/api-tokens/${id}`, { method: 'DELETE' }),
};
