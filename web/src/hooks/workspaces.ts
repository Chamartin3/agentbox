import { useCallback } from 'react';
import { api } from '../api/client';
import { apiRequestOrNull } from '../api/http';
import { subagentsApi } from '../api/repo';
import { useFetch } from './fetch';

export interface WorkspaceBundle {
  ws: Record<string, unknown>;
  permissions: Record<string, unknown>;
  builtinTools: string[];
  skills: Array<{ name: string; path: string; size: number }>;
  subagentCount: number;
  bindingCount: number;
}

async function loadWorkspaceBundle(id: string): Promise<WorkspaceBundle> {
  const [ws, perms, mcp, sk, subagents, bindings] = await Promise.all([
    api.getWorkspaceByName(id),
    api.getWorkspacePermissionsByName(id),
    api.getWorkspaceMcpToolsByName(id),
    api.listWorkspaceSkillsByName(id),
    subagentsApi.list(id),
    apiRequestOrNull<{ items: unknown[] }>(
      `/api/workspaces/${encodeURIComponent(id)}/resources`,
    ).then((d) => d ?? { items: [] }),
  ]);
  return {
    ws: ws as Record<string, unknown>,
    permissions: (perms as { permissions?: Record<string, unknown> }).permissions ?? {},
    builtinTools: (mcp as { builtin_tools?: string[] }).builtin_tools ?? [],
    skills: (sk as { skills?: WorkspaceBundle['skills'] }).skills ?? [],
    subagentCount: subagents.items?.length ?? 0,
    bindingCount: (bindings as { items: unknown[] }).items?.length ?? 0,
  };
}

export function useWorkspace(id: string | null | undefined) {
  return useFetch<WorkspaceBundle | null>(
    async () => (id ? await loadWorkspaceBundle(id) : null),
    [id ?? ''],
  );
}

export function useWorkspaceActions() {
  const create = useCallback(
    (body: { name: string; description?: string; path?: string }) =>
      api.createWorkspaceRegistry(body),
    [],
  );
  const remove = useCallback(
    (name: string, purgeDisk = false) => api.deleteWorkspaceRegistry(name, purgeDisk),
    [],
  );
  const generateConfigs = useCallback(
    (name: string) => api.generateWorkspaceConfigsByName(name),
    [],
  );
  const generateSkills = useCallback(
    (name: string) => api.generateWorkspaceSkillsByName(name),
    [],
  );
  const setPermissions = useCallback(
    (name: string, permissions: Record<string, unknown>) =>
      api.setWorkspacePermissionsByName(name, permissions),
    [],
  );
  const getFile = useCallback(
    (name: string, path: string) => api.getWorkspaceFileByName(name, path),
    [],
  );
  const putFile = useCallback(
    (name: string, path: string, content: string) =>
      api.putWorkspaceFileByName(name, path, content),
    [],
  );
  const listPaginated = useCallback(
    (params: Parameters<typeof api.listWorkspacesPaginated>[0]) =>
      api.listWorkspacesPaginated(params),
    [],
  );
  return { create, remove, generateConfigs, generateSkills, setPermissions, getFile, putFile, listPaginated };
}
