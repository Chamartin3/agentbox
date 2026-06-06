import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

vi.mock('@/api/client', () => ({
  api: {
    listRunnerProfiles: vi.fn(),
    listRunnerProviders: vi.fn(),
    listRunnerBackends: vi.fn(),
    refreshRunnerProviders: vi.fn(),
    deleteRunnerProfile: vi.fn(),
  },
}));

import { api } from '@/api/client';
import {
  useRunnerBackends,
  useRunnerProfileActions,
  useRunnerProfiles,
  useRunnerProviders,
} from '@/hooks/runnerProfiles';

const a = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe('runnerProfiles hooks', () => {
  beforeEach(() => {
    Object.values(a).forEach((m) => m.mockReset());
  });

  describe.each([
    ['useRunnerProfiles', useRunnerProfiles, 'listRunnerProfiles'],
    ['useRunnerProviders', useRunnerProviders, 'listRunnerProviders'],
    ['useRunnerBackends', useRunnerBackends, 'listRunnerBackends'],
  ] as const)('%s', (_name, hook, apiFn) => {
    it('loads from the corresponding api method', async () => {
      a[apiFn].mockResolvedValue([{ id: 'p1' }]);
      const { result } = renderHook(() => hook());
      await waitFor(() => expect(result.current.loading).toBe(false));
      expect(result.current.data).toEqual([{ id: 'p1' }]);
      expect(a[apiFn]).toHaveBeenCalledTimes(1);
    });
  });

  describe('useRunnerProfileActions', () => {
    it('refreshProviders triggers refresh + onChange', async () => {
      a.refreshRunnerProviders.mockResolvedValue({ ok: true });
      const onChange = vi.fn();
      const { result } = renderHook(() => useRunnerProfileActions(onChange));
      await act(async () => {
        await result.current.refreshProviders();
      });
      expect(a.refreshRunnerProviders).toHaveBeenCalled();
      expect(onChange).toHaveBeenCalled();
    });

    it('remove deletes + calls onChange', async () => {
      a.deleteRunnerProfile.mockResolvedValue(undefined);
      const onChange = vi.fn();
      const { result } = renderHook(() => useRunnerProfileActions(onChange));
      await act(async () => {
        await result.current.remove('p1');
      });
      expect(a.deleteRunnerProfile).toHaveBeenCalledWith('p1');
      expect(onChange).toHaveBeenCalled();
    });
  });
});
