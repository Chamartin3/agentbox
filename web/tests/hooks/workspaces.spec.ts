import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('@/api/client', () => ({
  api: {
    getWorkspaceByName: vi.fn(),
    getWorkspacePermissionsByName: vi.fn(),
    getWorkspaceMcpToolsByName: vi.fn(),
    listWorkspaceSkillsByName: vi.fn(),
    createWorkspaceRegistry: vi.fn(),
    deleteWorkspaceRegistry: vi.fn(),
    generateWorkspaceConfigsByName: vi.fn(),
    generateWorkspaceSkillsByName: vi.fn(),
    setWorkspacePermissionsByName: vi.fn(),
    getWorkspaceFileByName: vi.fn(),
    putWorkspaceFileByName: vi.fn(),
    listWorkspacesPaginated: vi.fn(),
  },
}));
vi.mock('@/api/http', () => ({
  apiRequestOrNull: vi.fn(),
}));
vi.mock('@/api/repo', () => ({
  subagentsApi: { list: vi.fn() },
}));

import { api } from '@/api/client';
import { apiRequestOrNull } from '@/api/http';
import { subagentsApi } from '@/api/repo';
import { useWorkspace, useWorkspaceActions } from '@/hooks/workspaces';

const a = api as unknown as Record<string, ReturnType<typeof vi.fn>>;
const subList = subagentsApi.list as unknown as ReturnType<typeof vi.fn>;
const reqOrNull = apiRequestOrNull as unknown as ReturnType<typeof vi.fn>;

describe('workspaces hooks', () => {
  beforeEach(() => {
    Object.values(a).forEach((m) => m.mockReset());
    subList.mockReset();
    reqOrNull.mockReset();
  });

  describe('useWorkspace', () => {
    it('skips when id is null', async () => {
      const { result } = renderHook(() => useWorkspace(null));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(a.getWorkspaceByName).not.toHaveBeenCalled();
      expect(result.current.data).toBeNull();
    });

    it('composes bundle from 6 parallel sources', async () => {
      a.getWorkspaceByName.mockResolvedValue({ name: 'ws1' });
      a.getWorkspacePermissionsByName.mockResolvedValue({ permissions: { read: true } });
      a.getWorkspaceMcpToolsByName.mockResolvedValue({ builtin_tools: ['fs.read', 'shell.exec'] });
      a.listWorkspaceSkillsByName.mockResolvedValue({ skills: [{ name: 's', path: 'p', size: 1 }] });
      subList.mockResolvedValue({ items: [{ id: 'sub1' }] });
      reqOrNull.mockResolvedValue({ items: [{ id: 'b1' }, { id: 'b2' }] });

      const { result } = renderHook(() => useWorkspace('ws1'));
      await waitFor(() => expect(result.current.loading).toBe(false));

      expect(result.current.data).toEqual({
        ws: { name: 'ws1' },
        permissions: { read: true },
        builtinTools: ['fs.read', 'shell.exec'],
        skills: [{ name: 's', path: 'p', size: 1 }],
        subagentCount: 1,
        bindingCount: 2,
      });
    });

    it('defaults gracefully when binding endpoint returns null', async () => {
      a.getWorkspaceByName.mockResolvedValue({});
      a.getWorkspacePermissionsByName.mockResolvedValue({});
      a.getWorkspaceMcpToolsByName.mockResolvedValue({});
      a.listWorkspaceSkillsByName.mockResolvedValue({});
      subList.mockResolvedValue({ items: [] });
      reqOrNull.mockResolvedValue(null);

      const { result } = renderHook(() => useWorkspace('ws1'));
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data?.bindingCount).toBe(0);
      expect(result.current.data?.builtinTools).toEqual([]);
    });
  });

  describe('useWorkspaceActions', () => {
    it.each([
      ['create', 'createWorkspaceRegistry', [{ name: 'w' }]],
      ['generateConfigs', 'generateWorkspaceConfigsByName', ['w']],
      ['generateSkills', 'generateWorkspaceSkillsByName', ['w']],
      ['setPermissions', 'setWorkspacePermissionsByName', ['w', { read: true }]],
      ['getFile', 'getWorkspaceFileByName', ['w', 'p']],
      ['putFile', 'putWorkspaceFileByName', ['w', 'p', 'c']],
      ['listPaginated', 'listWorkspacesPaginated', [{ q: 'x' }]],
    ] as const)('%s delegates to api.%s', async (action, apiFn, args) => {
      a[apiFn].mockResolvedValue('ok');
      const { result } = renderHook(() => useWorkspaceActions());
      await act(async () => {
        const fn = result.current[action] as (...a: unknown[]) => Promise<unknown>;
        await fn(...args);
      });
      expect(a[apiFn]).toHaveBeenCalledWith(...args);
    });

    it('remove defaults purgeDisk to false', async () => {
      a.deleteWorkspaceRegistry.mockResolvedValue('ok');
      const { result } = renderHook(() => useWorkspaceActions());
      await act(async () => {
        await result.current.remove('w');
      });
      expect(a.deleteWorkspaceRegistry).toHaveBeenCalledWith('w', false);
    });

    it('remove forwards purgeDisk=true', async () => {
      a.deleteWorkspaceRegistry.mockResolvedValue('ok');
      const { result } = renderHook(() => useWorkspaceActions());
      await act(async () => {
        await result.current.remove('w', true);
      });
      expect(a.deleteWorkspaceRegistry).toHaveBeenCalledWith('w', true);
    });
  });
});
