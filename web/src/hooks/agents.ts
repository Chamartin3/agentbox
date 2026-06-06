import { useCallback } from 'react';
import { api, type AgentDef, type RunnerSpec } from '../api/client';
import { useFetch } from './fetch';

export type AgentDetail = Awaited<ReturnType<typeof api.getAgent>>;
export type AgentCreatePayload = Parameters<typeof api.createAgent>[0];
export type AgentPatch = Partial<AgentDef> & { runner?: Partial<RunnerSpec> };

export function useAgents(opts?: { includeDisabled?: boolean }) {
  const includeDisabled = !!opts?.includeDisabled;
  return useFetch<AgentDef[]>(
    () => api.listAgents({ includeDisabled }),
    [includeDisabled],
  );
}

export function useAgent(id: string | null | undefined) {
  return useFetch<AgentDetail | null>(
    async () => (id ? await api.getAgent(id) : null),
    [id ?? ''],
  );
}

export function useAgentActions() {
  const create = useCallback((payload: AgentCreatePayload) => api.createAgent(payload), []);
  const patch = useCallback((id: string, body: AgentPatch) => api.patchAgent(id, body), []);
  const disable = useCallback((id: string) => api.disableAgent(id), []);
  const enable = useCallback((id: string) => api.enableAgent(id), []);
  const setRunnerProfile = useCallback(
    (id: string, profileId: string) => api.setAgentRunnerProfile(id, profileId),
    [],
  );
  const clearRunnerProfile = useCallback((id: string) => api.clearAgentRunnerProfile(id), []);
  return { create, patch, disable, enable, setRunnerProfile, clearRunnerProfile };
}
